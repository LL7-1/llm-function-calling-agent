"""工具层单元测试：不联网、不花额度，验证 4 类失败都有明确返回。

跑法：python -m pytest -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.tools import dispatch, query_sqlite, read_excel  # noqa: E402

XLSX = str(ROOT / "data" / "sales.xlsx")
DB = str(ROOT / "data" / "demo.db")


def load(raw: str) -> dict:
    return json.loads(raw)


# ---------------------------------------------------------------- 读 Excel
def test_read_excel_ok():
    out = load(read_excel(XLSX, max_rows=5))
    assert out["ok"] is True
    assert "订单明细" in out["data"]
    assert "|" in out["data"]           # 返回的是表格
    assert "只返回前 5 行" in out["data"]  # 截断要有提示


def test_read_excel_bad_sheet():
    out = load(read_excel(XLSX, sheet_name="不存在"))
    assert out["ok"] is False
    assert out["error_type"] == "bad_args"
    assert "订单明细" in out["hint"]     # 提示里要列出可用 sheet


def test_read_excel_missing_file():
    out = load(read_excel("data/没有这个文件.xlsx"))
    assert out["ok"] is False
    assert out["error_type"] == "file_not_found"


# ---------------------------------------------------------------- 查数据库
def test_query_ok():
    sql = "SELECT region, SUM(amount) AS total FROM orders GROUP BY region ORDER BY total DESC"
    out = load(query_sqlite(DB, sql))
    assert out["ok"] is True
    for region in ("华东", "华北", "华南", "西南"):
        assert region in out["data"]


def test_query_rejects_write():
    for sql in ("DELETE FROM orders", "UPDATE orders SET qty=0", "DROP TABLE orders"):
        out = load(query_sqlite(DB, sql))
        assert out["ok"] is False
        assert out["error_type"] == "forbidden_sql"


def test_query_rejects_multi_statement():
    out = load(query_sqlite(DB, "SELECT 1; SELECT 2"))
    # 分号后还有内容 → 要么被判多语句，要么被写操作规则拦住，都不能执行成功
    assert out["ok"] is False


def test_query_bad_table():
    out = load(query_sqlite(DB, "SELECT * FROM 没有这张表"))
    assert out["ok"] is False
    assert out["error_type"] == "tool_crash"


def test_query_missing_db():
    out = load(query_sqlite("data/none.db", "SELECT 1"))
    assert out["ok"] is False
    assert out["error_type"] == "file_not_found"


# ---------------------------------------------------------------- 分发器
def test_dispatch_unknown_tool():
    out = load(dispatch("send_email", {}))
    assert out["ok"] is False
    assert out["error_type"] == "bad_args"


def test_dispatch_bad_params():
    out = load(dispatch("read_excel", {"什么参数": 1}))
    assert out["ok"] is False
    assert out["error_type"] == "bad_args"
