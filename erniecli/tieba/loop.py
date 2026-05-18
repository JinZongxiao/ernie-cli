"""TiebaSession — multi-agent forum discussion loop.

Flow:
  1. /tieba — enter the forum UI
  2. User (楼主) speaks first — posts any question/topic
  3. System selects 1-3 most relevant personas and lets them respond in sequence
  4. User speaks again → more AI responses
  5. No user input = no AI activity (pure user-driven)
  6. /done → terminator synthesises the discussion into a plan file
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from erniecli.api.client import ErnieClient
from erniecli.tui.renderer import StreamRenderer
from erniecli.tieba.personas import Persona
from erniecli.tieba.scheduler import Scheduler
from erniecli.tieba import renderer as R

# Context truncation thresholds
_MAX_CONTEXT_FLOORS = 30
_KEEP_RECENT_FLOORS = 20

# ── Terminator prompts (two-pass) ──────────────────────────────────────────────

_PASS1_SYSTEM = """\
你是一个技术需求分析师。根据楼主的所有发言，提炼出楼主的核心需求和期望目标。

输出结构（直接输出，不要额外解释）：

# 楼主需求分析 · {topic}

## 核心需求
（楼主想解决什么问题，用1-3条概括）

## 期望目标
（楼主希望达到的具体效果）

## 初步方案方向
（仅基于楼主需求，给出3-5条技术方向，不展开细节）
"""

_PASS2_SYSTEM = """\
你是一个技术会议记录员。下面是「初步需求分析」和「完整讨论记录」。请你：

1. 以初步方案为基础，结合讨论中楼主明确认可、追问或重复提及的观点进行修正。
2. 忽略楼主没有回应的纯 AI 自嗨内容（那些没人接的话）。
3. 保留所有风险提示（特别是老PTSD和运维老王提到的坑，这些往往是干货）。
4. 忽略闲聊、玩梗、摸鱼内容。
5. 输出格式为 Markdown，层级清晰，适用于直接保存为 .md 文件。

输出结构（直接输出，不要额外解释）：

# 技术方案 · {topic}
> 整理日期：{date}

## 最终方案
（若有多个，按优先级排序，每个方案说明：做什么 / 为什么 / 怎么做）

## 风险与注意事项
（来自讨论中提到的坑、教训和警告）

## 落地步骤
（可执行的有序步骤清单）

