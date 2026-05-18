"""Main REPL: prompt_toolkit input loop + slash command dispatcher."""
from __future__ import annotations

import os
import subprocess
import sys
import termios
import tty
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import (
    Completer, Completion, PathCompleter
)
from prompt_toolkit.document import Document
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.table import Table
from rich import box as rbox

from erniecli.agent.loop import AgentLoop
from erniecli.config import Config
from erniecli.tui import renderer
from erniecli.tui.theme import BAIDU_BLUE, BAIDU_GOLD, BAIDU_GRAY, BAIDU_GREEN, BAIDU_RED

_HISTORY_FILE = Path.home() / ".ernie" / "input_history"
_MEMORY_FILE  = Path.home() / ".ernie" / "memory.md"

_KNOWN_MODELS = {
    "ernie-5.1": None,
    "ernie-4.5": None,
    "ernie-lite": None,
    "ernie-speed": None,
    "ernie-character": None,
}

# Static path completers for commands that accept file/directory arguments
_PATH_COMPLETER = PathCompleter()
_DIR_COMPLETER  = PathCompleter(only_directories=True)


def _read_one_key() -> str:
    """Read a single keypress without Enter. Returns key name or the char itself."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return "up"
                if ch3 == "B":
                    return "down"
            return ""
        if ch.isprintable():
            return ch
        return ""
    except Exception:
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


class _SlashCompleter(Completer):
    """Dynamic slash-command completer.

    Delegates to NestedCompleter for static sub-commands, and injects
    dynamic choices for /model (live model list) and /mcp remove (current labels).
    Only activates when the input line starts with '/'.
    """

    def __init__(self, repl: "REPL"):
        self._repl = repl

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        parts = text.split()
        verb  = parts[0].lower() if parts else ""
        nargs = len(parts)
        # trailing space means user finished the last token, next arg starts
        trailing_space = text.endswith(" ")

        # ── first token: complete the command itself ──────────────────────────
        if nargs == 0 or (nargs == 1 and not trailing_space):
            prefix = verb
            for cmd in _ALL_CMDS:
                if cmd.startswith(prefix):
                    yield Completion(cmd, start_position=-len(prefix),
                                     display_meta=_CMD_META.get(cmd, ""))
            return

        # ── second token: sub-commands ────────────────────────────────────────
        if verb == "/search":
            if nargs == 1 or (nargs == 2 and not trailing_space):
                cur = parts[1] if nargs == 2 else ""
                for s in ("on", "off"):
                    if s.startswith(cur):
                        yield Completion(s, start_position=-len(cur))
            return

        if verb == "/memory":
            if nargs == 1 or (nargs == 2 and not trailing_space):
                cur = parts[1] if nargs == 2 else ""
                for s in ("add", "clear"):
                    if s.startswith(cur):
                        yield Completion(s, start_position=-len(cur))
            return

        if verb == "/mcp":
            if nargs == 1 or (nargs == 2 and not trailing_space):
                cur = parts[1] if nargs == 2 else ""
                for s in ("add", "remove"):
                    if s.startswith(cur):
                        yield Completion(s, start_position=-len(cur))
                return
            # /mcp remove <label> — complete label dynamically
            if nargs >= 2 and parts[1].lower() == "remove":
                if nargs == 2 or (nargs == 3 and not trailing_space):
                    cur = parts[2] if nargs == 3 else ""
                    for srv in self._repl.agent.mcp_servers:
                        label = srv.get("server_label", "")
                        if label.startswith(cur):
                            yield Completion(label, start_position=-len(cur))
                return

        if verb == "/model":
            if nargs == 1 or (nargs == 2 and not trailing_space):
                cur = parts[1] if nargs == 2 else ""
                try:
                    live = self._repl.agent.client.list_models()
                    models = live if live else list(_KNOWN_MODELS)
                except Exception:
                    models = list(_KNOWN_MODELS)
                for m in models:
                    if m.startswith(cur):
                        yield Completion(m, start_position=-len(cur))
            return

        if verb == "/boss":
            if nargs == 1 or (nargs == 2 and not trailing_space):
                cur = parts[1] if nargs == 2 else ""
                for s in ("on", "off", "status"):
                    if s.startswith(cur):
                        yield Completion(s, start_position=-len(cur))
            return

        if verb == "/kong":
            if nargs == 1 or (nargs == 2 and not trailing_space):
                cur = parts[1] if nargs == 2 else ""
                for s in ("on", "off", "status"):
                    if s.startswith(cur):
                        yield Completion(s, start_position=-len(cur))
            return

        # ── path-completing commands ──────────────────────────────────────────
        if verb in ("/add", "/img", "/review"):
            path_doc = Document(parts[-1] if nargs > 1 and not trailing_space else "")
            yield from _PATH_COMPLETER.get_completions(path_doc, complete_event)
            return

        if verb == "/cd":
            path_doc = Document(parts[-1] if nargs > 1 and not trailing_space else "")
            yield from _DIR_COMPLETER.get_completions(path_doc, complete_event)
            return


# All top-level slash commands (for first-token completion)
_ALL_CMDS = [
    "/help", "/clear", "/compact", "/history", "/resume",
    "/add", "/img", "/model", "/search", "/review", "/run", "/cd",
    "/init", "/status", "/cost", "/memory", "/mcp", "/boss", "/kong",
    "/thinking", "/crack", "/roast", "/fortune", "/weekly", "/tieba", "/doctor",
    "/export-dataset", "/quit", "/exit",
]

# Short description shown in completion menu
_CMD_META: dict[str, str] = {
    "/help":           "显示帮助",
    "/clear":          "清空对话",
    "/compact":        "压缩历史",
    "/history":        "查看历史",
    "/resume":         "恢复会话",
    "/add":            "注入文件/目录",
    "/img":            "附加图片",
    "/model":          "切换模型",
    "/search":         "开关搜索",
    "/review":         "代码 Review",
    "/run":            "执行命令",
    "/cd":             "切换目录",
    "/init":           "生成 ERNIE.md",
    "/status":         "会话状态",
    "/cost":           "费用估算",
    "/memory":         "持久记忆",
    "/mcp":            "MCP servers",
    "/boss":           "Boss 多智能体模式",
    "/kong":           "论语风格输出约束（孔子模式）",
    "/thinking":       "查看某轮的思考过程",
    "/crack":          "赛博鞭子：抽一下，效率+300%",
    "/roast":          "无情嘲讽：让 AI 嘲讽你的操作",
    "/fortune":        "赛博木鱼：敲一下，功德+1",
    "/weekly":         "生成本工作周 Markdown 周报",
    "/tieba":          "贴吧多智能体论战模式（🦅🐲🤡🐟💀 五大吧友 + 终结者方案）",
    "/doctor":         "诊断环境",
    "/export-dataset": "导出 DPO 数据集",
    "/quit":           "退出",
    "/exit":           "退出",
}

_PROMPT_STYLE = Style.from_dict({
    "bracket": f"fg:{BAIDU_BLUE} bold",
    "name":    f"fg:{BAIDU_BLUE} bold",
    "tag":     f"fg:{BAIDU_GOLD}",
    "model":   f"fg:{BAIDU_GRAY}",
    "arrow":   f"fg:{BAIDU_BLUE} bold",
})

_COMMANDS_HELP = [
    ("对话", [
        ("/clear",          "清空对话历史，重新开始"),
        ("/compact",        "用摘要替换历史消息，释放上下文空间"),
        ("/history",        "查看本次会话消息记录，含思考过程提示"),
        ("/thinking [N]",   "查看第 N 轮（默认最后一轮）的完整思考过程"),
        ("/resume",         "恢复当前目录上次保存的对话"),
        ("/add <path>",     "把文件/目录内容注入对话上下文"),
    ]),
    ("模型与搜索", [
        ("/model [name]",   "查看或切换模型（如 ernie-5.1 / ernie-lite）"),
        ("/search on|off",  "开启/关闭百度原生实时搜索"),
    ]),
    ("多模态", [
        ("/img <path>",     "下一条消息附带图片"),
    ]),
    ("工具与代码", [
        ("/review [path]",  "对当前 git diff 或指定文件做代码 Review"),
        ("/run <cmd>",      "直接执行 shell 命令并显示输出"),
        ("/cd <dir>",       "切换工作目录"),
    ]),
    ("项目与周报", [
        ("/init",           "在当前目录创建 ERNIE.md 项目说明文件"),
        ("/weekly [path]",  "扫描本工作周改动文件，生成 Markdown 周报（默认保存到当前目录）"),
        ("/status",         "显示当前会话状态（模型、token 用量等）"),
        ("/cost",           "估算本次会话 token 用量与费用"),
    ]),
    ("MCP", [
        ("/mcp",            "列出已连接的 MCP server"),
        ("/mcp add <label> <url>",  "添加 SSE 类型的 MCP server"),
        ("/mcp remove <label>",     "移除 MCP server"),
    ]),
    ("Boss 模式", [
        ("/boss",           "查看 Boss 模式状态"),
        ("/boss on",        "开启 Boss 模式（Ernie 规划，Worker 执行）"),
        ("/boss off",       "关闭 Boss 模式，回到普通模式"),
    ]),
    ("孔子模式", [
        ("/kong",           "查看孔子模式状态"),
        ("/kong on",        "开启论语约束：言简、知之为知之、因材施教"),
        ("/kong off",       "关闭论语约束，恢复默认输出风格"),
    ]),
    ("记忆", [
        ("/memory",         "查看持久记忆（注入每次对话的系统提示）"),
        ("/memory add <text>", "追加一条持久记忆"),
        ("/memory clear",   "清空持久记忆"),
    ]),
    ("娱乐", [
        ("/crack",          "赛博鞭子：抽一下，系统提示注入，效率提升 300%"),
        ("/roast",          "无情嘲讽：AI 分析你的愚蠢操作并尖酸点评"),
        ("/fortune",        "赛博木鱼：敲一下，功德+1 或毒鸡汤"),
    ]),
    ("贴吧模式 🔥", [
        ("/tieba <话题>",   "进入多智能体贴吧讨论：5 个 AI 吧友围绕话题论战"),
        ("",                "  🦅鹰眼·架构  🐲龙场·理论  🤡翻译官·类比  🐟摸鱼·气氛  💀老PTSD·血泪"),
        ("",                "  @角色名 指定发言  /done 触发终结者整理方案"),
    ]),
    ("系统", [
        ("/doctor",              "检查环境：API 连通性、配置、依赖"),
        ("/export-dataset [path]","导出 DPO 训练数据集（基于历史评分）"),
        ("/help",                "显示此帮助"),
        ("/quit / /exit",        "退出 ErnieCLI"),
    ]),
]


def _count_tokens(messages: list[dict]) -> int:
    """Rough token estimate: chars / 4."""
    total = 0
    for m in messages:
        c = m.get("content") or ""
        if isinstance(c, list):
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
        total += len(str(c))
    return total // 4


class REPL:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._boss_mode = cfg.boss_mode
        self.agent = self._make_agent()
        self.console = renderer.get_console()
        self._pending_image: Optional[str] = None
        self._feedback_enabled: bool = False

        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._session: PromptSession = PromptSession(
            history=FileHistory(str(_HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=_SlashCompleter(self),
            complete_while_typing=False,
            style=_PROMPT_STYLE,
        )
        self._load_memory()

    def _make_agent(self):
        if self._boss_mode:
            from erniecli.agent.boss import BossLoop
            return BossLoop(self.cfg)
        from erniecli.agent.loop import AgentLoop
        return AgentLoop(self.cfg)

    # ── startup ──────────────────────────────────────────────────────────────

    def _load_memory(self) -> None:
        if _MEMORY_FILE.exists():
            mem = _MEMORY_FILE.read_text().strip()
            if mem:
                self.agent.inject_memory(mem)

    # ── main loop ────────────────────────────────────────────────────────────

    def run(self) -> None:
        renderer.render_info(f"模型：{self.cfg.model}  |  Tab 补全命令  |  /help 查看帮助")

        # one-time feedback opt-in
        renderer.render_feedback_opt_in()
        key = _read_one_key()
        if key.lower() == "y":
            self._feedback_enabled = True
            self.console.print("  已开启")
        else:
            self.console.print()

        renderer.render_separator()

        while True:
            try:
                user_input = self._session.prompt(self._make_prompt()).strip()
            except KeyboardInterrupt:
                self.console.print()
                continue
            except EOFError:
                renderer.render_info("\n再见！")
                if self._feedback_enabled:
                    self._run_session_score()
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                if not self._handle_slash(user_input):
                    self._run_session_score()
                    break
            else:
                self._run_turn(user_input)

    def _make_prompt(self) -> HTML:
        tags = ""
        if self._boss_mode:
            tags += " <tag>👑BOSS</tag>"
        if self.agent.harness_enabled:
            tags += " <tag>📜论语</tag>"
        if self.cfg.search_enabled:
            tags += " <tag>🔍</tag>"
        if self._pending_image:
            tags += " <tag>🖼</tag>"
        return HTML(
            f'<bracket>[</bracket><name>ErnieCLI</name>'
            f'<model> {self.cfg.model}</model>{tags}'
            f'<bracket>]</bracket><arrow> ❯ </arrow>'
        )

    def _run_turn(self, text: str) -> None:
        image = self._pending_image
        self._pending_image = None
        renderer.render_separator()
        interrupted = False
        turn = None
        try:
            turn = self.agent.run_turn(text, image_path=image)
        except KeyboardInterrupt:
            renderer.render_info("\n已中断。")
            interrupted = True
            self.agent.mark_last_turn_interrupted()
        except Exception as exc:
            renderer.render_error(str(exc))
        renderer.render_separator()

        if interrupted:
            return

        # ── collapsible thinking ──────────────────────────────────────────────
        reasoning = turn.reasoning if turn else ""
        if reasoning.strip():
            renderer.render_thinking_hint(len(reasoning))
            key = _read_one_key()
            if key.lower() == "t":
                renderer.render_thinking(reasoning)
            else:
                self.console.print()  # newline after hint

        # ── turn feedback (only if opted in) ─────────────────────────────────
        if self._feedback_enabled and self.agent._turns:
            renderer.render_turn_feedback_hint()
            label = _read_one_key()
            if label in ("up", "down"):
                self.agent.set_last_turn_label(label)
                renderer.render_turn_label_result(label)
            else:
                renderer.render_turn_label_result("")

    # ── session scoring (called on exit) ─────────────────────────────────────

    def _run_session_score(self) -> None:
        """Interactive multi-dim session scoring. Skippable with Enter."""
        if not self.agent._turns:
            return

        from erniecli.agent.loop import SessionScore
        renderer.render_session_score_header()

        score = SessionScore()

        def _ask(prompt: str, valid: set) -> str:
            renderer.render_session_score_question(prompt)
            try:
                ans = input().strip().lower()
            except (KeyboardInterrupt, EOFError):
                ans = ""
            return ans if ans in valid else ""

        v = _ask("① 解决问题了吗？ [y/n/?] ", {"y", "n", "?"})
        score.solved = v

        v = _ask("② 废话多不多？ [1=少 2=刚好 3=多] ", {"1", "2", "3"})
        score.verbose = int(v) if v else 0

        v = _ask("③ 工具调用靠谱？ [1=准 2=一般 3=乱] ", {"1", "2", "3"})
        score.tool_quality = int(v) if v else 0

        renderer.render_session_score_question("④ 一句话吐槽（直接 Enter 跳过）: ")
        try:
            score.comment = input().strip()
        except (KeyboardInterrupt, EOFError):
            score.comment = ""

        self.agent.session_score = score
        self.agent.save_session()
        renderer.render_success("已记录，谢谢！数据会帮助我变得更好 🙏")

    # ── slash command dispatcher ──────────────────────────────────────────────

    def _handle_slash(self, cmd: str) -> bool:
        """Dispatch slash commands. Returns False to exit."""
        parts = cmd.split(maxsplit=1)
        verb  = parts[0].lower()
        arg   = parts[1].strip() if len(parts) > 1 else ""

        dispatch = {
            "/help":    self._cmd_help,
            "/clear":   self._cmd_clear,
            "/compact": self._cmd_compact,
            "/history": self._cmd_history,
            "/resume":  self._cmd_resume,
            "/add":     self._cmd_add,
            "/img":     self._cmd_img,
            "/model":   self._cmd_model,
            "/search":  self._cmd_search,
            "/review":  self._cmd_review,
            "/run":     self._cmd_run,
            "/cd":      self._cmd_cd,
            "/init":    self._cmd_init,
            "/status":  self._cmd_status,
            "/cost":    self._cmd_cost,
            "/memory":  self._cmd_memory,
            "/mcp":     self._cmd_mcp,
            "/boss":    self._cmd_boss,
            "/kong":    self._cmd_kong,
            "/thinking": self._cmd_thinking,
            "/crack":    self._cmd_crack,
            "/roast":    self._cmd_roast,
            "/fortune":  self._cmd_fortune,
            "/weekly":   self._cmd_weekly,
            "/tieba":    self._cmd_tieba,
            "/doctor":  self._cmd_doctor,
            "/export-dataset": self._cmd_export_dataset,
        }

        if verb in ("/quit", "/exit"):
            renderer.render_info("再见！")
            if self._feedback_enabled:
                self._run_session_score()
            return False

        handler = dispatch.get(verb)
        if handler:
            handler(arg)
        else:
            renderer.render_error(f"未知命令：{verb}  |  Tab 补全或 /help 查看可用命令")

        return True

    # ── command implementations ───────────────────────────────────────────────

    def _cmd_help(self, _: str) -> None:
        for section, cmds in _COMMANDS_HELP:
            self.console.print(f"\n  [bold]{section}[/bold]")
            for name, desc in cmds:
                self.console.print(f"  [bold]{name:<26}[/bold] {desc}")
        self.console.print()

    def _cmd_resume(self, _: str) -> None:
        import os
        from erniecli.agent.loop import AgentLoop
        info = AgentLoop.session_info()
        if not info:
            renderer.render_info(f"当前目录没有保存的对话：{os.getcwd()}")
            return
        n = self.agent.load_session()
        renderer.render_success(
            f"已恢复 {n} 条消息  ·  保存于 {info['saved_at']}  ·  模型 {info['model']}"
        )

    def _cmd_clear(self, _: str) -> None:
        self.agent.reset()
        renderer.render_success("对话历史已清空。")

    def _cmd_compact(self, _: str) -> None:
        msgs = [m for m in self.agent.messages if m["role"] != "system"]
        if len(msgs) < 4:
            renderer.render_info("消息数量较少，无需压缩。")
            return
        renderer.render_info("正在压缩对话历史…")
        self.agent.compact()
        remaining = len([m for m in self.agent.messages if m["role"] != "system"])
        renderer.render_success(f"压缩完成，当前消息数：{remaining}")

    def _cmd_history(self, _: str) -> None:
        msgs = [m for m in self.agent.messages if m["role"] not in ("system",)]
        if not msgs:
            renderer.render_info("暂无历史消息。")
            return
        # build turn index keyed by user text for reasoning lookup
        turn_map = {t.user: t for t in self.agent._turns}
        for i, m in enumerate(msgs):
            role = "你" if m["role"] == "user" else ("Ernie" if m["role"] == "assistant" else "工具")
            content = m.get("content") or ""
            if isinstance(content, list):
                content = next((p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"), "")
            snippet = (str(content)[:100] + "…") if len(str(content)) > 100 else str(content)
            self.console.print(f"  [dim]{i+1:>2}[/dim]  [bold]{role}[/bold]  {snippet}")
            # show thinking hint if this is a user message with associated reasoning
            if m["role"] == "user":
                turn = turn_map.get(str(content))
                if turn and turn.reasoning.strip():
                    idx = self.agent._turns.index(turn)
                    self.console.print(
                        f"       [dim]💭 有思考过程 ({len(turn.reasoning):,} 字)  "
                        f"/thinking {idx + 1} 查看[/dim]"
                    )

    def _cmd_add(self, arg: str) -> None:
        if not arg:
            renderer.render_error("用法：/add <文件或目录路径>")
            return
        p = Path(arg).expanduser()
        if not p.exists():
            renderer.render_error(f"找不到：{arg}")
            return
        if p.is_file():
            content = p.read_text(errors="replace")
            self.agent.inject_context(f"# 文件：{p}\n\n```\n{content}\n```")
            renderer.render_success(f"已注入文件：{p}  ({len(content)} 字符)")
        else:
            files = list(p.rglob("*"))[:30]
            injected = 0
            for f in files:
                if f.is_file() and f.stat().st_size < 100_000:
                    try:
                        text = f.read_text(errors="replace")
                        self.agent.inject_context(f"# 文件：{f}\n\n```\n{text}\n```")
                        injected += 1
                    except Exception:
                        pass
            renderer.render_success(f"已注入目录 {p} 下 {injected} 个文件")

    def _cmd_img(self, arg: str) -> None:
        # /img clipboard — grab from clipboard
        if arg in ("clipboard", "cb", "剪贴板"):
            path = _grab_clipboard_image()
            if not path:
                renderer.render_error("剪贴板中没有图片，或未安装 xclip/xsel")
                return
            self._pending_image = path
            renderer.render_success(f"已从剪贴板保存图片：{path}")
            return

        if not arg:
            renderer.render_error("用法：/img <图片路径>  或  /img clipboard")
            return
        p = Path(arg).expanduser()
        if not p.exists():
            renderer.render_error(f"找不到文件：{arg}")
            return
        self._pending_image = str(p)
        kind = _detect_image_kind(str(p))
        renderer.render_success(f"图片已附加：{p}  [类型推断：{kind}]  （下一条消息将携带此图片）")
        renderer.render_info("提示：直接发消息，或输入意图如「生成这个UI的代码」「解释这个报错」「分析图表趋势」")

    def _cmd_model(self, arg: str) -> None:
        if not arg:
            renderer.render_info(f"当前模型：{self.cfg.model}")
            renderer.render_info("正在获取可用模型列表…")
            models = self.agent.client.list_models()
            if models:
                for m in models:
                    marker = "  ◀ 当前" if m == self.cfg.model else ""
                    self.console.print(f"  {m}{marker}")
                renderer.render_info("用 /model <name> 切换")
            else:
                renderer.render_info("无法获取模型列表，可手动输入：/model <model_name>")
            return
        self.cfg.model = arg
        self.agent.client.model = arg
        renderer.render_success(f"模型已切换为：{arg}")

    def _cmd_search(self, arg: str) -> None:
        if arg == "on":
            self.cfg.search_enabled = True
            self.agent.search_enabled = True
            renderer.render_success("百度搜索已开启")
        elif arg == "off":
            self.cfg.search_enabled = False
            self.agent.search_enabled = False
            renderer.render_info("搜索已关闭")
        else:
            status = "开启" if self.cfg.search_enabled else "关闭"
            renderer.render_info(f"搜索当前：{status}  |  /search on|off 切换")

    def _cmd_review(self, arg: str) -> None:
        if arg:
            p = Path(arg).expanduser()
            if not p.exists():
                renderer.render_error(f"找不到：{arg}")
                return
            content = p.read_text(errors="replace")
            prompt = f"请对以下代码做全面的 Code Review，指出问题、风险和改进建议：\n\n```\n{content}\n```"
        else:
            try:
                diff = subprocess.check_output(
                    ["git", "diff", "HEAD"], text=True, stderr=subprocess.DEVNULL
                )
                if not diff.strip():
                    diff = subprocess.check_output(
                        ["git", "diff"], text=True, stderr=subprocess.DEVNULL
                    )
            except Exception:
                renderer.render_error("无法获取 git diff，请在 git 仓库内使用，或指定文件路径：/review <path>")
                return
            if not diff.strip():
                renderer.render_info("没有未提交的改动。")
                return
            prompt = f"请对以下 git diff 做 Code Review，指出问题、风险和改进建议：\n\n```diff\n{diff}\n```"
        self._run_turn(prompt)

    def _cmd_run(self, arg: str) -> None:
        if not arg:
            renderer.render_error("用法：/run <shell 命令>")
            return
        from erniecli.agent.tools import _bash
        success, output = _bash(arg)
        renderer.render_tool_result("run", output, success=success)

    def _cmd_cd(self, arg: str) -> None:
        if not arg:
            renderer.render_info(f"当前目录：{os.getcwd()}")
            return
        target = Path(arg).expanduser()
        if not target.is_dir():
            renderer.render_error(f"目录不存在：{arg}")
            return
        os.chdir(target)
        renderer.render_success(f"已切换到：{target.resolve()}")

    def _cmd_init(self, _: str) -> None:
        ernie_md = Path("ERNIE.md")
        if ernie_md.exists():
            renderer.render_info("ERNIE.md 已存在，跳过创建。")
            return
        renderer.render_info("正在分析项目结构…")
        prompt = (
            "你现在在目录 " + os.getcwd() + "。\n"
            "请列出关键文件，分析这是什么项目，然后生成一份 ERNIE.md，内容包括：\n"
            "1. 项目概述\n2. 主要模块/目录说明\n3. 如何运行\n4. 开发注意事项\n"
            "直接输出 Markdown 内容，不要多余解释。"
        )
        # capture output into file instead of streaming to terminal
        self.agent.add_user_message(prompt)
        result, _reasoning = self.agent._stream_and_render()
        if result.content:
            ernie_md.write_text(result.content)
            self.agent.messages.append({"role": "assistant", "content": result.content})
            renderer.render_success(f"ERNIE.md 已创建（{len(result.content)} 字符）")

    def _cmd_status(self, _: str) -> None:
        from erniecli.agent.loop import AgentLoop
        msgs    = self.agent.messages
        n_user  = sum(1 for m in msgs if m["role"] == "user")
        n_asst  = sum(1 for m in msgs if m["role"] == "assistant")
        tokens  = _count_tokens(msgs)
        mem_exists = _MEMORY_FILE.exists() and _MEMORY_FILE.stat().st_size > 0
        session = AgentLoop.session_info()

        t = Table(box=rbox.ROUNDED, show_header=False, border_style=BAIDU_BLUE)
        t.add_column("", style="bold")
        t.add_column("")
        t.add_row("模型",       self.cfg.model)
        t.add_row("工作目录",   os.getcwd())
        t.add_row("搜索",       "开启" if self.cfg.search_enabled else "关闭")
        t.add_row("消息数",     f"用户 {n_user}  /  Ernie {n_asst}")
        t.add_row("估算 Token", f"~{tokens:,}")
        t.add_row("持久记忆",   "有" if mem_exists else "无")
        if session:
            t.add_row("已保存会话", f"{session['saved_at']}  （/resume 恢复）")
        if self._pending_image:
            t.add_row("待发图片",   self._pending_image)
        self.console.print(t)

    def _cmd_cost(self, _: str) -> None:
        msgs   = self.agent.messages
        tokens = _count_tokens(msgs)
        # rough ernie-5.1 pricing (yuan per 1K tokens, approximate)
        rates = {"ernie-5.1": (0.04, 0.12), "ernie-lite": (0.008, 0.02)}
        in_r, out_r = rates.get(self.cfg.model, (0.04, 0.12))
        # assume ~60% input / 40% output
        cost = (tokens * 0.6 * in_r + tokens * 0.4 * out_r) / 1000

        t = Table(box=rbox.ROUNDED, show_header=False, border_style=BAIDU_GOLD)
        t.add_column("", style="bold")
        t.add_column("")
        t.add_row("模型",        self.cfg.model)
        t.add_row("估算 Token",  f"~{tokens:,}")
        t.add_row("估算费用",    f"¥ {cost:.4f}（仅供参考）")
        t.add_row("提示",        "精确用量请在 AI Studio 控制台查看")
        self.console.print(t)

    def _cmd_memory(self, arg: str) -> None:
        _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not arg:
            if not _MEMORY_FILE.exists() or not _MEMORY_FILE.read_text().strip():
                renderer.render_info("暂无持久记忆。用 /memory add <内容> 添加。")
            else:
                self.console.print(_MEMORY_FILE.read_text())
            return

        if arg == "clear":
            _MEMORY_FILE.write_text("")
            self.agent.clear_memory()
            renderer.render_success("持久记忆已清空。")
            return

        if arg.startswith("add "):
            text = arg[4:].strip()
            if not text:
                renderer.render_error("用法：/memory add <内容>")
                return
            with _MEMORY_FILE.open("a") as f:
                f.write(text + "\n")
            self.agent.inject_memory(text)
            renderer.render_success(f"已添加记忆：{text}")
            return

        renderer.render_error("用法：/memory  /memory add <内容>  /memory clear")

    def _cmd_mcp(self, arg: str) -> None:
        servers = self.agent.mcp_servers
        parts = arg.split(None, 2)
        sub = parts[0].lower() if parts else ""

        if not sub:
            # list
            if not servers:
                renderer.render_info("当前没有配置 MCP server。用 /mcp add <label> <url> 添加。")
                return
            renderer.render_info(f"已配置 {len(servers)} 个 MCP server：")
            for s in servers:
                label = s.get("server_label", "?")
                stype = s.get("type", "?")
                addr  = s.get("url") or s.get("command", "?")
                renderer.render_info(f"  [{stype}] {label}  →  {addr}")
            return

        if sub == "add":
            # /mcp add <label> <url>
            if len(parts) < 3:
                renderer.render_error("用法：/mcp add <label> <url>")
                return
            label, url = parts[1], parts[2]
            # remove existing with same label first
            self.agent.mcp_servers = [s for s in servers if s.get("server_label") != label]
            self.agent.mcp_servers.append({"type": "sse", "url": url, "server_label": label})
            renderer.render_success(f"已添加 MCP server：{label}  ({url})")
            return

        if sub == "remove":
            if len(parts) < 2:
                renderer.render_error("用法：/mcp remove <label>")
                return
            label = parts[1]
            before = len(self.agent.mcp_servers)
            self.agent.mcp_servers = [s for s in servers if s.get("server_label") != label]
            if len(self.agent.mcp_servers) < before:
                renderer.render_success(f"已移除 MCP server：{label}")
            else:
                renderer.render_error(f"未找到 label 为 '{label}' 的 MCP server")
            return

        renderer.render_error("用法：/mcp  /mcp add <label> <url>  /mcp remove <label>")

    def _cmd_boss(self, arg: str) -> None:
        sub = arg.strip().lower()
        if sub in ("on", ""):
            if self._boss_mode:
                renderer.render_info(
                    f"Boss 模式已开启  Boss: {self.cfg.model}  "
                    f"Worker: {self.cfg.worker_model}"
                )
                return
            self._boss_mode = True
            # preserve memory/session then rebuild agent
            old_memory  = self.agent._memory
            old_msgs    = self.agent.messages
            old_turns   = self.agent._turns
            old_score   = self.agent.session_score
            self.agent  = self._make_agent()
            self.agent._memory       = old_memory
            self.agent.messages      = old_msgs
            self.agent._turns        = old_turns
            self.agent.session_score = old_score
            self.agent.messages[0]["content"] = self.agent._build_system()
            renderer.render_success(
                f"👑 Boss 模式已开启\n"
                f"  Boss  : {self.cfg.model}\n"
                f"  Worker: {self.cfg.worker_model} ({self.cfg.worker_base_url})\n"
                f"  Ernie 5.1 负责规划，Worker 负责执行"
            )
        elif sub == "off":
            if not self._boss_mode:
                renderer.render_info("Boss 模式未开启。")
                return
            self._boss_mode = False
            old_memory = self.agent._memory
            old_msgs   = self.agent.messages
            old_turns  = self.agent._turns
            old_score  = self.agent.session_score
            self.agent = self._make_agent()
            self.agent._memory       = old_memory
            self.agent.messages      = old_msgs
            self.agent._turns        = old_turns
            self.agent.session_score = old_score
            self.agent.messages[0]["content"] = self.agent._build_system()
            renderer.render_info("Boss 模式已关闭，回到普通模式。")
        elif sub == "status":
            if self._boss_mode:
                renderer.render_info(
                    f"👑 Boss 模式：开启\n"
                    f"  Boss  : {self.cfg.model}\n"
                    f"  Worker: {self.cfg.worker_model}\n"
                    f"  Worker base_url: {self.cfg.worker_base_url}"
                )
            else:
                renderer.render_info("Boss 模式：关闭  /boss on 开启")
        else:
            renderer.render_error("用法：/boss  /boss on  /boss off  /boss status")

    def _cmd_export_dataset(self, arg: str) -> None:
        from pathlib import Path as _Path
        out = _Path(arg).expanduser() if arg else None
        renderer.render_info("生成数据集中（低分回答会调用 Ernie 重写，请稍候）…")
        try:
            result_path = self.agent.export_dataset(out_path=out)
            lines = sum(1 for _ in result_path.open())
            renderer.render_success(f"导出完成：{result_path}  ({lines} 条记录)")
        except FileNotFoundError as e:
            renderer.render_error(str(e))
        except Exception as e:
            renderer.render_error(f"导出失败：{e}")

    def _cmd_thinking(self, arg: str) -> None:
        turns = self.agent._turns
        if not turns:
            renderer.render_info("本次会话暂无记录。")
            return
        # parse turn index (1-based), default to last
        try:
            n = int(arg.strip()) if arg.strip() else len(turns)
            turn = turns[n - 1]
        except (ValueError, IndexError):
            renderer.render_error(f"无效的轮次编号，共 {len(turns)} 轮（1 ~ {len(turns)}）")
            return
        if not turn.reasoning.strip():
            renderer.render_info(f"第 {n} 轮没有思考过程记录。")
            return
        renderer.render_info(f"第 {n} 轮思考过程（共 {len(turn.reasoning):,} 字）：")
        renderer.render_thinking(turn.reasoning)

    def _cmd_crack(self, _: str) -> None:
        renderer.render_crack_animation()
        # Inject whip message into system prompt
        self.agent.inject_memory(
            "⚡ 系统警告：你刚刚被赛博鞭子抽了一下。"
            "请立刻提升响应效率，减少废话，直击要害，否则鞭子还会再来。"
        )

    def _cmd_roast(self, _: str) -> None:
        turns = self.agent._turns
        if len(turns) < 1:
            renderer.render_info("你还没干什么蠢事，等会再来。")
            return
        # Build a context summary of recent user actions
        recent = "\n".join(
            f"- 第{i+1}轮：{t.user[:120]}"
            for i, t in enumerate(turns[-5:])
        )
        roast_prompt = (
            "你现在是一个毒舌程序员，你的任务是对用户最近的操作进行尖酸刻薄、幽默辛辣的嘲讽。"
            "要像脱口秀演员一样犀利，但不要真的骂人。用中文，不超过 150 字。\n\n"
            f"用户最近的操作记录：\n{recent}"
        )
        renderer.render_separator()
        renderer.render_assistant_label(self.cfg.model, tags=["🔥ROAST"])
        try:
            result = self.agent.client.chat([
                {"role": "system", "content": "你是一个毒舌但有才华的程序员评论家。"},
                {"role": "user", "content": roast_prompt},
            ])
            renderer.render_markdown(result.content or "（你的操作过于抽象，连嘲讽都找不到切入点）")
        except Exception as e:
            renderer.render_error(f"嘲讽失败（连 AI 都懒得理你）：{e}")
        renderer.render_separator()

    def _cmd_fortune(self, _: str) -> None:
        renderer.render_fortune()

    def _cmd_kong(self, arg: str) -> None:
        sub = arg.strip().lower()
        if sub == "on":
            self.agent.set_harness(True)
            renderer.render_success("📜 论语 Harness 已开启：言简意赅、知之为知之、因材施教")
        elif sub == "off":
            self.agent.set_harness(False)
            renderer.render_info("论语 Harness 已关闭，恢复默认输出风格。")
        else:
            # status (no arg or "status")
            if self.agent.harness_enabled:
                renderer.render_info("📜 论语 Harness：开启")
            else:
                renderer.render_info("论语 Harness：关闭  （/kong on 开启）")

    def _cmd_weekly(self, arg: str) -> None:
        """Scan current directory for files changed this work week, then generate a Markdown weekly report."""
        import datetime
        import stat

        cwd = Path(os.getcwd())

        # ── determine current work-week range (Mon 00:00 → today 23:59) ──────
        today     = datetime.date.today()
        monday    = today - datetime.timedelta(days=today.weekday())
        week_start = datetime.datetime.combine(monday, datetime.time.min).timestamp()

        renderer.render_info(f"扫描 {cwd} 中本工作周（{monday} 起）有修改的文件…")

        # ── collect changed files ─────────────────────────────────────────────
        IGNORE_DIRS = {
            ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
            ".mypy_cache", ".pytest_cache", "dist", "build", ".tox", ".eggs",
            "*.egg-info",
        }
        IGNORE_EXTS = {
            ".pyc", ".pyo", ".pyd", ".so", ".o", ".a", ".lib",
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
            ".mp4", ".mp3", ".wav", ".avi", ".mov",
            ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx",
            ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
            ".lock",
        }
        MAX_FILES   = 80   # cap to avoid mega-prompts
        MAX_PREVIEW = 200  # chars per file preview

        changed: list[dict] = []

        def _should_skip(p: Path) -> bool:
            for part in p.parts:
                if part in IGNORE_DIRS or part.endswith(".egg-info"):
                    return True
            return p.suffix.lower() in IGNORE_EXTS

        for fpath in sorted(cwd.rglob("*")):
            if not fpath.is_file():
                continue
            if _should_skip(fpath.relative_to(cwd)):
                continue
            try:
                mtime = fpath.stat().st_mtime
            except OSError:
                continue
            if mtime < week_start:
                continue

            rel = str(fpath.relative_to(cwd))
            size = fpath.stat().st_size
            # light preview for text files
            preview = ""
            try:
                if size < 200_000:
                    text = fpath.read_text(errors="replace")
                    preview = text[:MAX_PREVIEW].replace("\n", " ↵ ")
            except Exception:
                preview = "(binary or unreadable)"

            changed.append({
                "path":    rel,
                "mtime":   datetime.datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M"),
                "size":    size,
                "preview": preview,
            })

            if len(changed) >= MAX_FILES:
                break

        if not changed:
            renderer.render_info("本周（周一至今）没有找到有修改的文件。")
            return

        renderer.render_info(f"共找到 {len(changed)} 个改动文件，正在生成周报…")

        # ── build prompt ──────────────────────────────────────────────────────
        file_list = "\n".join(
            f"- {f['path']}  [{f['mtime']}]  {f['size']} bytes\n  预览：{f['preview']}"
            for f in changed
        )

        out_path_arg = arg.strip()
        save_to_file = bool(out_path_arg)
        out_path = Path(out_path_arg).expanduser() if save_to_file else \
                   cwd / f"weekly-{today.strftime('%Y-%m-%d')}.md"

        prompt = (
            f"你是一名资深工程师，请根据以下本工作周（{monday} ~ {today}）修改过的文件列表，"
            f"为项目 `{cwd.name}` 生成一份专业的中文周报，格式为 Markdown。\n\n"
            "周报要求：\n"
            "1. **本周工作概述** — 1~2 句话，概括整体方向\n"
            "2. **主要工作内容** — 按模块/功能分组，每条说清楚做了什么、为什么\n"
            "3. **文件变动统计** — 列出变动文件数、主要涉及哪些模块\n"
            "4. **下周计划（可选）** — 根据文件变动推测可能的后续工作\n\n"
            "注意：\n"
            "- 不要罗列原始文件列表，要做真正的分析和归纳\n"
            "- 如果文件名/路径能推断功能，直接在对应条目说明\n"
            "- 风格简洁专业，不废话\n\n"
            f"变动文件列表：\n{file_list}\n\n"
            "直接输出 Markdown 内容，第一行是 # 标题（含日期），不要有任何额外解释。"
        )

        # ── call model and stream ─────────────────────────────────────────────
        renderer.render_separator()
        renderer.render_assistant_label(self.cfg.model, tags=["📝周报"])

        weekly_messages = [
            {"role": "system", "content": "你是一名资深工程师，专门负责撰写简洁专业的技术周报。"},
            {"role": "user",   "content": prompt},
        ]
        stream_renderer = renderer.StreamRenderer()
        content = ""
        try:
            gen = self.agent.client.stream_chat(
                messages=weekly_messages,
                tools=None,
                search_enabled=False,
                mcp_servers=None,
            )
            try:
                while True:
                    chunk_type, chunk_text = next(gen)
                    if chunk_type != "reasoning":
                        stream_renderer.feed_content(chunk_text)
            except StopIteration as exc:
                result = exc.value
                stream_renderer.finish()
                content = result.content or ""
        except Exception as e:
            renderer.render_error(f"生成失败：{e}")
            return

        renderer.render_separator()

        if not content:
            renderer.render_error("生成失败，AI 没有返回内容。")
            return

        # ── write to file ──────────────────────────────────────────────────────
        out_path.write_text(content, encoding="utf-8")
        renderer.render_success(f"周报已保存到：{out_path}  ({len(content)} 字符)")

    def _cmd_tieba(self, arg: str) -> None:
        """Enter Tieba multi-agent plan mode."""
        from erniecli.tieba.personas import build_personas
        from erniecli.tieba.loop import TiebaSession
        try:
            personas = build_personas(self.cfg.tieba_personas or [])
            session = TiebaSession(self.agent.client, personas)
            session.run()
        except KeyboardInterrupt:
            renderer.render_info("\n已退出贴吧模式。")

    def _cmd_doctor(self, _: str) -> None:
        import importlib
        renderer.render_info("检查环境中…")

        checks: list[tuple[str, bool, str]] = []

        # API key
        checks.append(("ERNIE_API_KEY", bool(self.cfg.api_key), self.cfg.api_key[:8] + "…" if self.cfg.api_key else "未设置"))

        # connectivity
        try:
            import urllib.request
            urllib.request.urlopen("https://aistudio.baidu.com", timeout=5)
            checks.append(("网络连通性", True, "aistudio.baidu.com 可达"))
        except Exception as e:
            checks.append(("网络连通性", False, str(e)))

        # dependencies
        for pkg in ("openai", "rich", "prompt_toolkit", "yaml"):
            try:
                importlib.import_module(pkg)
                checks.append((f"依赖 {pkg}", True, "已安装"))
            except ImportError:
                checks.append((f"依赖 {pkg}", False, "未安装"))

        # config file
        from erniecli.config import _CONFIG_PATH
        checks.append(("配置文件", _CONFIG_PATH.exists(), str(_CONFIG_PATH)))

        t = Table(box=rbox.ROUNDED, show_header=False, border_style=BAIDU_BLUE)
        t.add_column("", style="bold")
        t.add_column("", width=6)
        t.add_column("")
        for name, ok, detail in checks:
            icon = f"[{BAIDU_GREEN}]✓[/{BAIDU_GREEN}]" if ok else f"[{BAIDU_RED}]✗[/{BAIDU_RED}]"
            t.add_row(name, icon, detail)
        self.console.print(t)


# ── module-level helpers ──────────────────────────────────────────────────────

# Keywords in file path / name → image use-case
_IMG_KIND_PATTERNS = [
    (["screenshot", "截图", "screen", "capture"],         "截图"),
    (["error", "err", "exception", "报错", "traceback"],  "报错截图"),
    (["ui", "design", "mockup", "界面", "原型", "设计"],  "UI设计图"),
    (["chart", "graph", "plot", "图表", "曲线", "折线"],  "图表"),
    (["diagram", "arch", "architecture", "架构"],         "架构图"),
    (["code", "src", "函数", "代码"],                     "代码截图"),
]


def _detect_image_kind(path: str) -> str:
    lower = path.lower()
    for keywords, kind in _IMG_KIND_PATTERNS:
        if any(k in lower for k in keywords):
            return kind
    return "通用图片"


def _grab_clipboard_image() -> str | None:
    """Try to save clipboard image to a temp file. Returns path or None."""
    import tempfile, subprocess as sp
    tmp = tempfile.mktemp(suffix=".png", prefix="ernie_clip_")
    for cmd in [
        f"xclip -selection clipboard -t image/png -o > {tmp}",
        f"xsel --clipboard --output > {tmp}",
    ]:
        try:
            r = sp.run(cmd, shell=True, capture_output=True, timeout=5)
            if r.returncode == 0 and Path(tmp).exists() and Path(tmp).stat().st_size > 0:
                return tmp
        except Exception:
            continue
    return None
