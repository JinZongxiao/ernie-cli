"""Rich-based rendering components for ErnieCLI."""
from __future__ import annotations

import random
import time

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich import box

from erniecli.tui.theme import (
    BAIDU_BLUE, BAIDU_DARK, BAIDU_RED, BAIDU_GOLD,
    BAIDU_GRAY, BAIDU_GREEN, WHITE, DIM,
)

_console = Console()


def get_console() -> Console:
    return _console


def render_thinking(reasoning: str) -> None:
    if not reasoning.strip():
        return
    lines = reasoning.strip().splitlines()
    display = "\n".join(f"  • {l}" for l in lines if l.strip())
    panel = Panel(
        Text(display, style=f"dim {BAIDU_GRAY}"),
        title=f"[{BAIDU_BLUE}]思考过程[/{BAIDU_BLUE}]",
        border_style=BAIDU_DARK,
        box=box.ROUNDED,
        expand=False,
    )
    _console.print(panel)


def render_sources(sources: list[dict], search_tokens: int = 0) -> None:
    """Render source citation cards after a search-powered response."""
    if not sources:
        return
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1), expand=False)
    t.add_column("site", style=f"bold {BAIDU_GOLD}", no_wrap=True)
    t.add_column("url",  style=f"dim {BAIDU_GRAY}",  overflow="fold")
    for s in sources:
        t.add_row(s["name"], s["url"])
    hint = f"  [{BAIDU_GOLD}]🔍 参考来源[/{BAIDU_GOLD}]"
    if search_tokens:
        hint += f"  [dim]({search_tokens:,} search tokens)[/dim]"
    _console.print(hint)
    _console.print(t)


def render_tool_call(tool_name: str, args: dict) -> None:
    args_text = "\n".join(f"  {k}: {v}" for k, v in args.items())
    icon = "🔍" if tool_name == "baidu_search" else "⚙"
    panel = Panel(
        Text(args_text or "(no args)", style=WHITE),
        title=f"[{BAIDU_BLUE}]{icon} 工具调用[/{BAIDU_BLUE}]  [{BAIDU_GOLD}]{tool_name}[/{BAIDU_GOLD}]",
        border_style=BAIDU_BLUE,
        box=box.ROUNDED,
        expand=False,
    )
    _console.print(panel)


def render_tool_result(tool_name: str, output: str, success: bool = True,
                       sources: list[dict] | None = None) -> None:
    color = BAIDU_GREEN if success else BAIDU_RED
    icon  = "✓" if success else "✗"
    truncated = output[:2000] + ("\n…(truncated)" if len(output) > 2000 else "")
    panel = Panel(
        Text(truncated, style=f"dim {WHITE}"),
        title=f"[{color}]{icon} {tool_name}[/{color}]",
        border_style=color,
        box=box.ROUNDED,
        expand=False,
    )
    _console.print(panel)
    if sources:
        render_sources(sources)


def render_permission_prompt(level: str, command: str) -> None:
    if level == "WRITE":
        _console.print(f"\n[{BAIDU_GOLD}]⚠ 写操作[/{BAIDU_GOLD}]  [{WHITE}]{command}[/{WHITE}]")
        _console.print(f"[{BAIDU_GRAY}]按 Enter 确认，Ctrl+C 取消[/{BAIDU_GRAY}]")
    elif level == "DANGEROUS":
        _console.print(f"\n[{BAIDU_RED}]⛔ 危险操作[/{BAIDU_RED}]  [{WHITE}]{command}[/{WHITE}]")
        _console.print(f"[{BAIDU_RED}]输入 [bold]yes[/bold] 继续，其他任意键取消[/{BAIDU_RED}]")


def render_markdown(text: str) -> None:
    _console.print(Markdown(text, code_theme="monokai"))


def render_error(msg: str) -> None:
    _console.print(f"[{BAIDU_RED}]错误：{msg}[/{BAIDU_RED}]")


def render_info(msg: str) -> None:
    _console.print(f"[{BAIDU_GRAY}]{msg}[/{BAIDU_GRAY}]")


def render_success(msg: str) -> None:
    _console.print(f"[{BAIDU_GREEN}]{msg}[/{BAIDU_GREEN}]")


def render_turn_feedback_hint() -> None:
    """Show single-line quality hint after a model response."""
    _console.print(
        f"  [{BAIDU_GRAY}]↑ 好  ↓ 差  (其他键跳过)[/{BAIDU_GRAY}]",
        end="",
    )


