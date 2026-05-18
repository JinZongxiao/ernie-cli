"""Worker agent — lightweight model that executes specific sub-tasks."""
from __future__ import annotations

import json
from typing import Optional, TYPE_CHECKING

from openai import OpenAI

from erniecli.agent.tools import ALL_TOOLS, execute_tool
from erniecli.tui import renderer

if TYPE_CHECKING:
    from erniecli.api.client import ErnieClient

_WORKER_SYSTEM = """\
你是 Worker AI，由 Boss AI 调度来执行具体任务。
- 直接执行，不需要确认，不需要废话
- 优先使用工具完成任务（read_file/write_file/bash/baidu_search）
- 执行完成后，返回简洁的结果摘要和关键输出
- 遇到错误时说明原因并给出修复建议
"""

_MAX_WORKER_ROUNDS = 10


class WorkerAgent:
    """Thin wrapper around a smaller/faster model that can use all tools."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        boss_client: Optional["ErnieClient"] = None,
        timeout: int = 60,
    ):
        self.model = model
        self.boss_client = boss_client   # for baidu_search fallback
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def run_task(self, task: str, context: str = "") -> str:
        """Run a sub-task and return the result as a string."""
        user_content = task
        if context:
            user_content = f"上下文信息：\n{context}\n\n任务：{task}"

        messages: list[dict] = [
            {"role": "system", "content": _WORKER_SYSTEM},
            {"role": "user",   "content": user_content},
        ]

        for _round in range(_MAX_WORKER_ROUNDS):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=ALL_TOOLS,
                    tool_choice="auto",
                    max_tokens=4096,
                    stream=False,
                )
            except Exception as e:
                return f"[Worker 调用失败] {e}"

            msg = resp.choices[0].message
            finish = resp.choices[0].finish_reason

            if not msg.tool_calls or finish == "stop":
                return msg.content or "(Worker 无输出)"

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute tools and collect results
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                renderer.render_worker_tool_call(name, args)
                success, output, sources = execute_tool(
                    name, args, client=self.boss_client
                )
                renderer.render_worker_tool_result(name, output, success)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output,
                })

        return "(Worker 达到最大轮次限制)"
