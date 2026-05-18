"""ErnieCLI entry point."""
import sys
import argparse
from importlib.metadata import version as _pkg_version, PackageNotFoundError
from erniecli.config import load_config
from erniecli.tui.logo import print_logo
from erniecli.repl import REPL

try:
    _VERSION = _pkg_version("erniecli")
except PackageNotFoundError:
    _VERSION = "dev"


def main():
    parser = argparse.ArgumentParser(
        prog="ernie",
        description="ErnieCLI — Agent CLI powered by Ernie 5.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ask", "-a", metavar="QUESTION", help="Single-shot question, then exit")
    parser.add_argument("--model", "-m", metavar="MODEL", help="Override model name")
    parser.add_argument("--search", action="store_true", help="Enable web search")
    parser.add_argument("--image", "-i", metavar="PATH", help="Attach image (use with --ask)")
    parser.add_argument("--version", action="version", version=f"ErnieCLI {_VERSION}")
    args = parser.parse_args()

    cfg = load_config()
    if args.model:
        cfg.model = args.model
    if args.search:
        cfg.search_enabled = True

    if args.ask:
        from erniecli.agent.loop import AgentLoop
        loop = AgentLoop(cfg)
        loop.run_single(args.ask, image_path=args.image)
    else:
        print_logo()
        repl = REPL(cfg)
        repl.run()


if __name__ == "__main__":
    main()
