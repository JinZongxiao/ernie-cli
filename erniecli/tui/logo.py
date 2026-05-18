"""Startup banner for ErnieCLI."""
from rich.console import Console
from rich.text import Text
from rich.align import Align
from erniecli.tui.theme import BAIDU_BLUE, BAIDU_GRAY, BAIDU_GOLD

_ERNIE_LINES = [
    "███████╗██████╗ ███╗  ██╗██╗███████╗",
    "██╔════╝██╔══██╗████╗ ██║██║██╔════╝",
    "█████╗  ██████╔╝██╔██╗██║██║█████╗  ",
    "██╔══╝  ██╔══██╗██║╚████║██║██╔══╝  ",
    "███████╗██║  ██║██║ ╚███║██║███████╗",
    "╚══════╝╚═╝  ╚═╝╚═╝  ╚══╝╚═╝╚══════╝",
]

_SUBTITLE = "github.com/JinZongxiao/ernie-cli"
_HINT     = "/help 查看命令  ·  Ctrl+C 退出"


def print_logo(console: Console | None = None) -> None:
    if console is None:
        console = Console()

    t = Text()
    for line in _ERNIE_LINES:
        t.append(line + "\n", style=f"bold {BAIDU_BLUE}")
    t.append(_SUBTITLE + "\n", style=BAIDU_GOLD)
    t.append(_HINT + "\n",     style=f"dim {BAIDU_GRAY}")

    console.print()
    console.print(Align.center(t))
    console.print()
