"""命令行入口。

用法：
  python main.py --selftest              # 不联网，验证两个工具是否正常
  python main.py                         # 交互式提问
  python main.py --q "上月华东销售额多少"  # 单次提问
  python main.py --q "..." --provider zhipu
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from agent.loop import Agent
from agent.tools import query_sqlite, read_excel

load_dotenv()  # 读 .env 里的 API Key


def selftest() -> int:
    """不花 API 额度，把两个工具的四种结果都跑一遍。"""
    print("=" * 60)
    print("工具自检（不需要 API Key）")
    print("=" * 60)

    cases = [
        ("读 Excel · 正常", lambda: read_excel("data/sales.xlsx", max_rows=4)),
        ("读 Excel · sheet 不存在", lambda: read_excel("data/sales.xlsx", sheet_name="不存在的表")),
        ("读 Excel · 文件不存在", lambda: read_excel("data/nope.xlsx")),
        ("查库 · 正常", lambda: query_sqlite("data/demo.db", "SELECT region, SUM(amount) AS 金额 FROM orders GROUP BY region ORDER BY 金额 DESC")),
        ("查库 · 拒绝写操作", lambda: query_sqlite("data/demo.db", "DELETE FROM orders")),
        ("查库 · 语法错", lambda: query_sqlite("data/demo.db", "SELECT * FROM 没有这张表")),
    ]

    for title, fn in cases:
        print(f"\n--- {title}")
        print(fn())

    print("\n" + "=" * 60)
    print("自检结束。上面每条都应有 ok=true 或明确的 error_type；")
    print("只要没有抛异常、没崩，这个 Agent 的骨架就是通的。")
    return 0


def ask(question: str, provider: str | None) -> None:
    try:
        bot = Agent(llm=None if provider is None else _make_llm(provider))
    except SystemExit as exc:
        print(exc)
        return
    print(f"\n问题：{question}\n" + "-" * 60)
    print("\n答案：" + bot.run(question))
    if bot.trace:
        print(f"\n（共调用工具 {len(bot.trace)} 次）")


def _make_llm(provider: str):
    from agent.llm import LLM

    return LLM(provider=provider)


def main() -> int:
    ap = argparse.ArgumentParser(description="能读 Excel、查数据库的最小 Agent")
    ap.add_argument("--q", "--question", dest="question", help="要问的问题")
    ap.add_argument("--provider", choices=["deepseek", "zhipu", "openai"], help="用哪家大模型")
    ap.add_argument("--selftest", action="store_true", help="不联网，自检工具")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.question:
        ask(args.question, args.provider)
        return 0

    print("输入问题，回车提问；输入 q 退出。")
    while True:
        try:
            q = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if q.lower() in {"q", "quit", "exit"}:
            break
        if q:
            ask(q, args.provider)
    return 0


if __name__ == "__main__":
    sys.exit(main())
