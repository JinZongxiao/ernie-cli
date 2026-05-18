"""Rich TUI rendering for Tieba plan mode."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich import box

from erniecli.tui.renderer import get_console
from erniecli.tui.theme import BAIDU_GRAY, BAIDU_GREEN, WHITE, DIM

_TERMINATOR_COLOR = "#FFD700"
_USER_COLOR        = "#E0E0E0"


def _con() -> Console:
    return get_console()


# ── Welcome banner ────────────────────────────────────────────────────────────

def render_tieba_welcome() -> None:
    """Shown once when entering Tieba mode."""
    c = _con()
    c.print()
    body = Text()
    body.append("📮  ErnieCLI 技术吧\n", style=f"bold {BAIDU_GREEN}")
    body.append("你是楼主，先开口，吧友才会冒出来。\n\n", style=WHITE)
    body.append(
        "🦅鹰眼·架构  🐲龙场·理论  🤡翻译官·类比  🐟摸鱼·气氛  💀老PTSD·血泪\n",
        style=f"dim {BAIDU_GRAY}",
    )
    body.append(
        "@角色名 指定发言  /done 结束 & 生成方案",
        style=f"dim {BAIDU_GRAY}",
    )
    c.print(Panel(
        body,
        box=box.DOUBLE_EDGE,
        border_style=BAIDU_GREEN,
        expand=False,
        padding=(0, 2),
    ))
    c.print()


# ── User post ─────────────────────────────────────────────────────────────────

def render_tieba_user_post(floor: int, content: str) -> None:
    _con().print(Panel(
        Text(content, style=WHITE),
        title=f"[bold {_USER_COLOR}]👤 楼主[/bold {_USER_COLOR}]  [dim]{floor}楼[/dim]",
        border_style=_USER_COLOR,
        box=box.ROUNDED,
        expand=False,
        padding=(0, 1),
    ))


# ── Persona post (streaming) ──────────────────────────────────────────────────

def render_tieba_streaming_header(persona, floor: int) -> None:
    """One-line header printed before streaming the persona's reply."""
    _con().print(
        f"\n[bold {persona.color}]{persona.emoji} {persona.name}[/bold {persona.color}]"
        f"  [dim]{floor}楼[/dim]  "
        f"[dim {BAIDU_GRAY}]{'─' * 38}[/dim {BAIDU_GRAY}]"
    )


def render_tieba_post_footer() -> None:
    _con().print(Rule(style=DIM))


# ── Terminator ────────────────────────────────────────────────────────────────

def render_tieba_terminator_header() -> None:
    c = _con()
    c.print()
    c.print(Rule(
        title=f"[bold {_TERMINATOR_COLOR}]⚡ 终结者 · 分析楼主需求[/bold {_TERMINATOR_COLOR}]",
        style=_TERMINATOR_COLOR,
    ))
    c.print()


def render_tieba_terminator_refine_header() -> None:
    c = _con()
    c.print()
    c.print(Rule(
        title=f"[bold {_TERMINATOR_COLOR}]⚡ 终结者 · 结合讨论修正方案[/bold {_TERMINATOR_COLOR}]",
        style=_TERMINATOR_COLOR,
    ))
    c.print()


def render_tieba_terminator_saved(path: str) -> None:
    _con().print(f"\n[{BAIDU_GREEN}]✓ 方案已保存：{path}[/{BAIDU_GREEN}]\n")


# ── Input ─────────────────────────────────────────────────────────────────────

def render_tieba_input_hint() -> None:
    _con().print(
        f"\n  [dim {BAIDU_GRAY}]"
        f"↩ 发言  @角色名 指定发言人  /done 结束讨论"
        f"[/dim {BAIDU_GRAY}]"
    )


def render_tieba_input_prompt(floor: int, personas: dict | None = None) -> str:
    """Print the prompt and return user input.

    If *personas* is provided, enables Tab-completion for @mention names.
    Uses prompt_toolkit when available (already a project dependency).
    """
    prompt_str = f"👤 楼主  {floor}楼 ❯ "

    if personas:
        try:
            from prompt_toolkit import prompt as _pt_prompt
            from prompt_toolkit.completion import Completer, Completion
            from prompt_toolkit.styles import Style

            _names: list[str] = []
            for p in personas.values():
                _names.append(p.name)
                _names.append(p.key)

            class _AtCompleter(Completer):
                def get_completions(self, document, complete_event):
                    text = document.text_before_cursor
                    at_pos = text.rfind("@")
                    if at_pos == -1:
                        return
                    after_at = text[at_pos + 1 :]
                    for name in _names:
                        if name.startswith(after_at):
                            yield Completion(name, start_position=-len(after_at))

            _style = Style.from_dict({"": f"{_USER_COLOR} bold"})
            try:
                _con().print()   # blank line before prompt for breathing room
                return _pt_prompt(prompt_str, completer=_AtCompleter(),
                                  complete_while_typing=True, style=_style)
            except (KeyboardInterrupt, EOFError):
                return "/done"
        except ImportError:
            pass

    # Fallback: plain input()
    _con().print(
        f"[bold {_USER_COLOR}]👤 楼主[/bold {_USER_COLOR}]"
        f"[dim]  {floor}楼[/dim]"
        f"[bold {_USER_COLOR}] ❯[/bold {_USER_COLOR}] ",
        end="",
    )
    try:
        return input()
    except (KeyboardInterrupt, EOFError):
        return "/done"


# ── Misc ──────────────────────────────────────────────────────────────────────

def render_tieba_dry_warning() -> None:
    _con().print(
        f"  [dim {BAIDU_GRAY}]（🐟 没啥干货，摸鱼队长忍不住了）[/dim {BAIDU_GRAY}]"
    )


def render_tieba_info(msg: str) -> None:
    _con().print(f"[dim {BAIDU_GRAY}]{msg}[/dim {BAIDU_GRAY}]")
