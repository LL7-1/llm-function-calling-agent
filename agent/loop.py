"""Agent 主循环：模型决定调哪个工具，代码负责执行并回灌结果。

这个循环只有一件事要保证：**不管工具返回什么，循环都必须能继续或体面结束。**
工具报错不中断对话，因为报错本身就是模型下一步决策的输入。
"""

from __future__ import annotations

import json

from .llm import LLM
from .tools import TOOL_SPECS, dispatch

SYSTEM_PROMPT = """你是一个数据查询助手，可以读 Excel 和查 SQLite 数据库来回答用户的问题。

规则：
1. 需要数据时必须调用工具拿真实结果，不要凭印象编造。
2. SQL 只写 SELECT，不允许改数据。
3. 工具返回 ok=false 时，先看 error_type：参数错就改参数重试一次；文件不存在就告诉用户有哪些可用文件；被拒绝的 SQL 就重写成查询。不要同一个错重复试两次以上。
4. 最后用中文回答，给出结论和依据（引用了哪些行/哪些字段）。
"""


class Agent:
    def __init__(self, llm: LLM | None = None, max_steps: int = 6, verbose: bool = True):
        self.llm = llm or LLM()
        self.max_steps = max_steps
        self.verbose = verbose
        self.trace: list[dict] = []

    def run(self, question: str) -> str:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        for step in range(1, self.max_steps + 1):
            msg = self.llm.chat(messages, tools=TOOL_SPECS)

            # 没有工具调用 → 这就是最终答案
            if not msg.tool_calls:
                if self.verbose:
                    print(f"[step {step}] 直接回答")
                return msg.content or "（模型没有返回内容）"

            # 把模型的决策原样记回上下文（协议要求，不能省）
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                name = tc.function.name
                raw = tc.function.arguments or "{}"
                # 模型给的不是 JSON 时不要崩，当成空参数处理
                try:
                    args = json.loads(raw)
                except json.JSONDecodeError:
                    args = {}
                result = dispatch(name, args)

                if self.verbose:
                    brief = ", ".join(f"{k}={v}" for k, v in args.items())
                    print(f"[step {step}] 调用 {name}({brief})")
                    print(f"           → {result[:120].replace(chr(10), ' ')}{'…' if len(result) > 120 else ''}")

                self.trace.append({"step": step, "tool": name, "args": args, "result": result})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        # 步数用尽：不给死循环，明确告诉用户
        return f"（已连续调用工具 {self.max_steps} 次仍未得出结论，先停下来，请把问题拆小一点）"
