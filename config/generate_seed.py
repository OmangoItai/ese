"""Generate seed_world.db: 2 firms, 5 households, 3 goods, 1 government."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "seed_world.db")

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

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
    is_active INTEGER NOT NULL DEFAULT 1
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
    unemployment_ticks INTEGER NOT NULL DEFAULT 0
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
    unemployment_benefit REAL NOT NULL DEFAULT 0.0
)
""")

# Goods: 1=bread(food), 2=labor, 3=iron(raw_material)
c.executemany(
    "INSERT INTO goods VALUES (?,?,?,?)",
    [
        (1, "bread", "food", 1),
        (2, "labor", "labor", 1),
        (3, "iron", "raw_material", 2),
    ],
)

# Firms
c.executemany(
    "INSERT INTO firms VALUES (?,?,?,?,?)",
    [
        (1, 5000.0, 100.0, 0.0, 1),  # bakery
        (2, 8000.0, 200.0, 0.0, 1),  # iron mine
    ],
)

# Firm inventories
c.executemany(
    "INSERT INTO firm_inventory VALUES (?,?,?)",
    [
        (1, 1, 50.0),  # bakery has 50 bread
        (1, 3, 10.0),  # bakery has 10 iron (raw material)
        (2, 1, 5.0),  # iron mine has 5 bread
        (2, 3, 100.0),  # iron mine has 100 iron
    ],
)

# Households
c.executemany(
    "INSERT INTO households VALUES (?,?,?,?,?,?)",
    [
        (1, 200.0, 10.0, 1, 1, 0),  # employed at firm 1
        (2, 200.0, 8.0, 1, 2, 0),  # employed at firm 2
        (3, 150.0, 10.0, 0, None, 0),  # unemployed
        (4, 300.0, 12.0, 1, 1, 0),  # employed at firm 1
        (5, 250.0, 9.0, 0, None, 2),  # unemployed for 2 ticks
    ],
)

# Household inventories (start with some bread)
c.executemany(
    "INSERT INTO household_inventory VALUES (?,?,?)",
    [
        (1, 1, 20.0),
        (2, 1, 15.0),
        (3, 1, 10.0),
        (4, 1, 25.0),
        (5, 1, 12.0),
    ],
)

# Firm employees
c.executemany(
    "INSERT INTO firm_employees VALUES (?,?)",
    [
        (1, 1),
        (1, 4),
        (2, 2),
    ],
)

# Government
c.execute(
    "INSERT INTO governments VALUES (?,?,?,?,?)",
    (1, 50000.0, 0.1, 0.0, 5.0),
)

conn.commit()
conn.close()
print(f"Created {DB_PATH}")
