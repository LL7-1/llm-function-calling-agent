"""生成示例数据：data/sales.xlsx 与 data/demo.db。

数据是编的，但结构照着真实业务来：订单有地区、产品、数量、金额、日期。
这样 Agent 才有东西可查，也方便你换成自己的数据。
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from openpyxl import Workbook

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)

REGIONS = ["华东", "华北", "华南", "西南"]
PRODUCTS = [
    ("P01", "智能标注平台·标准版", 12000),
    ("P02", "智能标注平台·专业版", 36000),
    ("P03", "数据质检服务", 8000),
    ("P04", "私有化部署包", 58000),
]

random.seed(42)  # 固定种子，保证每次生成的数据一样


def make_orders(n: int = 60):
    rows = []
    for i in range(1, n + 1):
        code, name, price = random.choice(PRODUCTS)
        qty = random.randint(1, 5)
        month = random.randint(1, 9)
        rows.append({
            "order_id": f"SO{2026000 + i}",
            "customer": f"客户{i:02d}",
            "region": random.choice(REGIONS),
            "product_code": code,
            "product_name": name,
            "qty": qty,
            "amount": price * qty,
            "order_date": f"2026-{month:02d}-{random.randint(1, 28):02d}",
        })
    return rows


def build_db(orders):
    db_path = DATA / "demo.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE products (
            product_code TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            unit_price   INTEGER NOT NULL
        );
        CREATE TABLE orders (
            order_id     TEXT PRIMARY KEY,
            customer     TEXT,
            region       TEXT,
            product_code TEXT REFERENCES products(product_code),
            qty          INTEGER,
            amount       INTEGER,
            order_date   TEXT
        );
        """
    )
    cur.executemany("INSERT INTO products VALUES (?,?,?)", PRODUCTS)
    cur.executemany(
        "INSERT INTO orders VALUES (:order_id,:customer,:region,:product_code,:qty,:amount,:order_date)",
        orders,
    )
    conn.commit()
    conn.close()
    return db_path


def build_excel(orders):
    wb = Workbook()

    ws = wb.active
    ws.title = "订单明细"
    headers = ["订单号", "客户", "地区", "产品编码", "产品名称", "数量", "金额", "下单日期"]
    ws.append(headers)
    for o in orders:
        ws.append([o["order_id"], o["customer"], o["region"], o["product_code"],
                   o["product_name"], o["qty"], o["amount"], o["order_date"]])

    ws2 = wb.create_sheet("产品价目")
    ws2.append(["产品编码", "产品名称", "单价"])
    for code, name, price in PRODUCTS:
        ws2.append([code, name, price])

    ws3 = wb.create_sheet("填表说明")
    ws3.append(["字段", "说明"])
    ws3.append(["地区", "华东 / 华北 / 华南 / 西南，四选一"])
    ws3.append(["金额", "单价 × 数量，单位元，含税"])
    ws3.append(["下单日期", "格式 YYYY-MM-DD"])

    xlsx = DATA / "sales.xlsx"
    wb.save(xlsx)
    return xlsx


if __name__ == "__main__":
    orders = make_orders()
    db = build_db(orders)
    xlsx = build_excel(orders)
    print(f"已生成：{xlsx}")
    print(f"已生成：{db}")
    print(f"订单 {len(orders)} 条，产品 {len(PRODUCTS)} 个，地区 {len(REGIONS)} 个")
