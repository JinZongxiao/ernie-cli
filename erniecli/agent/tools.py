"""Tool definitions and executor for ErnieCLI agent."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
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


# ── Tool schemas ──────────────────────────────────────────────────────────────

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

GREP_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "grep_search",
        "description": (
            "在文件或目录中搜索文本/正则表达式，返回匹配行和行号。"
            "适合在代码库中定位函数定义、变量引用、错误信息等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern":     {"type": "string",  "description": "搜索关键词或正则表达式"},
                "path":        {"type": "string",  "description": "搜索路径（文件或目录，默认当前目录）"},
                "glob":        {"type": "string",  "description": "文件名过滤，如 '*.py'、'*.ts'"},
                "ignore_case": {"type": "boolean", "description": "忽略大小写（默认 false）"},
                "max_results": {"type": "integer", "description": "最多返回条数（默认 50）"},
            },
            "required": ["pattern"],
        },
    },
}

EDIT_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": (
            "精准替换文件中的某段内容。"
            "old_string 必须在文件中存在且唯一，否则报错。"
            "比 write_file 更安全，只改需要改的部分。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":        {"type": "string",  "description": "文件路径"},
                "old_string":  {"type": "string",  "description": "要替换的原始文本（需唯一）"},
                "new_string":  {"type": "string",  "description": "替换后的新文本"},
                "replace_all": {"type": "boolean", "description": "替换所有匹配（默认只替换第一个）"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
}

GLOB_SCHEMA = {
    "type": "function",
    "function": {
        "name": "glob",
        "description": (
            "按 glob pattern 查找文件，如 '**/*.py'、'src/**/*.ts'。"
            "返回匹配的文件路径列表，按修改时间倒序排列。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern":     {"type": "string",  "description": "glob pattern，如 '**/*.py'"},
                "path":        {"type": "string",  "description": "搜索根目录（默认当前目录）"},
                "max_results": {"type": "integer", "description": "最多返回条数（默认 100）"},
            },
            "required": ["pattern"],
        },
    },
}

HTTP_REQUEST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "http_request",
        "description": (
            "发送 HTTP 请求，支持 GET/POST。"
            "适合调用 REST API、抓取网页内容、测试接口。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url":     {"type": "string", "description": "请求 URL"},
                "method":  {"type": "string", "description": "HTTP 方法：GET 或 POST（默认 GET）"},
                "headers": {"type": "object", "description": "请求头（可选）"},
                "body":    {"type": "string", "description": "请求体（POST 时使用，可选）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 15）"},
            },
            "required": ["url"],
        },
    },
}

PYTHON_REPL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "python_repl",
        "description": (
            "直接执行 Python 代码片段，返回 stdout/stderr 输出。"
            "适合快速计算、数据处理、测试逻辑、不想写文件的场景。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code":    {"type": "string",  "description": "要执行的 Python 代码"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 30）"},
            },
            "required": ["code"],
        },
    },
}

IMAGE_VIEW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "image_view",
        "description": (
            "读取图片文件并转为 base64，供模型分析图片内容。"
            "支持 jpg/png/gif/webp/bmp 格式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "图片文件路径"},
            },
            "required": ["path"],
        },
    },
}

NOTEBOOK_EXEC_SCHEMA = {
    "type": "function",
    "function": {
        "name": "notebook_exec",
        "description": (
            "执行 Jupyter notebook (.ipynb) 或直接运行 Python 代码并返回 cell 输出。"
            "path 和 code 二选一：path 执行整个 notebook，code 创建临时 notebook 执行。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string",  "description": ".ipynb 文件路径（执行整个 notebook）"},
                "code":    {"type": "string",  "description": "直接执行的 Python 代码（创建临时 notebook）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 60）"},
            },
            "required": [],
        },
    },
}

ALL_TOOLS = [
    READ_FILE_SCHEMA,
    LIST_DIR_SCHEMA,
    WRITE_FILE_SCHEMA,
    EDIT_FILE_SCHEMA,
    BASH_SCHEMA,
    GREP_SEARCH_SCHEMA,
    GLOB_SCHEMA,
    HTTP_REQUEST_SCHEMA,
    PYTHON_REPL_SCHEMA,
    # IMAGE_VIEW_SCHEMA — 已移除：marker 尚未转换为真正的 multimodal message
    NOTEBOOK_EXEC_SCHEMA,
    BAIDU_SEARCH_SCHEMA,
]


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
        if name == "edit_file":
            ok, out = _edit_file(**args)
            return ok, out, []
        if name == "bash":
            ok, out = _bash(**args)
            return ok, out, []
        if name == "grep_search":
            ok, out = _grep_search(**args)
            return ok, out, []
        if name == "glob":
            ok, out = _glob(**args)
            return ok, out, []
        if name == "http_request":
            ok, out = _http_request(**args)
            return ok, out, []
        if name == "python_repl":
            ok, out = _python_repl(**args)
            return ok, out, []
        if name == "image_view":
            ok, out = _image_view(**args)
            return ok, out, []
        if name == "notebook_exec":
            ok, out = _notebook_exec(**args)
            return ok, out, []
        if name == "baidu_search":
            return _baidu_search(args.get("query", ""), client)
        return False, f"Unknown tool: {name}", []
    except Exception as exc:
        return False, f"Tool error: {exc}", []


# ── Diff helper ───────────────────────────────────────────────────────────────

def _show_diff(old: str, new: str, path: str) -> None:
    """Render a unified diff to the terminal via Rich."""
    import difflib
    from rich.syntax import Syntax
    from erniecli.tui.renderer import get_console

    diff_lines = list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    ))
    if not diff_lines:
        return
    # cap to avoid flooding the terminal
    MAX_DIFF_LINES = 60
    truncated = len(diff_lines) > MAX_DIFF_LINES
    shown = diff_lines[:MAX_DIFF_LINES]
    diff_text = "".join(shown)
    if truncated:
        diff_text += f"\n… ({len(diff_lines) - MAX_DIFF_LINES} lines omitted)"

    con = get_console()
    con.print()
    con.print(Syntax(diff_text, "diff", theme="monokai", line_numbers=False))
    con.print()


# ── Implementations ───────────────────────────────────────────────────────────

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
    p = Path(path).expanduser()
    mode_label = "追加" if append else "写入"

    # ── diff preview ─────────────────────────────────────────────────────────
    if not append and p.exists():
        old = p.read_text(errors="replace")
        _show_diff(old, content, path)
    else:
        from erniecli.tui import renderer as _r
        preview = content[:300] + ("…" if len(content) > 300 else "")
        _r.render_info(f"新建文件 {path}，内容预览：\n{preview}")

    if not request_permission(PermLevel.WRITE, f"{mode_label} {path}"):
        return False, "用户取消。"

    p.parent.mkdir(parents=True, exist_ok=True)
    if append:
        with p.open("a") as f:
            f.write(content)
    else:
        p.write_text(content)
    return True, f"{'Appended to' if append else 'Wrote'} {path} ({len(content)} chars)"


def _edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> tuple[bool, str]:
    p = Path(path).expanduser()
    if not p.exists():
        return False, f"文件不存在：{path}"

    content = p.read_text(errors="replace")
    count = content.count(old_string)

    if count == 0:
        return False, "未找到 old_string，请检查内容是否完全匹配（包括空格和换行）"
    if count > 1 and not replace_all:
        return False, f"old_string 在文件中出现了 {count} 次，请提供更多上下文使其唯一，或设置 replace_all=true"

    # ── diff preview ─────────────────────────────────────────────────────────
    new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    _show_diff(content, new_content, path)

    if not request_permission(PermLevel.WRITE, f"edit {path}"):
        return False, "用户取消。"

    p.write_text(new_content)
    replaced = count if replace_all else 1
    return True, f"已替换 {replaced} 处，文件已保存：{path}"


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


def _grep_search(
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    ignore_case: bool = False,
    max_results: int = 50,
) -> tuple[bool, str]:
    import fnmatch as _fnmatch

    root = Path(path).expanduser()
    flags = re.IGNORECASE if ignore_case else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return False, f"正则表达式错误：{e}"

    if root.is_file():
        files = [root]
    else:
        files = [f for f in root.rglob("*") if f.is_file()]
        if glob:
            files = [f for f in files if _fnmatch.fnmatch(f.name, glob)]

    results: list[str] = []
    for filepath in sorted(files):
        try:
            lines = filepath.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                results.append(f"{filepath}:{i}: {line.rstrip()}")
                if len(results) >= max_results:
                    break
        if len(results) >= max_results:
            break

    if not results:
        return True, "(无匹配结果)"
    suffix = f"\n…(仅显示前 {max_results} 条)" if len(results) == max_results else ""
    return True, "\n".join(results) + suffix


def _glob(pattern: str, path: str = ".", max_results: int = 100) -> tuple[bool, str]:
    root = Path(path).expanduser()
    if not root.exists():
        return False, f"路径不存在：{path}"

    matches = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    matches = matches[:max_results]

    if not matches:
        return True, "(无匹配文件)"

    lines = []
    for m in matches:
        try:
            rel = m.relative_to(root)
        except ValueError:
            rel = m
        lines.append(str(rel))

    suffix = f"\n…(仅显示前 {max_results} 条)" if len(matches) == max_results else ""
    return True, "\n".join(lines) + suffix


def _http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
    timeout: int = 15,
) -> tuple[bool, str]:
    import urllib.request
    import urllib.error
    import urllib.parse

    method = method.upper()

    # ── permission classification ─────────────────────────────────────────────
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    _PRIVATE = re.compile(
        r"^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0"
        r"|10\.\d+\.\d+\.\d+"
        r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+"
        r"|192\.168\.\d+\.\d+)$"
    )
    is_private = bool(_PRIVATE.match(host))
    is_mutating = method in ("POST", "PUT", "PATCH", "DELETE")

    if is_private:
        level = PermLevel.DANGEROUS
    elif is_mutating:
        level = PermLevel.WRITE
    else:
        level = PermLevel.WRITE   # GET to public URL still needs one confirm

    label = f"{method} {url}" + (" [内网地址！]" if is_private else "")
    if not request_permission(level, label):
        return False, "用户取消。"

    data = body.encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", "ErnieCLI/1.5")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            if len(text) > 10_000:
                text = text[:10_000] + "\n…(truncated)"
            return True, f"HTTP {resp.status}\n{text}"
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:2000]
        return False, f"HTTP {e.code} {e.reason}\n{body_text}"
    except Exception as e:
        return False, f"请求失败：{e}"


def _python_repl(code: str, timeout: int = 30) -> tuple[bool, str]:
    preview = code[:80].replace("\n", "↵")
    if not request_permission(PermLevel.WRITE, f"python -c '{preview}...'"):
        return False, "用户取消。"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name

    try:
        result = subprocess.run(
            ["python3", tmp],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip() or "(no output)"
    except FileNotFoundError:
        # fallback to python
        try:
            result = subprocess.run(
                ["python", tmp],
                capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout + result.stderr
            return result.returncode == 0, output.strip() or "(no output)"
        except Exception as e:
            return False, f"执行失败：{e}"
    except subprocess.TimeoutExpired:
        return False, f"执行超时（{timeout}s）"
    finally:
        Path(tmp).unlink(missing_ok=True)


def _image_view(path: str) -> tuple[bool, str]:
    import base64
    import mimetypes

    p = Path(path).expanduser()
    if not p.exists():
        return False, f"文件不存在：{path}"

    mime, _ = mimetypes.guess_type(str(p))
    if not mime or not mime.startswith("image/"):
        return False, f"不是图片文件（mime={mime}）：{path}"

    data = p.read_bytes()
    b64 = base64.b64encode(data).decode()
    size = p.stat().st_size

    # Return a marker that agent loop can detect for multimodal injection
    return True, f"__IMAGE_B64__{mime}::{b64}__END_IMAGE__\n文件：{path} | 大小：{size:,} B | 格式：{mime}"


def _notebook_exec(
    path: str | None = None,
    code: str | None = None,
    timeout: int = 60,
) -> tuple[bool, str]:
    import json

    if not path and not code:
        return False, "需要提供 path 或 code 参数"

    cleanup = False
    if code and not path:
        nb = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python"},
            },
            "cells": [{
                "cell_type": "code",
                "source": code,
                "metadata": {},
                "outputs": [],
                "execution_count": None,
            }],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False, encoding="utf-8") as f:
            json.dump(nb, f)
            path = f.name
        cleanup = True
    else:
        if not Path(path).exists():
            return False, f"文件不存在：{path}"

    if not request_permission(PermLevel.WRITE, f"jupyter nbconvert --execute {path}"):
        if cleanup:
            Path(path).unlink(missing_ok=True)
        return False, "用户取消。"

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "output.ipynb"
            result = subprocess.run(
                ["jupyter", "nbconvert", "--to", "notebook", "--execute",
                 "--ExecutePreprocessor.timeout=" + str(timeout),
                 "--output", str(out_path), path],
                capture_output=True,
                text=True,
                timeout=timeout + 10,
            )

            if result.returncode != 0:
                return False, f"执行失败：\n{result.stderr[:2000]}"

            nb_out = json.loads(out_path.read_text())
            outputs: list[str] = []
            for cell in nb_out.get("cells", []):
                for out in cell.get("outputs", []):
                    otype = out.get("output_type", "")
                    if otype == "stream":
                        outputs.append("".join(out.get("text", [])))
                    elif otype in ("execute_result", "display_data"):
                        txt = out.get("data", {}).get("text/plain", "")
                        if txt:
                            outputs.append(txt if isinstance(txt, str) else "".join(txt))
                    elif otype == "error":
                        outputs.append(f"ERROR {out.get('ename')}: {out.get('evalue')}\n" +
                                       "".join(out.get("traceback", [])))

            return True, "\n".join(outputs).strip() or "(无输出)"

    except FileNotFoundError:
        return False, "未找到 jupyter 命令，请先安装：pip install jupyter"
    except subprocess.TimeoutExpired:
        return False, f"执行超时（{timeout}s）"
    finally:
        if cleanup:
            Path(path).unlink(missing_ok=True)


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
