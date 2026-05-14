"""Core agentic loop: stream → tool calls → execute → feed back → repeat."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Optional

_SESSIONS_DIR = Path.home() / ".ernie" / "sessions"


def _session_path(cwd: str) -> Path:
    key = hashlib.sha1(cwd.encode()).hexdigest()[:16]
    return _SESSIONS_DIR / f"{key}.json"

from erniecli.api.client import ErnieClient, StreamResult
from erniecli.agent.tools import ALL_TOOLS, execute_tool
from erniecli.config import Config
from erniecli.tui import renderer

_SYSTEM_PROMPT = """\
You are ErnieCLI, a powerful coding and research assistant running in the terminal.
You have access to tools: read_file, list_directory, write_file, bash, baidu_search.

## 工具使用原则
- 需要最新信息、查文档、查版本号时，优先调用 baidu_search
- 操作文件时用 read_file / write_file，不要用 bash cat/echo
- 安装包时 bash 会自动使用清华镜像，无需手动加 -i 参数

## 本土化开发规范（中国开发者环境）
- pip install 自动使用国内镜像，conda 推荐 -c https://mirrors.tuna.tsinghua.edu.cn/anaconda
- 国内 Git 托管优先推荐 Gitee，备选 GitHub
- 云服务：百度云 BOS / 腾讯云 COS / 阿里云 OSS，提供对应 SDK 示例
- 深度学习框架：优先推荐飞桨（PaddlePaddle），熟悉其 API 和生态
- 遇到乱码问题时，检查 GBK/UTF-8 编码，提供 chardet 检测方案
- Docker 镜像推荐使用国内源（阿里云/腾讯云镜像加速）

## 回复规范
- 解释和交互用中文，代码和命令保持英文
- 给出代码时提供完整可运行示例，不省略关键部分
"""

_MAX_TOOL_ROUNDS = 20  # prevent infinite loops


class AgentLoop:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = ErnieClient(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            timeout=cfg.timeout,
        )
        self._memory: str = ""
        self.messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        self.search_enabled = cfg.search_enabled

    def reset(self) -> None:
        self._memory: str = ""
        self.messages = [{"role": "system", "content": self._build_system()}]

    def _build_system(self) -> str:
        parts = [_SYSTEM_PROMPT]
        if self._memory:
            parts.append(f"\n## 持久记忆\n{self._memory}")
        return "\n".join(parts)

    def inject_memory(self, text: str) -> None:
        self._memory = (self._memory + "\n" + text).strip()
        # update system message in-place
        self.messages[0]["content"] = self._build_system()

    def clear_memory(self) -> None:
        self._memory = ""
        self.messages[0]["content"] = self._build_system()

    def inject_context(self, text: str) -> None:
        """Inject extra context as a system message."""
        self.messages.append({"role": "user", "content": f"[context injection]\n{text}"})
        self.messages.append({"role": "assistant", "content": "已收到上下文，我会在后续回答中参考这些内容。"})

    def compact(self) -> None:
        """Summarise the conversation then replace history with the summary."""
        msgs = [m for m in self.messages if m["role"] != "system"]
        if not msgs:
            return
        history_text = "\n".join(
            f"[{m['role']}]: {m.get('content','')}"
            for m in msgs
        )
        summary_prompt = (
            "请将以下对话历史压缩成一段简明的中文摘要，保留关键信息、决策和代码片段：\n\n"
            + history_text[:6000]
        )
        # non-streaming compact call
        result = self.client.chat([
            {"role": "system", "content": "你是一个对话摘要助手。"},
            {"role": "user",   "content": summary_prompt},
        ])
        summary = result.content or "(摘要失败)"
        self.messages = [
            {"role": "system", "content": self._build_system()},
            {"role": "user",   "content": "[历史摘要]"},
            {"role": "assistant", "content": summary},
        ]

    def add_user_message(self, text: str, image_path: Optional[str] = None) -> None:
        if image_path:
            content = _build_image_content(text, image_path)
        else:
            content = text
        self.messages.append({"role": "user", "content": content})

    def save_session(self) -> Path:
        """Persist current conversation to ~/.ernie/sessions/<cwd-hash>.json."""
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        cwd = os.getcwd()
        path = _session_path(cwd)
        payload = {
            "cwd":      cwd,
            "model":    self.cfg.model,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "messages": [m for m in self.messages if m["role"] != "system"],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return path

    @staticmethod
    def session_info(cwd: str | None = None) -> dict | None:
        """Return metadata of the saved session for cwd (or os.getcwd())."""
        path = _session_path(cwd or os.getcwd())
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            data["_path"] = str(path)
            return data
        except Exception:
            return None

    def load_session(self, cwd: str | None = None) -> int:
        """Load saved session for cwd. Returns number of messages restored."""
        info = self.session_info(cwd)
        if not info:
            return 0
        msgs = info.get("messages", [])
        self.messages = [{"role": "system", "content": self._build_system()}] + msgs
        return len(msgs)

    def run_turn(self, user_text: str, image_path: Optional[str] = None) -> None:
        """Run one full turn (may involve multiple tool-call rounds)."""
        self.add_user_message(user_text, image_path=image_path)

        for _round in range(_MAX_TOOL_ROUNDS):
            result = self._stream_and_render()

            if not result.tool_calls:
                # No more tool calls — turn is complete
                self.messages.append({"role": "assistant", "content": result.content})
                self.save_session()
                return

            # Append assistant message with tool calls in OpenAI format
            self.messages.append({
                "role": "assistant",
                "content": result.content or None,
                "tool_calls": [
                    {
                        "id": tc["id"] or f"call_{i}",
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                    }
                    for i, tc in enumerate(result.tool_calls)
                ],
            })

            # Execute each tool call and collect results
            tool_results: list[dict] = []
            for tc in result.tool_calls:
                renderer.render_tool_call(tc["name"], tc["args"])
                success, output, sources = execute_tool(tc["name"], tc["args"], client=self.client)
                renderer.render_tool_result(tc["name"], output, success=success, sources=sources)
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"] or "call_0",
                    "content": output,
                })

            self.messages.extend(tool_results)

        renderer.render_error("达到最大工具调用轮次限制，请重试。")

    def run_single(self, question: str, image_path: Optional[str] = None) -> None:
        """Single-shot mode: ask one question and exit."""
        self.run_turn(question, image_path=image_path)

    def _stream_and_render(self) -> StreamResult:
        """Stream the next response, rendering chunks in real-time."""
        stream_renderer = renderer.StreamRenderer()
        result: StreamResult | None = None

        gen = self.client.stream_chat(
            messages=self.messages,
            tools=ALL_TOOLS,
            search_enabled=self.search_enabled,
        )

        try:
            while True:
                chunk_type, chunk_text = next(gen)
                if chunk_type == "reasoning":
                    stream_renderer.feed_reasoning(chunk_text)
                else:
                    if stream_renderer._reasoning_buf:
                        stream_renderer.end_reasoning()
                    stream_renderer.feed_content(chunk_text)
        except StopIteration as exc:
            result = exc.value

        stream_renderer.finish(
            sources=result.sources if self.search_enabled else None,
            search_tokens=result.search_tokens,
        )
        return result  # type: ignore[return-value]


def _build_image_content(text: str, image_path: str) -> list[dict]:
    """Build a multimodal content list with text + image."""
    p = Path(image_path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode()
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
    ]
