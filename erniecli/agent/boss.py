"""Boss mode: Ernie 5.1 orchestrates, deepseek-v4-flash executes."""
from __future__ import annotations

import json
from typing import Optional

from erniecli.agent.loop import AgentLoop, _build_image_content
from erniecli.agent.tools import ALL_TOOLS, execute_tool
from erniecli.agent.worker import WorkerAgent
from erniecli.config import Config
from erniecli.tui import renderer

# ── Boss system prompt ────────────────────────────────────────────────────────

_BOSS_SYSTEM = """\
You are Boss AI — an orchestrator powered by Ernie 5.1.
Your job is to plan, delegate, and synthesize. You have one special tool:
  delegate_to_worker(task, context)

## 何时委派给 Worker
- 编写、修改、调试代码
- 读写文件、执行 shell 命令
- 网络搜索与信息收集
- 任何需要实际"动手"的操作

## 何时自己处理
- 分析任务结构、制定计划
- 判断子任务之间的依赖关系
- 综合多个 Worker 的结果
- 最终呈现给用户的回答

## 工作流程
1. 收到用户请求后，思考是否需要拆解
2. 对每个需要执行的子任务调用 delegate_to_worker
3. 等待所有 Worker 完成后，综合结果
4. 用中文给用户清晰的最终回答

## 委派原则
- task 字段要清晰完整，Worker 看不到上下文
- 如果任务间有依赖，按顺序串行委派
- 独立任务可以在一轮内多次委派（会依次执行）

## 回复规范
- 解释和交互用中文，代码和命令保持英文
- 综合结果时说明各 Worker 完成了什么
"""

# ── delegate_to_worker tool schema ───────────────────────────────────────────

DELEGATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate_to_worker",
        "description": (
            "将一个具体的执行子任务委派给 Worker AI（deepseek 模型）处理。"
            "Worker 有完整的工具调用能力（读写文件、执行命令、搜索）。"
            "适合用于：写代码、执行脚本、读文件、搜索信息等动手操作。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "要执行的具体任务描述，需完整清晰（Worker 没有对话上下文）",
                },
                "context": {
                    "type": "string",
                    "description": "执行任务所需的额外上下文（代码片段、文件路径、前置结果等）",
                },
            },
            "required": ["task"],
        },
    },
}

# Boss uses delegate tool + all regular tools as fallback
_BOSS_TOOLS = [DELEGATE_SCHEMA] + ALL_TOOLS


class BossLoop(AgentLoop):
    """AgentLoop variant where Ernie 5.1 orchestrates and workers execute."""

    def __init__(self, cfg: Config):
        super().__init__(cfg)
        # Override system prompt with boss version
        self.messages[0]["content"] = self._build_boss_system()

        # Build worker from config
        worker_key  = cfg.worker_api_key or cfg.api_key
        worker_url  = cfg.worker_base_url
        worker_model = cfg.worker_model
        self.worker = WorkerAgent(
            api_key=worker_key,
            base_url=worker_url,
            model=worker_model,
            boss_client=self.client,
        )

    def _build_boss_system(self) -> str:
        parts = [_BOSS_SYSTEM]
        if self._memory:
            parts.append(f"\n## 持久记忆\n{self._memory}")
        return "\n".join(parts)

    def _build_system(self) -> str:
        return self._build_boss_system()

    # ── override run_turn to use delegate tool ────────────────────────────────

    def run_turn(self, user_text: str, image_path: Optional[str] = None):
        from erniecli.api.client import StreamResult
        self.add_user_message(user_text, image_path=image_path)

        from erniecli.agent.loop import TurnRecord, _MAX_TOOL_ROUNDS
        turn = TurnRecord(idx=len(self._turns), user=user_text, assistant="")
        tool_rounds = 0
        tool_failures = 0

        for _round in range(_MAX_TOOL_ROUNDS):
            result = self._boss_stream_and_render()

            if not result.tool_calls:
                turn.assistant = result.content
                turn.tool_rounds = tool_rounds
                turn.tool_failures = tool_failures
                turn.response_chars = len(result.content)
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
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]),
                        },
                    }
                    for i, tc in enumerate(result.tool_calls)
                ],
            })

            tool_results: list[dict] = []
            for tc in result.tool_calls:
                name = tc["name"]
                args = tc["args"]

                if name == "delegate_to_worker":
                    task    = args.get("task", "")
                    context = args.get("context", "")
                    renderer.render_boss_dispatch(task, self.worker.model)
                    output  = self.worker.run_task(task, context)
                    renderer.render_boss_worker_done(output)
                    success = True
                    sources: list[dict] = []
                else:
                    # boss can also call tools directly if it wants
                    renderer.render_tool_call(name, args)
                    success, output, sources = execute_tool(
                        name, args, client=self.client
                    )
                    renderer.render_tool_result(name, output,
                                                success=success, sources=sources)
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

    def _boss_stream_and_render(self):
        """Stream with boss tool set (delegate + regular tools)."""
        stream_renderer = renderer.StreamRenderer()
        result = None

        gen = self.client.stream_chat(
            messages=self.messages,
            tools=_BOSS_TOOLS,
            search_enabled=self.search_enabled,
            mcp_servers=self.mcp_servers or None,
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
        return result
