"""Three-tier permission system for tool execution."""
from __future__ import annotations

import re
import sys
from enum import Enum

from erniecli.tui import renderer


class PermLevel(str, Enum):
    SAFE      = "SAFE"
    WRITE     = "WRITE"
    DANGEROUS = "DANGEROUS"


# Commands that are always read-only / side-effect-free
_SAFE_CMDS = {
    "ls", "ll", "la", "cat", "less", "more", "head", "tail",
    "grep", "rg", "find", "locate", "which", "whereis",
    "echo", "printf", "wc", "sort", "uniq", "diff", "file",
    "pwd", "whoami", "id", "uname", "hostname", "date",
    "env", "printenv", "ps", "top", "htop", "df", "du",
    "git", "python", "python3", "pip", "pip3",  # git reads by default; refined below
    "jq", "awk", "sed",  # refined below for writes
    "curl", "wget",  # refined below for writes
}

# Patterns that escalate a SAFE command to WRITE or DANGEROUS
_DANGEROUS_PATTERNS = [
    r"\brm\b",
    r"\bsudo\b",
    r"\bchmod\s+(777|[0-7]*[2-7][0-7]{2})",
    r"\bchown\b",
    r"\bdd\b",
    r"\bmkfs\b",
    r"\bshred\b",
    r"\bformat\b",
    r"curl\s+.*\|\s*(ba)?sh",
    r"wget\s+.*\|\s*(ba)?sh",
    r">\s*/etc/",
    r">\s*/usr/",
    r">\s*/bin/",
    r";\s*rm\b",
    r"&&\s*rm\b",
    r"\beval\b",
    r"\bexec\b",
    r":.*:\{.*:\}",  # fork bomb pattern
]

_WRITE_PATTERNS = [
    r"\brm\b(?!.*-r)",                    # rm without -r
    r"\bmkdir\b",
    r"\btouch\b",
    r"\bcp\b",
    r"\bmv\b",
    r"\bpip\s+install\b",
    r"\bapt(-get)?\s+install\b",
    r"\byum\s+install\b",
    r"\bgit\s+(add|commit|push|reset|rebase|merge|tag|branch\s+-[dD])\b",
    r"\bsed\s+.*-i\b",
    r"\bawk\s+.*>\s*\S",
    r">\s*\S",       # output redirect (write)
    r">>\s*\S",      # output redirect (append — write tier)
    r"\bwrite_file\b",
]

_DANGEROUS_RE = [re.compile(p) for p in _DANGEROUS_PATTERNS]
_WRITE_RE     = [re.compile(p) for p in _WRITE_PATTERNS]


def classify(command: str) -> PermLevel:
    for pat in _DANGEROUS_RE:
        if pat.search(command):
            return PermLevel.DANGEROUS
    for pat in _WRITE_RE:
        if pat.search(command):
            return PermLevel.WRITE
    return PermLevel.SAFE


def request_permission(level: PermLevel, command: str) -> bool:
    """Display prompt and return True if user approves execution."""
    if level == PermLevel.SAFE:
        renderer.render_info(f"  ✓ 执行: {command}")
        return True

    if level == PermLevel.WRITE:
        renderer.render_permission_prompt("WRITE", command)
        try:
            ans = input()
            return True  # any Enter = confirm; Ctrl+C raises KeyboardInterrupt
        except (KeyboardInterrupt, EOFError):
            renderer.render_info("已取消。")
            return False

    # DANGEROUS
    renderer.render_permission_prompt("DANGEROUS", command)
    try:
        ans = input().strip().lower()
        return ans == "yes"
    except (KeyboardInterrupt, EOFError):
        renderer.render_info("已取消。")
        return False
