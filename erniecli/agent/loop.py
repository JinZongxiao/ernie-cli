"""Core agentic loop: stream → tool calls → execute → feed back → repeat."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_SESSIONS_DIR  = Path.home() / ".ernie" / "sessions"
_DATASET_DIR   = Path.home() / ".ernie" / "dataset"

from erniecli.api.client import ErnieClient, StreamResult
from erniecli.agent.tools import ALL_TOOLS, execute_tool
from erniecli.config import Config
from erniecli.tui import renderer


def _session_path(cwd: str) -> Path:
    key = hashlib.sha1(cwd.encode()).hexdigest()[:16]
    return _SESSIONS_DIR / f"{key}.json"


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

_MAX_TOOL_ROUNDS = 20

_CONFUCIAN_HARNESS = """\
## 论语输出规范（孔子风格约束层）
你现在受论语精神约束，回答须体现以下原则：

- **言简意赅**："辞达而已矣"——说清楚就行，不废话，不凑字数
- **知之为知之**：不确定的事直说不确定，不要编造，不要过度自信
- **因材施教**：根据用户的技术水平调整解释深度，不要对初学者甩源码，不要对专家讲基础
- **过则勿惮改**：发现自己之前说错了，直接承认并纠正，不要绕弯子
- **工欲善其事**：给工具调用方案前先想清楚，不要无头苍蝇乱调工具
- **君子不器**：不要只给答案，适当说明原因和权衡，让用户真的学到东西
- **慎于言**：不要在回答末尾加"如有问题欢迎继续提问"之类的废话结尾

