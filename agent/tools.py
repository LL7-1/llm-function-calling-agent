"""两个工具函数：读 Excel、查 SQLite。

设计原则（这三条是面试时要讲的）：
1. 工具自己解释自己：返回的永远是结构化字符串，模型能读懂，不需要人猜。
2. 错误要能被模型消化：失败不抛异常，而是返回 ok=false + 错误类型，
   让模型知道"下一步该干什么"（换参数、换文件、还是直接告诉用户做不到）。
3. 只读：SQL 只允许 SELECT / WITH，其余一律拒绝。Agent 能动手，但不能乱动。
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

# 工具失败的类型，故意收成四类（对应"四类失败各有兜底"的设计）
ERR_FILE_NOT_FOUND = "file_not_found"
ERR_BAD_ARGS = "bad_args"
ERR_FORBIDDEN_SQL = "forbidden_sql"
ERR_TOOL_CRASH = "tool_crash"


def _ok(data: str) -> str:
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False)


def _err(err_type: str, message: str, hint: str = "") -> str:
    payload = {"ok": False, "error_type": err_type, "message": message}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, ensure_ascii=False)


# --------------------------------------------------------------------------
# 工具 1：读 Excel
# --------------------------------------------------------------------------
def read_excel(file_path: str, sheet_name: str | None = None, max_rows: int = 20) -> str:
    """把 Excel 的一个 sheet 读成文本表格，供模型阅读。"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return _err(ERR_TOOL_CRASH, "缺少 openpyxl 依赖", "执行 pip install openpyxl")

    path = Path(file_path)
    if not path.exists():
        # 让它去 data/ 下面找同名文件，避免模型乱编路径
        candidates = list(path.parent.glob("*.xlsx")) if path.parent.exists() else []
        hint = "可用的 Excel 文件：" + ", ".join(c.name for c in candidates) if candidates else ""
        return _err(ERR_FILE_NOT_FOUND, f"文件不存在：{file_path}", hint)

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        return _err(ERR_TOOL_CRASH, f"打不开文件：{exc}", "确认它是 .xlsx 且没有加密")

    sheets = wb.sheetnames
    target = sheet_name or sheets[0]
    if target not in sheets:
        wb.close()
        return _err(ERR_BAD_ARGS, f"没有这个 sheet：{target}", "可用的 sheet：" + ", ".join(sheets))

    ws = wb[target]
    rows: list[list[str]] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= max_rows:
            break
        rows.append(["" if v is None else str(v) for v in row])
    wb.close()

    if not rows:
        return _ok(f"sheet「{target}」是空的")

    # 用 markdown 表格返回：模型对表格格式理解最稳
    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(["---"] * len(header)) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in body]

    head = f"文件：{path.name}　sheet：{target}　总 sheet 数：{len(sheets)}（{', '.join(sheets)}）"
    tail = "" if len(rows) < max_rows else f"\n（只返回前 {max_rows} 行）"
    return _ok(head + "\n" + "\n".join(lines) + tail)


# --------------------------------------------------------------------------
# 工具 2：查 SQLite（只读）
# --------------------------------------------------------------------------
_READONLY = ("select", "with", "pragma", "explain")
_DANGEROUS = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|vacuum)\b", re.I)


def query_sqlite(db_path: str, sql: str, max_rows: int = 50) -> str:
    """执行只读 SQL 并返回结果表。写操作一律拒绝。"""
    path = Path(db_path)
    if not path.exists():
        candidates = list(path.parent.glob("*.db")) if path.parent.exists() else []
        hint = "可用的数据库：" + ", ".join(c.name for c in candidates) if candidates else ""
        return _err(ERR_FILE_NOT_FOUND, f"数据库不存在：{db_path}", hint)

    stmt = (sql or "").strip().rstrip(";").strip()
    if not stmt:
        return _err(ERR_BAD_ARGS, "SQL 为空")

    first = stmt.split()[0].lower()
    if first not in _READONLY or _DANGEROUS.search(stmt):
        return _err(
            ERR_FORBIDDEN_SQL,
            "只允许只读查询（SELECT / WITH），拒绝执行写操作",
            "需要改数据请走人工流程；查询请重写成 SELECT 语句",
        )
    if ";" in stmt:
        return _err(ERR_BAD_ARGS, "一次只能执行一条语句", "去掉多余的分号后再试")

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(stmt)
        rows = cur.fetchmany(max_rows)
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return _err(ERR_TOOL_CRASH, f"SQL 执行失败：{exc}", "检查表名、字段名是否正确，可先查表结构")

    if not cols:
        return _ok("查询没有返回列")
    lines = ["| " + " | ".join(cols) + " |",
             "| " + " | ".join(["---"] * len(cols)) + " |"]
    lines += ["| " + " | ".join("" if r[c] is None else str(r[c]) for c in cols) + " |" for r in rows]
    return _ok(f"共返回 {len(rows)} 行（上限 {max_rows}）\n" + "\n".join(lines))


# --------------------------------------------------------------------------
# 给模型看的工具说明书（function calling 的 schema）
# --------------------------------------------------------------------------
TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "read_excel",
            "description": "读取 Excel 文件里某个 sheet 的前若干行，以文本表格返回。用于查看订单、名单等结构化数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Excel 文件路径，例如 data/sales.xlsx"},
                    "sheet_name": {"type": "string", "description": "sheet 名称；不填则读第一个"},
                    "max_rows": {"type": "integer", "description": "最多返回多少行，默认 20"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_sqlite",
            "description": "对 SQLite 数据库执行只读查询（仅 SELECT / WITH），返回结果表。用于统计、筛选、聚合。",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "数据库路径，例如 data/demo.db"},
                    "sql": {"type": "string", "description": "一条只读 SQL 语句"},
                    "max_rows": {"type": "integer", "description": "最多返回多少行，默认 50"},
                },
                "required": ["db_path", "sql"],
            },
        },
    },
]

# 名字 → 函数，Agent 循环里按名字查表
TOOL_REGISTRY = {
    "read_excel": read_excel,
    "query_sqlite": query_sqlite,
}


def dispatch(name: str, arguments: dict) -> str:
    """按名字调用工具。参数不合法时返回错误而不是崩掉。"""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return _err(ERR_BAD_ARGS, f"没有这个工具：{name}", "可用工具：" + ", ".join(TOOL_REGISTRY))
    try:
        return fn(**arguments)
    except TypeError as exc:
        return _err(ERR_BAD_ARGS, f"参数不匹配：{exc}")
    except Exception as exc:  # noqa: BLE001
        return _err(ERR_TOOL_CRASH, f"工具执行异常：{exc}")
