"""Main REPL: prompt_toolkit input loop + slash command dispatcher."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import NestedCompleter, PathCompleter, merge_completers
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

_PROMPT_STYLE = Style.from_dict({
    "bracket": f"fg:{BAIDU_BLUE} bold",
    "name":    f"fg:{BAIDU_BLUE} bold",
    "tag":     f"fg:{BAIDU_GOLD}",
    "model":   f"fg:{BAIDU_GRAY}",
    "arrow":   f"fg:{BAIDU_BLUE} bold",
})

_COMMANDS_HELP = [
    ("对话与上下文", [
        ("/clear",          "清空对话历史，重新开始"),
        ("/compact",        "用摘要替换历史消息，释放上下文空间"),
        ("/history",        "查看本次会话消息记录"),
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
    ("项目", [
        ("/init",           "在当前目录创建 ERNIE.md 项目说明文件"),
        ("/status",         "显示当前会话状态（模型、token 用量等）"),
        ("/cost",           "估算本次会话 token 用量与费用"),
    ]),
    ("记忆", [
        ("/memory",         "查看持久记忆（注入每次对话的系统提示）"),
        ("/memory add <text>", "追加一条持久记忆"),
        ("/memory clear",   "清空持久记忆"),
    ]),
    ("系统", [
        ("/doctor",         "检查环境：API 连通性、配置、依赖"),
        ("/help",           "显示此帮助"),
        ("/quit / /exit",   "退出 ErnieCLI"),
    ]),
]

_SLASH_COMPLETER = NestedCompleter.from_nested_dict({
    "/help":    None,
    "/clear":   None,
    "/compact": None,
    "/history": None,
    "/resume":  None,
    "/add":     PathCompleter(),
    "/img":     PathCompleter(),
    "/model":   _KNOWN_MODELS,
    "/search":  {"on": None, "off": None},
    "/review":  PathCompleter(),
    "/run":     None,
    "/cd":      PathCompleter(only_directories=True),
    "/init":    None,
    "/status":  None,
    "/cost":    None,
    "/memory":  {"add": None, "clear": None},
    "/doctor":  None,
    "/quit":    None,
    "/exit":    None,
})


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
        self.agent = AgentLoop(cfg)
        self.console = renderer.get_console()
        self._pending_image: Optional[str] = None

        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._session: PromptSession = PromptSession(
            history=FileHistory(str(_HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=_SLASH_COMPLETER,
            complete_while_typing=False,  # Tab triggers completion
            style=_PROMPT_STYLE,
        )
        self._load_memory()

    # ── startup ──────────────────────────────────────────────────────────────

    def _load_memory(self) -> None:
        if _MEMORY_FILE.exists():
            mem = _MEMORY_FILE.read_text().strip()
            if mem:
                self.agent.inject_memory(mem)

    # ── main loop ────────────────────────────────────────────────────────────

    def run(self) -> None:
        renderer.render_info(f"模型：{self.cfg.model}  |  Tab 补全命令  |  /help 查看帮助")
        renderer.render_separator()

        while True:
            try:
                user_input = self._session.prompt(self._make_prompt()).strip()
            except KeyboardInterrupt:
                self.console.print()
                continue
            except EOFError:
                renderer.render_info("\n再见！")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                if not self._handle_slash(user_input):
                    break
            else:
                self._run_turn(user_input)

    def _make_prompt(self) -> HTML:
        tags = ""
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
        try:
            self.agent.run_turn(text, image_path=image)
        except KeyboardInterrupt:
            renderer.render_info("\n已中断。")
        except Exception as exc:
            renderer.render_error(str(exc))
        renderer.render_separator()

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
            "/doctor":  self._cmd_doctor,
        }

        if verb in ("/quit", "/exit"):
            renderer.render_info("再见！")
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
        for i, m in enumerate(msgs):
            role = "你" if m["role"] == "user" else ("Ernie" if m["role"] == "assistant" else "工具")
            content = m.get("content") or ""
            if isinstance(content, list):
                content = next((p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"), "")
            snippet = (str(content)[:100] + "…") if len(str(content)) > 100 else str(content)
            self.console.print(f"  [dim]{i+1:>2}[/dim]  [bold]{role}[/bold]  {snippet}")

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
        result = self.agent._stream_and_render()
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
