"""Ernie API client — OpenAI-compatible with Ernie-specific extensions."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Generator, Optional
from urllib.parse import urlparse

from openai import OpenAI

# Known Chinese/tech site domain → human-readable name
_SITE_NAMES: dict[str, str] = {
    "zhihu.com":           "知乎",
    "csdn.net":            "CSDN",
    "baike.baidu.com":     "百度百科",
    "baidu.com":           "百度",
    "juejin.cn":           "掘金",
    "jianshu.com":         "简书",
    "cnblogs.com":         "博客园",
    "segmentfault.com":    "SegmentFault",
    "oschina.net":         "开源中国",
    "gitee.com":           "Gitee",
    "github.com":          "GitHub",
    "stackoverflow.com":   "Stack Overflow",
    "docs.python.org":     "Python 文档",
    "paddlepaddle.org.cn": "飞桨官网",
    "huggingface.co":      "Hugging Face",
    "arxiv.org":           "arXiv",
    "pytorch.org":         "PyTorch",
    "tensorflow.org":      "TensorFlow",
    "pypi.org":            "PyPI",
    "npmjs.com":           "npm",
    "developer.mozilla.org": "MDN",
}

_URL_RE = re.compile(r'https?://[^\s\)\]\"\'\>]+')


def extract_sources(text: str) -> list[dict]:
    """Extract unique URLs from text and return source metadata."""
    seen: set[str] = set()
    sources: list[dict] = []
    for url in _URL_RE.findall(text):
        url = url.rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)
        try:
            host = urlparse(url).netloc.lower().lstrip("www.")
        except Exception:
            continue
        name = next((v for k, v in _SITE_NAMES.items() if host.endswith(k)), host)
        sources.append({"url": url, "host": host, "name": name})
    return sources


@dataclass
class ToolCallAccumulator:
    id: str = ""
    name: str = ""
    arguments: str = ""
    index: int = 0


@dataclass
class StreamResult:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: Optional[str] = None
    search_tokens: int = 0
    sources: list[dict] = field(default_factory=list)   # extracted from content


class ErnieClient:
    def __init__(self, api_key: str, base_url: str, model: str,
                 max_tokens: int = 8192, temperature: float = 0.7, timeout: int = 120):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def list_models(self) -> list[str]:
        try:
            models = self._client.models.list()
            return sorted(m.id for m in models.data)
        except Exception:
            return []

    def stream_chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        search_enabled: bool = False,
    ) -> Generator[tuple[str, str], None, StreamResult]:
        """Stream chat. Yields (chunk_type, text). Returns StreamResult."""
        extra_body: dict = {}
        if search_enabled:
            extra_body["web_search"] = {"enable": True}

        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if extra_body:
            kwargs["extra_body"] = extra_body

        stream = self._client.chat.completions.create(**kwargs)

        result = StreamResult()
        tc_accum: dict[int, ToolCallAccumulator] = {}

        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta  = choice.delta

            reasoning_delta = getattr(delta, "reasoning_content", None)
            if reasoning_delta:
                result.reasoning += reasoning_delta
                yield "reasoning", reasoning_delta

            if delta.content:
                result.content += delta.content
                yield "content", delta.content

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_accum:
                        tc_accum[idx] = ToolCallAccumulator(index=idx)
                    acc = tc_accum[idx]
                    if tc_delta.id:
                        acc.id = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc.name += tc_delta.function.name
                        if tc_delta.function.arguments:
                            acc.arguments += tc_delta.function.arguments

            if choice.finish_reason:
                result.finish_reason = choice.finish_reason

            # capture search_tokens from usage on final chunk
            if hasattr(chunk, "usage") and chunk.usage:
                pt = chunk.usage.prompt_tokens_details
                if pt and hasattr(pt, "search_tokens") and pt.search_tokens:
                    result.search_tokens = pt.search_tokens

        for idx in sorted(tc_accum):
            acc = tc_accum[idx]
            try:
                args = json.loads(acc.arguments) if acc.arguments else {}
            except json.JSONDecodeError:
                args = {"raw": acc.arguments}
            result.tool_calls.append({"id": acc.id, "name": acc.name, "args": args})

        # extract source URLs from combined content
        combined = result.content + "\n" + result.reasoning
        result.sources = extract_sources(combined)

        return result

    def search(self, query: str) -> tuple[str, list[dict]]:
        """Focused search call for the baidu_search tool.
        Returns (answer_text, sources)."""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是搜索助手。基于搜索结果，简明列出关键信息，保留所有来源URL。"},
                {"role": "user",   "content": query},
            ],
            max_tokens=2048,
            stream=False,
            extra_body={"web_search": {"enable": True}},
        )
        text = resp.choices[0].message.content or ""
        reasoning = getattr(resp.choices[0].message, "reasoning_content", "") or ""
        sources = extract_sources(text + "\n" + reasoning)
        return text, sources

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        search_enabled: bool = False,
    ) -> StreamResult:
        result = StreamResult()
        gen = self.stream_chat(messages, tools=tools, search_enabled=search_enabled)
        try:
            while True:
                next(gen)
        except StopIteration as exc:
            result = exc.value
        return result

    def __init__(self, api_key: str, base_url: str, model: str,
                 max_tokens: int = 8192, temperature: float = 0.7, timeout: int = 120):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def list_models(self) -> list[str]:
        """Return model IDs available under the current API key."""
        try:
            models = self._client.models.list()
            return sorted(m.id for m in models.data)
        except Exception:
            return []

    def stream_chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        search_enabled: bool = False,
    ) -> Generator[tuple[str, str], None, StreamResult]:
        """Stream the chat response.

        Yields (chunk_type, chunk_text) tuples where chunk_type is:
          "content"   — normal response token
          "reasoning" — thinking chain token

        Returns a StreamResult via StopIteration.value (use `yield from` or
        loop manually and catch StopIteration).
        """
        extra_body: dict = {}
        if search_enabled:
            extra_body["web_search"] = {"enable": True}

        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if extra_body:
            kwargs["extra_body"] = extra_body

        stream = self._client.chat.completions.create(**kwargs)

        result = StreamResult()
        # tool call accumulator keyed by index
        tc_accum: dict[int, ToolCallAccumulator] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # reasoning_content is an Ernie-specific extra field
            reasoning_delta = getattr(delta, "reasoning_content", None)
            if reasoning_delta:
                result.reasoning += reasoning_delta
                yield "reasoning", reasoning_delta

            if delta.content:
                result.content += delta.content
                yield "content", delta.content

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_accum:
                        tc_accum[idx] = ToolCallAccumulator(index=idx)
                    acc = tc_accum[idx]
                    if tc_delta.id:
                        acc.id = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc.name += tc_delta.function.name
                        if tc_delta.function.arguments:
                            acc.arguments += tc_delta.function.arguments

            if chunk.choices[0].finish_reason:
                result.finish_reason = chunk.choices[0].finish_reason

        # finalise tool calls
        for idx in sorted(tc_accum):
            acc = tc_accum[idx]
            try:
                args = json.loads(acc.arguments) if acc.arguments else {}
            except json.JSONDecodeError:
                args = {"raw": acc.arguments}
            result.tool_calls.append({
                "id":   acc.id,
                "name": acc.name,
                "args": args,
            })

        return result

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        search_enabled: bool = False,
    ) -> StreamResult:
        """Non-streaming convenience wrapper (collects full stream)."""
        result = StreamResult()
        gen = self.stream_chat(messages, tools=tools, search_enabled=search_enabled)
        try:
            while True:
                next(gen)
        except StopIteration as exc:
            result = exc.value
        return result
