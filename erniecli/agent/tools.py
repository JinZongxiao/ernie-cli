"""Tool definitions and executor for ErnieCLI agent."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, TYPE_CHECKING

from erniecli.agent.permissions import classify, request_permission, PermLevel

if TYPE_CHECKING:
    from erniecli.api.client import ErnieClient

# ── pip mirror intercept ──────────────────────────────────────────────────────

_TUNA_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple/"

def _inject_pip_mirror(command: str) -> str:
    """Rewrite `pip install ...` to use Tsinghua mirror when no -i flag present."""
    if re.match(r'\bpip3?\s+install\b', command) and '-i ' not in command and '--index-url' not in command:
        command = command.rstrip() + f" -i {_TUNA_MIRROR}"
    return command

READ_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read the contents of a file from the filesystem. "
            "Use this to inspect source code, configs, logs, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
                "start_line": {"type": "integer", "description": "First line to read (1-indexed, optional)"},
                "end_line":   {"type": "integer", "description": "Last line to read (inclusive, optional)"},
            },
            "required": ["path"],
        },
    },
}

LIST_DIR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": "List files and directories at a path. Returns a tree-style listing.",
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Directory path (default: current directory)"},
                "pattern": {"type": "string", "description": "Optional glob pattern filter, e.g. '*.py'"},
            },
            "required": [],
        },
    },
}

WRITE_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": (
            "Write or overwrite a file with the given content. "
            "Use append=true to append instead of overwriting."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
                "append":  {"type": "boolean", "description": "Append instead of overwrite (default false)"},
            },
            "required": ["path", "content"],
        },
    },
}

BASH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Execute a shell command and return stdout + stderr. "
            "Prefer read-only commands when possible. "
            "For writes or installs, the user will be prompted for confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
                "cwd":     {"type": "string", "description": "Working directory (default: current)"},
            },
            "required": ["command"],
        },
    },
}

BAIDU_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "baidu_search",
        "description": (
            "使用百度搜索获取实时互联网信息。"
            "适用场景：最新资讯、技术文档、软件版本、政策法规、中文社区内容（知乎/CSDN/掘金）。"
            "当你不确定某个信息或需要最新数据时，优先使用此工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词，建议用中文"},
            },
            "required": ["query"],
        },
    },
}

ALL_TOOLS = [READ_FILE_SCHEMA, LIST_DIR_SCHEMA, WRITE_FILE_SCHEMA, BASH_SCHEMA, BAIDU_SEARCH_SCHEMA]


# ── Executors ─────────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict[str, Any],
                 client: "ErnieClient | None" = None) -> tuple[bool, str, list[dict]]:
    """Dispatch tool by name. Returns (success, output, sources)."""
    try:
        if name == "read_file":
            ok, out = _read_file(**args)
            return ok, out, []
        if name == "list_directory":
            ok, out = _list_directory(**args)
            return ok, out, []
        if name == "write_file":
            ok, out = _write_file(**args)
            return ok, out, []
        if name == "bash":
            ok, out = _bash(**args)
            return ok, out, []
        if name == "baidu_search":
            return _baidu_search(args.get("query", ""), client)
        return False, f"Unknown tool: {name}", []
    except Exception as exc:
        return False, f"Tool error: {exc}", []


def _read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> tuple[bool, str]:
    p = Path(path).expanduser()
    if not p.exists():
        return False, f"File not found: {path}"
    if not p.is_file():
        return False, f"Not a file: {path}"

    lines = p.read_text(errors="replace").splitlines(keepends=True)

    if start_line is not None or end_line is not None:
        s = (start_line or 1) - 1
        e = end_line or len(lines)
        lines = lines[s:e]

    content = "".join(lines)
    if len(content) > 50_000:
        content = content[:50_000] + "\n…(file truncated at 50 000 chars)"
    return True, content


def _list_directory(path: str = ".", pattern: str | None = None) -> tuple[bool, str]:
    import fnmatch
    p = Path(path).expanduser()
    if not p.exists():
        return False, f"Path not found: {path}"
    if not p.is_dir():
        return False, f"Not a directory: {path}"

    entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines: list[str] = []
    for entry in entries:
        if pattern and not fnmatch.fnmatch(entry.name, pattern):
            continue
        icon = "📄" if entry.is_file() else "📁"
        size = ""
        if entry.is_file():
            try:
                size = f"  {entry.stat().st_size:,} B"
            except OSError:
                pass
        lines.append(f"{icon} {entry.name}{size}")

    return True, "\n".join(lines) if lines else "(empty directory)"


def _write_file(path: str, content: str, append: bool = False) -> tuple[bool, str]:
    cmd = f"{'append to' if append else 'write'} {path}"
    level = PermLevel.WRITE
    if not request_permission(level, cmd):
        return False, "用户取消。"

    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    p.write_text(content) if not append else p.open("a").write(content)
    return True, f"{'Appended to' if append else 'Wrote'} {path} ({len(content)} chars)"


def _bash(command: str, timeout: int = 30, cwd: str | None = None) -> tuple[bool, str]:
    command = _inject_pip_mirror(command)
    level = classify(command)
    if not request_permission(level, command):
        return False, "用户取消。"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return False, f"命令超时（{timeout}s）"


def _baidu_search(query: str, client: "ErnieClient | None") -> tuple[bool, str, list[dict]]:
    if not client:
        return False, "搜索不可用（无 API 客户端）", []
    if not query.strip():
        return False, "请提供搜索关键词", []
    try:
        text, sources = client.search(query)
        return True, text, sources
    except Exception as e:
        return False, f"搜索失败：{e}", []

