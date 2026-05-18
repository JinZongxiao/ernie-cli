"""Intent-based three-layer scheduler for Tieba plan mode.

Priority (high → low):
  P1 — @mention: only that one persona responds, others stay silent
  P2 — Intent detection: keyword → role mapping table
  P3 — Balance fallback: round-robin ensuring everyone participates

Special rule — first post:
  摸鱼队长 always grabs floor 2 (mandatory).
  鹰眼 immediately follows to correct 摸鱼队长 (mandatory).
  Then normal scheduling resumes.

Dry-round rule:
  If 3+ consecutive AI posts contain no technical keywords,
  摸鱼队长 is forced in to break the silence.
"""
from __future__ import annotations

import re
from collections import deque

# ── Intent → persona key mapping ─────────────────────────────────────────────
# Each entry: (trigger_keywords, [must_respond_keys], [optional_keys])
# "must" = always included; "optional" = added if n slots remain

_INTENT_RULES: list[tuple[list[str], list[str], list[str]]] = [
    # Non-technical / venting — 摸鱼 only, others silent
    (
        ["烦死了", "老板", "我司", "加班", "薪资", "涨薪", "离职", "pua", "PUA",
         "卷", "摆烂", "躺平", "绩效"],
        ["fisherman"],
        [],
    ),
    # "Can't understand / explain simply" — 翻译官 must respond
    (
        ["看不懂", "太抽象", "说人话", "听不懂", "不懂", "什么意思", "太复杂",
         "能解释一下", "简单说"],
        ["translator"],
        ["eagle"],
    ),
    # Product / requirements / UX — PM must respond
    (
        ["需求", "用户体验", "功能", "上线时间", "排期", "产品", "竞品",
         "用户", "体验"],
        ["pm"],
        ["eagle"],
    ),
    # Deployment / ops — 运维老王 must respond
    (
        ["部署", "上线", "运维", "生产环境", "配置", "环境", "容器", "k8s",
         "docker", "Docker", "服务器", "扩容", "监控", "告警", "回滚"],
        ["ops"],
        ["eagle", "ptsd"],
    ),
    # Blood-and-tears / production incidents — 老PTSD
    (
        ["前公司", "踩坑", "血泪", "教训", "生产事故", "翻车", "坑爹"],
        ["ptsd"],
        ["eagle"],
    ),
    # Theory / interview / principle — 龙场 first, 鹰眼 second
    (
        ["原理", "为什么", "面试", "区别", "底层", "设计模式", "复杂度",
         "本质", "机制", "深入"],
        ["dragon", "eagle"],
        ["translator"],
    ),
    # Code / bug / implementation — 鹰眼 first, 龙场 second
    (
        ["代码", "技术实现", "安全", "架构", "报错", "bug", "Bug", "ERROR",
         "慢", "挂了", "怎么写", "帮我看看", "实现", "方案"],
        ["eagle", "dragon"],
        ["translator"],
    ),
]

# Keywords that count as "technical" (resets dry-round counter)
_TECHNICAL_WORDS = {
    "代码", "方案", "原理", "实现", "架构", "算法", "数据库",
    "缓存", "性能", "接口", "部署", "优化", "设计", "框架",
    "系统", "协议", "服务", "模型", "分析",
}

# Default round-robin order (all 8 personas)
_DEFAULT_ORDER = [
    "fisherman", "eagle", "dragon", "translator",
    "ptsd", "pm", "newbie", "ops",
]

# How many posts before 小白 is eligible to appear (avoids too-early confusion)
_NEWBIE_MIN_FLOOR = 6