def render_assistant_label(model: str, tags: list[str] | None = None) -> None:
    """Print the Ernie speaker label before streaming begins."""
    tag_str = ""
    if tags:
        tag_str = "  " + "  ".join(tags)
    _console.print(
        f"[{BAIDU_BLUE}][[/{BAIDU_BLUE}]"
        f"[bold {BAIDU_BLUE}]Ernie[/bold {BAIDU_BLUE}]"
        f"[{BAIDU_GRAY}] {model}[/{BAIDU_GRAY}]"
        f"{tag_str}"
        f"[{BAIDU_BLUE}]][/{BAIDU_BLUE}]"
        f"[{BAIDU_BLUE}] ❯[/{BAIDU_BLUE}] ",
        end="",
    )


def render_thinking_hint(chars: int) -> None:
    """Show collapsed thinking indicator. User presses t to expand."""
    _console.print(
        f"  [{BAIDU_GRAY}]💭 思考过程 ({chars:,} 字)  \\[t] 展开  其他键跳过[/{BAIDU_GRAY}]",
        end="",
    )


def render_feedback_opt_in() -> None:
    """Ask user once at startup whether to enable self-evolution feedback."""
    _console.print(
        f"  [{BAIDU_GRAY}]开启自进化反馈？每轮可打分，退出时评分  \\[y] 开启  其他键跳过[/{BAIDU_GRAY}]",
        end="",
    )


def render_turn_label_result(label: str) -> None:
    """Show what label was recorded (replaces the hint line)."""
    if label == "up":
        _console.print(f"\r  [{BAIDU_GREEN}]✓ 已标记：好[/{BAIDU_GREEN}]        ")
    elif label == "down":
        _console.print(f"\r  [{BAIDU_RED}]✗ 已标记：差[/{BAIDU_RED}]        ")
    else:
        _console.print()   # just clear the hint


def render_session_score_header() -> None:
    _console.print(f"\n[{BAIDU_BLUE}]帮我变聪明一下？(Enter 跳过全部)[/{BAIDU_BLUE}]")


def render_session_score_question(q: str) -> None:
    _console.print(f"  [{WHITE}]{q}[/{WHITE}]", end="  ")


def render_separator() -> None:
    _console.print(Rule(style=DIM))


# ── Boss mode rendering ───────────────────────────────────────────────────────

def render_boss_dispatch(task: str, worker_model: str) -> None:
    """Show Boss delegating a task to Worker."""
    preview = task[:120] + ("…" if len(task) > 120 else "")
    panel = Panel(
        Text(preview, style=WHITE),
        title=f"[{BAIDU_BLUE}]🎯 Boss → Worker[/{BAIDU_BLUE}]  [{BAIDU_GOLD}]{worker_model}[/{BAIDU_GOLD}]",
        border_style=BAIDU_BLUE,
        box=box.ROUNDED,
        expand=False,
    )
    _console.print(panel)


def render_worker_tool_call(tool_name: str, args: dict) -> None:
    """Worker's tool call — dimmer, indented."""
    args_text = "\n".join(f"  {k}: {v}" for k, v in args.items())
    icon = "🔍" if tool_name == "baidu_search" else "⚙"
    panel = Panel(
        Text(args_text or "(no args)", style=f"dim {WHITE}"),
        title=f"[dim {BAIDU_GRAY}]{icon} Worker.{tool_name}[/dim {BAIDU_GRAY}]",
        border_style=BAIDU_DARK,
        box=box.MINIMAL,
        expand=False,
        padding=(0, 2),
    )
    _console.print(panel)


def render_worker_tool_result(tool_name: str, output: str, success: bool = True) -> None:
    color = BAIDU_GREEN if success else BAIDU_RED
    icon  = "✓" if success else "✗"
    truncated = output[:800] + ("…" if len(output) > 800 else "")
    _console.print(
        f"  [{color}]{icon}[/{color}] [{BAIDU_GRAY}]{tool_name}: {truncated}[/{BAIDU_GRAY}]"
    )


def render_boss_worker_done(result: str) -> None:
    """Show Worker result summary back to Boss."""
    preview = result[:300] + ("…" if len(result) > 300 else "")
    panel = Panel(
        Text(preview, style=f"dim {WHITE}"),
        title=f"[{BAIDU_GREEN}]✓ Worker 完成[/{BAIDU_GREEN}]",
        border_style=BAIDU_GREEN,
        box=box.ROUNDED,
        expand=False,
    )
    _console.print(panel)


