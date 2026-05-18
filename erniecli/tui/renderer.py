"""Rich-based rendering components for ErnieCLI."""
from __future__ import annotations

from rich.console import Console
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
        self._reasoning_buf += chunk
        _console.print(chunk, end="", style=f"dim {BAIDU_GRAY}", highlight=False)

    def end_reasoning(self) -> None:
        if self._reasoning_buf:
            _console.print()
            render_thinking(self._reasoning_buf)
            self._reasoning_buf = ""

    def feed_content(self, chunk: str) -> None:
        self._buf += chunk
        _console.print(chunk, end="", highlight=False)

    def finish(self, sources: list[dict] | None = None, search_tokens: int = 0) -> None:
        _console.print()
        if sources:
            render_sources(sources, search_tokens)