## 讨论摘要
（1-2句话概括本次讨论达成的核心共识）
"""


@dataclass
class TiebaPost:
    floor: int
    author: str       # persona key or "user"
    author_name: str  # display name
    content: str
    timestamp: str = ""

    def format_for_context(self) -> str:
        return f"[{self.floor}楼] @{self.author_name}: {self.content}"


class TiebaSession:
    def __init__(self, client: ErnieClient, personas: dict[str, Persona]):
        self.client   = client
        self.personas = personas
        self.thread:  list[TiebaPost] = []
        self.floor    = 1
        self.topic    = ""   # set from first user post
        self.scheduler = Scheduler(list(personas.keys()))

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        R.render_tieba_welcome()

        is_first_post = True

        while True:
            # ── User speaks first ─────────────────────────────────────────────
            R.render_tieba_input_hint()
            user_input = R.render_tieba_input_prompt(self.floor, self.personas)

            stripped = user_input.strip()

            # Exit commands
            if stripped.lower() in ("/done", "/quit", "/exit", ""):
                if not self.thread:
                    R.render_tieba_info("空楼，什么都没聊，直接走了。")
                    return
                break   # go to terminator

            # Record user post
            if not self.topic:
                self.topic = stripped
            self._add_user_post(stripped)
            R.render_tieba_user_post(self.floor - 1, stripped)

            # ── AI responds ───────────────────────────────────────────────────
            if is_first_post:
                # Special: 摸鱼队长 grabs floor 2, 鹰眼 immediately corrects
                keys = self.scheduler.decide_first_post()
                is_first_post = False
            else:
                keys = self.scheduler.decide(stripped, n=_decide_n(stripped))
                # Dry-round warning if 摸鱼 was auto-inserted mid-discussion
                if keys and keys[0] == "fisherman" and len(self.thread) > 3:
                    R.render_tieba_dry_warning()

            for key in keys:
                persona = self.personas.get(key)
                if not persona:
                    continue
                content = self._persona_speak(persona)
                if content:
                    self.scheduler.mark_content(content)
                    self.scheduler.queue_referenced(content)

        self._run_terminator()

    # ── Persona turn ──────────────────────────────────────────────────────────

    def _persona_speak(self, persona: Persona) -> str:
        messages = self._build_context(persona)

        stream_renderer = StreamRenderer()
        content = ""
        header_printed = False

        try:
            gen = self.client.stream_chat(
                messages=messages,
                tools=None,
                search_enabled=False,
                mcp_servers=None,
            )
            try:
                while True:
                    chunk_type, chunk_text = next(gen)
                    if chunk_type != "reasoning" and chunk_text:
                        # Print header together with the first content chunk
                        # so ID and reply appear at the same time (no dead air)
                        if not header_printed:
                            R.render_tieba_streaming_header(persona, self.floor)
                            header_printed = True
                        stream_renderer.feed_content(chunk_text)
            except StopIteration as exc:
                result = exc.value
                stream_renderer.finish()
                content = result.content or ""
        except Exception as e:
            from erniecli.tui.renderer import render_error
            render_error(f"[{persona.name}] 发言失败：{e}")

        if header_printed:
            R.render_tieba_post_footer()

        if content:
            self.thread.append(TiebaPost(
                floor=self.floor,
                author=persona.key,
                author_name=persona.name,
                content=content,
                timestamp=_now(),
            ))
            self.floor += 1

        return content

    # ── Terminator (two-pass) ─────────────────────────────────────────────────

    def _run_terminator(self) -> None:
        if not self.thread:
            return

        today = datetime.date.today().strftime("%Y-%m-%d")
        topic = self.topic or "未命名话题"

        # ── Pass 1: analyse 楼主's requirements ──────────────────────────────
        R.render_tieba_terminator_header()

        user_posts_text = "\n\n".join(
            f"[{p.floor}楼] 楼主: {p.content}"
            for p in self.thread if p.author == "user"
        )
        pass1_messages = [
            {
                "role": "system",
                "content": _PASS1_SYSTEM.replace("{topic}", topic),
            },
            {
                "role": "user",
                "content": f"楼主关于「{topic}」的所有发言：\n\n{user_posts_text}",
            },
        ]

        initial_plan = ""
        sr1 = StreamRenderer()
        try:
            gen = self.client.stream_chat(
                messages=pass1_messages, tools=None,
                search_enabled=False, mcp_servers=None,
            )
            try:
                while True:
                    chunk_type, chunk_text = next(gen)
                    if chunk_type != "reasoning":
                        sr1.feed_content(chunk_text)
            except StopIteration as exc:
                sr1.finish()
                initial_plan = exc.value.content or ""
        except Exception as e:
            from erniecli.tui.renderer import render_error
            render_error(f"终结者第一阶段失败：{e}")
            return

        if not initial_plan:
            return

        # ── Pass 2: refine with full discussion ───────────────────────────────
        R.render_tieba_terminator_refine_header()

        pass2_messages = [
            {
                "role": "system",
                "content": _PASS2_SYSTEM
                    .replace("{topic}", topic)
                    .replace("{date}",  today),
            },
            {
                "role": "user",
                "content": (
                    f"【初步需求分析】\n\n{initial_plan}\n\n"
                    f"【完整讨论记录】\n\n{self._format_thread()}"
                ),
            },
        ]

        final_plan = ""
        sr2 = StreamRenderer()
        try:
            gen = self.client.stream_chat(
                messages=pass2_messages, tools=None,
                search_enabled=False, mcp_servers=None,
            )
            try:
                while True:
                    chunk_type, chunk_text = next(gen)
                    if chunk_type != "reasoning":
                        sr2.feed_content(chunk_text)
            except StopIteration as exc:
                sr2.finish()
                final_plan = exc.value.content or ""
        except Exception as e:
            from erniecli.tui.renderer import render_error
            render_error(f"终结者第二阶段失败：{e}")
            return

        if final_plan:
            out_path = Path(f"tieba-plan-{today}.md")
            out_path.write_text(final_plan, encoding="utf-8")
            R.render_tieba_terminator_saved(str(out_path.resolve()))

    # ── Context ───────────────────────────────────────────────────────────────

    def _build_context(self, persona: Persona) -> list[dict]:
        thread = self.thread
        if len(thread) > _MAX_CONTEXT_FLOORS:
            user_posts = [p for p in thread if p.author == "user"]
            recent_ai  = [p for p in thread if p.author != "user"][-_KEEP_RECENT_FLOORS:]
            combined   = sorted(set(user_posts + recent_ai), key=lambda p: p.floor)
        else:
            combined = thread

        thread_text = "\n".join(p.format_for_context() for p in combined)
        # Last user message (楼主最新发言) — extra emphasis for the AI
        last_user = next(
            (p.content for p in reversed(thread) if p.author == "user"), ""
        )

        user_content = (
            f"贴吧话题：{self.topic}\n\n"
            f"楼层记录：\n{thread_text}\n\n"
            f"楼主最新发言：{last_user}\n\n"
            f"现在请你以 {persona.emoji}{persona.name} 的身份回复。\n"
            "要求：\n"
            "- 针对楼主最新发言，发表有新意的观点（不重复别人已说的）\n"
            "- 引用其他楼层时用格式：>> 引用@名字: 摘要\n"
            "- 保持你的人设风格\n"
        )
        return [
            {"role": "system", "content": persona.system},
            {"role": "user",   "content": user_content},
        ]

    def _format_thread(self) -> str:
        lines = []
        for p in self.thread:
            label = "楼主" if p.author == "user" else p.author_name
            lines.append(f"[{p.floor}楼] {label}: {p.content}")
        return "\n\n".join(lines)

    def _add_user_post(self, content: str) -> None:
        self.thread.append(TiebaPost(
            floor=self.floor,
            author="user",
            author_name="楼主",
            content=content,
            timestamp=_now(),
        ))
        self.floor += 1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M")


def _decide_n(user_input: str) -> int:
    """1-3 personas respond based on input length/complexity."""
    length = len(user_input)
    if length < 15:
        return 1   # short follow-up → 1 persona
    if length < 50:
        return 2   # normal → 2 personas
    return 3       # long/complex input → 3 personas