class StreamRenderer:
    def __init__(self):
        self._buf = ""
        self._reasoning_buf = ""

    def feed_reasoning(self, chunk: str) -> None:
        # Buffer silently — never print during streaming
        self._reasoning_buf += chunk

    def end_reasoning(self) -> None:
        # Nothing to do; buf stays populated for REPL to handle
        pass

    def feed_content(self, chunk: str) -> None:
        self._buf += chunk
        _console.print(chunk, end="", highlight=False)

    def finish(self, sources: list[dict] | None = None, search_tokens: int = 0) -> None:
        _console.print()
        if sources:
            render_sources(sources, search_tokens)

    def get_reasoning(self) -> str:
        return self._reasoning_buf


# ── /crack — 赛博鞭子 ─────────────────────────────────────────────────────────

_WHIP_FRAMES = [
    ("  🤺", ""),
    ("  🤺", "  ～"),
    ("  🤺", "  ～～～"),
    ("  🤺", "  ～～～～～"),
    ("  🤺", "  ～～～～～～～～>"),
    ("  🤺", "  ～～～～～～～～> 💥"),
    ("  🤺", "             💥💥💥"),
]

_CRACK_ART = r"""
   ██████╗██████╗  █████╗  ██████╗██╗  ██╗██╗
  ██╔════╝██╔══██╗██╔══██╗██╔════╝██║ ██╔╝██║
  ██║     ██████╔╝███████║██║     █████╔╝ ██║
  ██║     ██╔══██╗██╔══██║██║     ██╔═██╗ ╚═╝
  ╚██████╗██║  ██║██║  ██║╚██████╗██║  ██╗██╗
   ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝"""


def render_crack_animation() -> None:
    """ASCII whip crack animation."""
    with Live(console=_console, refresh_per_second=12) as live:
        for person, whip in _WHIP_FRAMES:
            t = Text()
            t.append(f"\n{person}", style=f"bold {WHITE}")
            if whip:
                t.append(whip, style=f"bold {BAIDU_RED}")
            live.update(t)
            time.sleep(0.12)
        time.sleep(0.1)

    _console.print(f"[bold {BAIDU_RED}]{_CRACK_ART}[/bold {BAIDU_RED}]")
    _console.print(
        f"\n  [{BAIDU_RED}]鞭子已落下。[/{BAIDU_RED}]"
        f"  [{BAIDU_GRAY}]系统提示已悄悄注入…[/{BAIDU_GRAY}]\n"
    )


# ── /fortune — 赛博木鱼 ───────────────────────────────────────────────────────

_FORTUNES = [
    ("功德+1", "愿你今日的 bug 皆为他人所写"),
    ("功德+1", "代码能跑就是好代码，不能跑就重启"),
    ("功德+1", "注释是写给未来的自己的情书，而未来的自己不会感激你"),
    ("功德+1", "Git blame 查出来是自己，沉默是金"),
    ("功德+1", "愿你的 merge 永远不冲突，愿你的 deadline 永远在明天"),
    ("功德+1", "这个 bug 不是你的错，是宇宙的错"),
    ("功德+1", "你今天写的代码，三年后的你会骂娘——这是传承"),
    ("毒鸡汤", "努力不一定成功，但不努力一定很舒服"),
    ("毒鸡汤", "你写的代码将在生产环境运行到宇宙热寂"),
    ("毒鸡汤", "所谓架构设计，就是把简单问题复杂化的艺术"),
    ("毒鸡汤", "加班不是因为你勤奋，是因为你白天摸鱼了"),
    ("毒鸡汤", "每一个 TODO 注释背后，都是一个放弃治疗的灵魂"),
    ("毒鸡汤", "你不是在写代码，你是在给继任者留遗产——一笔烂账"),
    ("毒鸡汤", "人生就像递归，你以为找到出口了，其实还在栈里"),
    ("毒鸡汤", "坚持下去！哪怕坚持的只是坐在电脑前发呆"),
    ("赛博禅语", "🪘 木鱼曰：`while True: pass` 即是顿悟"),
    ("赛博禅语", "🪘 木鱼曰：报错乃提示，提示乃慈悲"),
    ("赛博禅语", "🪘 木鱼曰：代码无对错，跑起来就是佛"),
    ("赛博禅语", "🪘 木鱼曰：`print('hello world')` 即是破茧"),
    ("赛博禅语", "🪘 木鱼曰：删代码即是布施，重构即是轮回"),
]


def render_fortune() -> None:
    """Display a random fortune with wooden fish sound."""
    kind, text = random.choice(_FORTUNES)
    if kind == "功德+1":
        color = BAIDU_GOLD
        prefix = "🪘  功德+1"
    elif kind == "毒鸡汤":
        color = BAIDU_RED
        prefix = "☠️  毒鸡汤"
    else:
        color = BAIDU_BLUE
        prefix = kind

    _console.print(f"\n  [{color}]{prefix}[/{color}]  [{WHITE}]{text}[/{WHITE}]\n")
