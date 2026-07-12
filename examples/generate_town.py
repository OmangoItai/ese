# generate_town_seed.py
import sqlite3
import os

DB_PATH = "town_world.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# ---- 建表（完全匹配 core/entities 结构） ----
c.execute("""
CREATE TABLE goods (
    good_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    good_type TEXT NOT NULL CHECK(good_type IN ('food','labor','capital','consumer','raw_material')),
    delivery_lag INTEGER NOT NULL CHECK(delivery_lag >= 1)
)
""")

c.execute("""
CREATE TABLE firms (
    id INTEGER PRIMARY KEY,
    cash REAL NOT NULL,
    capacity REAL NOT NULL DEFAULT 0.0,
    collateral REAL NOT NULL DEFAULT 0.0,
    is_active INTEGER NOT NULL DEFAULT 1,
    strategy_label TEXT NOT NULL DEFAULT 'default'
)
""")

c.execute("""
CREATE TABLE firm_inventory (
    firm_id INTEGER NOT NULL,
    good_id INTEGER NOT NULL,
    quantity REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (firm_id, good_id),
    FOREIGN KEY (firm_id) REFERENCES firms(id),
    FOREIGN KEY (good_id) REFERENCES goods(good_id)
)
""")

c.execute("""
CREATE TABLE firm_employees (
    firm_id INTEGER NOT NULL,
    household_id INTEGER NOT NULL,
    PRIMARY KEY (firm_id, household_id),
    FOREIGN KEY (firm_id) REFERENCES firms(id)
)
""")

c.execute("""
CREATE TABLE households (
    id INTEGER PRIMARY KEY,
    cash REAL NOT NULL,
    labor_ask_price REAL NOT NULL DEFAULT 0.0,
    is_employed INTEGER NOT NULL DEFAULT 0,
    employer_firm_id INTEGER,
    unemployment_ticks INTEGER NOT NULL DEFAULT 0,
    strategy_label TEXT NOT NULL DEFAULT 'default'
)
""")

c.execute("""
CREATE TABLE household_inventory (
    household_id INTEGER NOT NULL,
    good_id INTEGER NOT NULL,
    quantity REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (household_id, good_id),
    FOREIGN KEY (household_id) REFERENCES households(id),
    FOREIGN KEY (good_id) REFERENCES goods(good_id)
)
""")

c.execute("""
CREATE TABLE governments (
    id INTEGER PRIMARY KEY,
    cash REAL NOT NULL,
    tax_rate REAL NOT NULL DEFAULT 0.0,
    money_supply REAL NOT NULL DEFAULT 0.0,
    unemployment_benefit REAL NOT NULL DEFAULT 0.0,
    strategy_label TEXT NOT NULL DEFAULT 'default'
)
""")

# ---- 商品 ----
c.executemany(
    "INSERT INTO goods VALUES (?,?,?,?)",
    [
        (1, "food", "food", 1),  # 食物，交付延迟1 tick
        (2, "tool", "raw_material", 1),  # 工具（中间品）
    ],
)

# ---- 企业 ----
c.executemany(
    "INSERT INTO firms (id, cash, capacity, collateral, is_active, strategy_label) VALUES (?,?,?,?,?,?)",
    [
        (101, 1000.0, 50.0, 0.0, 1, "farm"),  # 农场：生产食物，需要工具
        (102, 1000.0, 30.0, 0.0, 1, "workshop"),  # 工坊：生产工具，需要食物作为工人报酬
    ],
)

# ---- 企业库存 ----
c.executemany(
    "INSERT INTO firm_inventory VALUES (?,?,?)",
    [
        (101, 1, 20.0),  # 农场初始存粮20
        (101, 2, 5.0),  # 农场有工具5（用于生产）
        (102, 1, 10.0),  # 工坊有食物10
        (102, 2, 15.0),  # 工坊库存工具15
    ],
)

# ---- 家庭（10户） ----
households = []
for i in range(1, 11):
    cash = 50.0 + i * 10  # 不同初始现金
    labor = 5.0 + i  # 期望工资不同
    # 前5户已就业（分别去两家企业），后5户失业
    employed = 1 if i <= 5 else 0
    employer = 101 if i <= 3 else 102 if i <= 5 else None
    households.append((i, cash, labor, employed, employer, 0, "default"))
c.executemany(
    "INSERT INTO households (id, cash, labor_ask_price, is_employed, employer_firm_id, unemployment_ticks, strategy_label) VALUES (?,?,?,?,?,?,?)",
    households,
)

# ---- 家庭库存（每户有点食物） ----
for i in range(1, 11):
    c.execute(
        "INSERT INTO household_inventory VALUES (?,?,?)",
        (i, 1, 2.0 + i * 0.5),  # 每人2~7单位食物
    )

# ---- 企业雇佣关系 ----
c.executemany(
    "INSERT INTO firm_employees VALUES (?,?)",
    [
        (101, 1),
        (101, 2),
        (101, 3),  # 农场雇1,2,3
        (102, 4),
        (102, 5),  # 工坊雇4,5
    ],
)

# ---- 政府 ----
c.execute(
    "INSERT INTO governments (id, cash, tax_rate, money_supply, unemployment_benefit, strategy_label) VALUES (?,?,?,?,?,?)",
    (201, 2000.0, 0.1, 0.0, 2.0, "default"),  # 税率10%，失业金2
)

conn.commit()
conn.close()
print(f"Created {DB_PATH}")