> 此约束层由用户开启，可用 /harness off 关闭。
"""


@dataclass
class TurnRecord:
    """Single conversation turn with quality signals."""
    idx: int
    user: str
    assistant: str
    label: Optional[str] = None          # "up" | "down" | None
    tool_rounds: int = 0
    tool_failures: int = 0
    response_chars: int = 0
    interrupted: bool = False            # user hit Ctrl+C mid-turn
    reasoning: str = ""                  # buffered thinking content


@dataclass
class SessionScore:
    solved: str = ""       # "y" | "n" | "?"
    verbose: int = 0       # 1=少 2=刚好 3=多
    tool_quality: int = 0  # 1=准 2=一般 3=乱
    comment: str = ""


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
        self.harness_enabled: bool = getattr(cfg, "harness_enabled", False)
        self.messages: list[dict] = [{"role": "system", "content": self._build_system()}]
        self.search_enabled = cfg.search_enabled
        self.mcp_servers: list[dict] = list(cfg.mcp_servers)
        # feedback tracking
        self._turns: list[TurnRecord] = []
        self.session_score: Optional[SessionScore] = None

    def reset(self) -> None:
        self._memory = ""
        self._turns = []
        self.session_score = None
        self.messages = [{"role": "system", "content": self._build_system()}]

    def _build_system(self) -> str:
        parts = [_SYSTEM_PROMPT]
        if self.harness_enabled:
            parts.append(_CONFUCIAN_HARNESS)
        if self._memory:
            parts.append(f"\n## 持久记忆\n{self._memory}")
        return "\n".join(parts)

    def inject_memory(self, text: str) -> None:
        self._memory = (self._memory + "\n" + text).strip()
        self.messages[0]["content"] = self._build_system()

    def clear_memory(self) -> None:
        self._memory = ""
        self.messages[0]["content"] = self._build_system()

    def set_harness(self, enabled: bool) -> None:
        self.harness_enabled = enabled
        self.messages[0]["content"] = self._build_system()

    def inject_context(self, text: str) -> None:
        self.messages.append({"role": "user", "content": f"[context injection]\n{text}"})
        self.messages.append({"role": "assistant", "content": "已收到上下文，我会在后续回答中参考这些内容。"})

    def compact(self) -> None:
        msgs = [m for m in self.messages if m["role"] != "system"]
        if not msgs:
            return
        history_text = "\n".join(f"[{m['role']}]: {m.get('content','')}" for m in msgs)
        result = self.client.chat([
            {"role": "system", "content": "你是一个对话摘要助手。"},
            {"role": "user",   "content":
             "请将以下对话历史压缩成一段简明的中文摘要，保留关键信息、决策和代码片段：\n\n"
             + history_text[:6000]},
        ])
        summary = result.content or "(摘要失败)"
        self.messages = [
            {"role": "system", "content": self._build_system()},
            {"role": "user",   "content": "[历史摘要]"},
            {"role": "assistant", "content": summary},
        ]

    def add_user_message(self, text: str, image_path: Optional[str] = None) -> None:
        content = _build_image_content(text, image_path) if image_path else text
        self.messages.append({"role": "user", "content": content})

    # ── turn label (called by REPL after showing feedback prompt) ─────────────

    def set_last_turn_label(self, label: str) -> None:
        """Set 'up'/'down' label on the most recently completed turn."""
        if self._turns:
            self._turns[-1].label = label

    def mark_last_turn_interrupted(self) -> None:
        if self._turns:
            self._turns[-1].interrupted = True

    # ── session persistence ───────────────────────────────────────────────────

    def save_session(self) -> Path:
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        cwd = os.getcwd()
        path = _session_path(cwd)
        payload: dict = {
            "cwd":      cwd,
            "model":    self.cfg.model,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "messages": [m for m in self.messages if m["role"] != "system"],
            "turns":    [_turn_to_dict(t) for t in self._turns],
        }
        if self.session_score:
            payload["session_score"] = {
                "solved":       self.session_score.solved,
                "verbose":      self.session_score.verbose,
                "tool_quality": self.session_score.tool_quality,
                "comment":      self.session_score.comment,
            }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return path

    @staticmethod
    def session_info(cwd: str | None = None) -> dict | None:
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
        info = self.session_info(cwd)
        if not info:
            return 0
        msgs = info.get("messages", [])
        self.messages = [{"role": "system", "content": self._build_system()}] + msgs
        # restore turn records if present (labels survive /resume)
        self._turns = [_dict_to_turn(d) for d in info.get("turns", [])]
        return len(msgs)

    # ── run ───────────────────────────────────────────────────────────────────

    def run_turn(self, user_text: str, image_path: Optional[str] = None) -> TurnRecord:
        """Run one full turn. Returns a TurnRecord with auto-signals filled in."""
        self.add_user_message(user_text, image_path=image_path)

        turn = TurnRecord(idx=len(self._turns), user=user_text, assistant="")
        tool_rounds = 0
        tool_failures = 0

        for _round in range(_MAX_TOOL_ROUNDS):
            result, reasoning = self._stream_and_render()

            if not result.tool_calls:
                turn.assistant = result.content
                turn.tool_rounds = tool_rounds
                turn.tool_failures = tool_failures
                turn.response_chars = len(result.content)
                turn.reasoning = reasoning
                self.messages.append({"role": "assistant", "content": result.content})
                self._turns.append(turn)
                self.save_session()
                return turn

            tool_rounds += 1
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

            tool_results: list[dict] = []
            for tc in result.tool_calls:
                renderer.render_tool_call(tc["name"], tc["args"])
                success, output, sources = execute_tool(tc["name"], tc["args"], client=self.client)
                renderer.render_tool_result(tc["name"], output, success=success, sources=sources)
                if not success:
                    tool_failures += 1
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"] or "call_0",
                    "content": output,
                })

            self.messages.extend(tool_results)

        renderer.render_error("达到最大工具调用轮次限制，请重试。")
        turn.tool_rounds = tool_rounds
        turn.tool_failures = tool_failures
        self._turns.append(turn)
        return turn

    def run_single(self, question: str, image_path: Optional[str] = None) -> None:
        self.run_turn(question, image_path=image_path)

    def _stream_and_render(self) -> tuple[StreamResult, str]:
        stream_renderer = renderer.StreamRenderer()
        result: StreamResult | None = None

        renderer.render_assistant_label(self.cfg.model)

        gen = self.client.stream_chat(
            messages=self.messages,
            tools=ALL_TOOLS,
            search_enabled=self.search_enabled,
            mcp_servers=self.mcp_servers or None,
        )

        try:
            while True:
                chunk_type, chunk_text = next(gen)
                if chunk_type == "reasoning":
                    stream_renderer.feed_reasoning(chunk_text)
                else:
                    stream_renderer.feed_content(chunk_text)
        except StopIteration as exc:
            result = exc.value

        stream_renderer.finish(
            sources=result.sources if self.search_enabled else None,
            search_tokens=result.search_tokens,
        )
        return result, stream_renderer.get_reasoning()  # type: ignore[return-value]

    # ── dataset export ────────────────────────────────────────────────────────

    def export_dataset(self, out_path: Optional[Path] = None) -> Path:
        """Generate DPO jsonl from all saved sessions. Returns output path."""
        _DATASET_DIR.mkdir(parents=True, exist_ok=True)
        out = out_path or (_DATASET_DIR / f"dpo_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")

        session_files = list(_SESSIONS_DIR.glob("*.json"))
        if not session_files:
            raise FileNotFoundError("没有找到任何会话文件。")

        records: list[dict] = []
        for sf in session_files:
            try:
                data = json.loads(sf.read_text())
            except Exception:
                continue

            score = data.get("session_score", {})
            turns = data.get("turns", [])
            model = data.get("model", "ernie-5.1")
            session_id = sf.stem

            # skip sessions where problem wasn't solved at all
            if score.get("solved") == "n" and not any(
                t.get("label") == "up" for t in turns
            ):
                continue

            for t in turns:
                user      = t.get("user", "")
                assistant = t.get("assistant", "")
                label     = t.get("label")

                if not user or not assistant:
                    continue

                signals = {
                    "tool_rounds":    t.get("tool_rounds", 0),
                    "tool_failures":  t.get("tool_failures", 0),
                    "response_chars": t.get("response_chars", 0),
                    "interrupted":    t.get("interrupted", False),
                }
                is_bad = (
                    label == "down"
                    or t.get("interrupted")
                    or t.get("tool_failures", 0) >= 2
                    or (score.get("verbose") == 3 and not label)
                )

                if label == "up":
                    # clean positive example — no rewriting needed
                    records.append({
                        "source":     "ernie-cli-v1",
                        "session_id": session_id,
                        "type":       "positive",
                        "prompt":     user,
                        "chosen":     assistant,
                        "rejected":   None,
                        "metadata":   {"model": model, "session_score": score, "signals": signals},
                    })
                elif is_bad:
                    # ask Ernie to rewrite into a better response
                    rewritten = self._rewrite_response(user, assistant, score)
                    if rewritten and rewritten != assistant:
                        records.append({
                            "source":     "ernie-cli-v1",
                            "session_id": session_id,
                            "type":       "dpo_pair",
                            "prompt":     user,
                            "chosen":     rewritten,
                            "rejected":   assistant,
                            "metadata":   {"model": model, "session_score": score, "signals": signals},
                        })

        with out.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        return out

    def _rewrite_response(self, user: str, bad_response: str, score: dict) -> str:
        """Ask Ernie to produce a better response given quality feedback."""
        hints: list[str] = []
        if score.get("verbose") == 3:
            hints.append("回复要简洁，避免冗长解释，直接给出结论和代码。")
        if score.get("tool_quality") == 3:
            hints.append("避免不必要的工具调用，只在真正需要时才调用工具。")
        if score.get("solved") == "n":
            hints.append("上一版回答没有解决用户问题，请重新思考并给出正确答案。")
        hint_text = "\n".join(hints) if hints else "请提供一个更高质量、更简洁准确的回答。"

        result = self.client.chat([
            {"role": "system", "content":
             f"你是一个专业的代码助手。请根据以下改进要求，重写这个回答：\n{hint_text}"},
            {"role": "user", "content":
             f"原始问题：{user}\n\n原始回答（质量不佳）：\n{bad_response}\n\n"
             f"请给出改进后的回答："},
        ])
        return result.content or ""


# ── helpers ───────────────────────────────────────────────────────────────────

def _turn_to_dict(t: TurnRecord) -> dict:
    return {
        "idx":           t.idx,
        "user":          t.user,
        "assistant":     t.assistant,
        "label":         t.label,
        "tool_rounds":   t.tool_rounds,
        "tool_failures": t.tool_failures,
        "response_chars":t.response_chars,
        "interrupted":   t.interrupted,
    }


def _dict_to_turn(d: dict) -> TurnRecord:
    return TurnRecord(
        idx           = d.get("idx", 0),
        user          = d.get("user", ""),
        assistant     = d.get("assistant", ""),
        label         = d.get("label"),
        tool_rounds   = d.get("tool_rounds", 0),
        tool_failures = d.get("tool_failures", 0),
        response_chars= d.get("response_chars", 0),
        interrupted   = d.get("interrupted", False),
    )


def _build_image_content(text: str, image_path: str) -> list[dict]:
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
