"""Agent 循环的离线测试：用一个假的模型桩驱动工具调用，不联网、不花钱。

为什么值得写这层测试：真实模型的行为不可控，但**循环本身的正确性必须可验证**——
它要保证三件事：工具结果被正确回灌、工具报错不中断、步数用尽能体面退出。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.loop import Agent  # noqa: E402

DB = str(ROOT / "data" / "demo.db")


class _Fn:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, idx: int, name: str, arguments: str):
        self.id = f"call_{idx}"
        self.type = "function"
        self.function = _Fn(name, arguments)


class _Msg:
    def __init__(self, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeLLM:
    """按脚本依次返回消息，模拟模型的决策序列。"""

    def __init__(self, script):
        self.script = list(script)
        self.seen: list[list[dict]] = []

    def chat(self, messages, tools=None):
        self.seen.append(list(messages))
        return self.script.pop(0)


def test_loop_executes_tool_then_answers():
    sql = "SELECT COUNT(*) AS n FROM orders"
    llm = FakeLLM([
        _Msg(tool_calls=[_ToolCall(1, "query_sqlite", json.dumps({"db_path": DB, "sql": sql}))]),
        _Msg(content="共 60 条订单。"),
    ])
    bot = Agent(llm=llm, verbose=False)
    answer = bot.run("一共有多少条订单？")

    assert answer == "共 60 条订单。"
    assert len(bot.trace) == 1
    assert bot.trace[0]["tool"] == "query_sqlite"
    assert json.loads(bot.trace[0]["result"])["ok"] is True


def test_loop_survives_tool_error():
    """工具报错时，循环必须继续，并把错误作为下一步的输入。"""
    llm = FakeLLM([
        _Msg(tool_calls=[_ToolCall(1, "query_sqlite", json.dumps({"db_path": DB, "sql": "DROP TABLE orders"}))]),
        _Msg(content="我不能执行删除操作，只能查询。"),
    ])
    bot = Agent(llm=llm, verbose=False)
    answer = bot.run("把订单表删了")

    assert "不能" in answer
    result = json.loads(bot.trace[0]["result"])
    assert result["ok"] is False
    assert result["error_type"] == "forbidden_sql"
    # 第二轮请求里必须带着 tool 消息，否则模型不知道刚才发生了什么
    assert any(m.get("role") == "tool" for m in llm.seen[1])


def test_loop_stops_when_steps_exhausted():
    """模型一直调工具不停 → 不能死循环，要在 max_steps 处退出。"""
    call = _Msg(tool_calls=[_ToolCall(1, "query_sqlite", json.dumps({"db_path": DB, "sql": "SELECT 1"}))])
    bot = Agent(llm=FakeLLM([call] * 10), max_steps=3, verbose=False)
    answer = bot.run("一直查下去")
    assert "3" in answer
    assert len(bot.trace) == 3


def test_loop_handles_bad_json_args():
    """模型给出非 JSON 参数时不能崩，应当当成空参数交给分发器报错。"""
    llm = FakeLLM([
        _Msg(tool_calls=[_ToolCall(1, "read_excel", "{这不是JSON")]),
        _Msg(content="读不了，参数有问题。"),
    ])
    bot = Agent(llm=llm, verbose=False)
    assert bot.run("读一下表") == "读不了，参数有问题。"
    assert json.loads(bot.trace[0]["result"])["ok"] is False