class Scheduler:
    def __init__(self, available_keys: list[str]):
        self._available = set(available_keys)
        self._order     = [k for k in _DEFAULT_ORDER if k in self._available]
        # Append any custom keys not in default order
        for k in available_keys:
            if k not in self._order:
                self._order.append(k)

        self._rr_index     = 0
        self._dry_rounds   = 0       # consecutive rounds without technical content
        self._pending      : deque[str] = deque()   # from >> 引用 triggers
        self._total_floors = 0       # tracks how many AI posts have been made

    # ── Public API ────────────────────────────────────────────────────────────

    def decide_first_post(self) -> list[str]:
        """Special rule for the very first user post:
        1. 摸鱼队长 grabs floor 2 (mandatory)
        2. 鹰眼 immediately follows to correct them (mandatory)
        """
        keys: list[str] = []
        if "fisherman" in self._available:
            keys.append("fisherman")
        if "eagle" in self._available:
            keys.append("eagle")
        # Advance round-robin past these two so they don't show up first again
        self._advance_past(keys)
        return keys

    def decide(self, user_input: str, n: int = 2) -> list[str]:
        """Return ordered list of persona keys to respond this round."""
        chosen: list[str] = []

        # P1: @mention → only that person responds
        mentioned = _extract_mentions(user_input)
        if mentioned:
            for m in mentioned:
                from erniecli.tieba.personas import resolve_mention
                key = resolve_mention(m)
                if key and key in self._available and key not in chosen:
                    chosen.append(key)
            # With @mention, only mentioned people speak
            return chosen[:n]

        # Dry-round: 摸鱼队长 forced in
        if self._dry_rounds >= 3 and "fisherman" in self._available:
            if "fisherman" not in chosen:
                chosen.insert(0, "fisherman")
            self._dry_rounds = 0

        # P2: Intent detection
        must, optional = _match_intent(user_input)
        for key in must:
            if key in self._available and key not in chosen:
                chosen.append(key)
        for key in optional:
            if key in self._available and key not in chosen and len(chosen) < n:
                chosen.append(key)

        # 小白 eligibility: only after enough floors, and not already chosen
        if (self._total_floors >= _NEWBIE_MIN_FLOOR
                and "newbie" in self._available
                and "newbie" not in chosen
                and len(chosen) < n
                and _should_newbie_appear(user_input, self._total_floors)):
            chosen.append("newbie")

        # Consume pending queue (from >> 引用 auto-triggers)
        while self._pending and len(chosen) < n:
            key = self._pending.popleft()
            if key in self._available and key not in chosen:
                chosen.append(key)

        # P3: round-robin to fill remaining slots
        attempts = 0
        while len(chosen) < n and attempts < len(self._order):
            key = self._order[self._rr_index % len(self._order)]
            self._rr_index += 1
            attempts += 1
            if key not in chosen and key in self._available:
                chosen.append(key)

        return chosen

    def mark_content(self, content: str) -> None:
        """Update dry-round counter and advance floor tracker after each AI post."""
        self._total_floors += 1
        if any(word in content for word in _TECHNICAL_WORDS):
            self._dry_rounds = 0
        else:
            self._dry_rounds += 1

    def queue_referenced(self, content: str) -> None:
        """Parse AI response for >> 引用@XXX: and queue the referenced persona."""
        for match in re.finditer(r'>>\s*引用@([^\s:：,，\n]+)', content):
            from erniecli.tieba.personas import resolve_mention
            key = resolve_mention(match.group(1))
            if key and key in self._available and key not in self._pending:
                self._pending.append(key)

    # ── Private ───────────────────────────────────────────────────────────────

    def _advance_past(self, keys: list[str]) -> None:
        """Advance the round-robin cursor past the given keys."""
        for key in keys:
            try:
                idx = self._order.index(key)
                if idx >= self._rr_index % len(self._order):
                    self._rr_index = idx + 1
            except ValueError:
                pass


# ── Intent matching ───────────────────────────────────────────────────────────

def _match_intent(text: str) -> tuple[list[str], list[str]]:
    """Return (must_respond, optional) based on the first matching intent rule."""
    for keywords, must, optional in _INTENT_RULES:
        if any(kw in text for kw in keywords):
            return must, optional
    return [], []


def _extract_mentions(text: str) -> list[str]:
    return re.findall(r'@([^\s@，,。.！!？?\n]+)', text)


def _should_newbie_appear(user_input: str, total_floors: int) -> bool:
    """Heuristic: newbie appears after accumulated technical posts when
    the user's latest message is relatively short (implies they're still
    digesting), or every ~8 floors as a natural interval."""
    is_short_followup = len(user_input.strip()) < 30
    natural_interval  = (total_floors % 8 == 0)
    return is_short_followup or natural_interval
