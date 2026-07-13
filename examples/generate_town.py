import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ese import WorldBuilder

DB_PATH = "examples/town_world.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

(
    WorldBuilder()
    .add_good(1, "food", "food", 1)
    .add_good(2, "tool", "raw_material", 1)
    .add_firm(
        101,
        1000.0,
        capacity=50.0,
        strategy_label="farm",
        inventory={1: 20.0, 2: 5.0},
        employees=[1, 2, 3],
    )
    .add_firm(
        102,
        1000.0,
        capacity=30.0,
        strategy_label="workshop",
        inventory={1: 10.0, 2: 15.0},
        employees=[4, 5],
    )
    .add_household(
        1,
        60.0,
        labor_ask_price=6.0,
        is_employed=True,
        employer_firm_id=101,
        inventory={1: 2.5},
    )
    .add_household(
        2,
        70.0,
        labor_ask_price=7.0,
        is_employed=True,
        employer_firm_id=101,
        inventory={1: 3.0},
    )
    .add_household(
        3,
        80.0,
        labor_ask_price=8.0,
        is_employed=True,
        employer_firm_id=101,
        inventory={1: 3.5},
    )
    .add_household(
        4,
        90.0,
        labor_ask_price=9.0,
        is_employed=True,
        employer_firm_id=102,
        inventory={1: 4.0},
    )
    .add_household(
        5,
        100.0,
        labor_ask_price=10.0,
        is_employed=True,
        employer_firm_id=102,
        inventory={1: 4.5},
    )
    .add_household(6, 110.0, labor_ask_price=11.0, inventory={1: 5.0})
    .add_household(7, 120.0, labor_ask_price=12.0, inventory={1: 5.5})
    .add_household(8, 130.0, labor_ask_price=13.0, inventory={1: 6.0})
    .add_household(9, 140.0, labor_ask_price=14.0, inventory={1: 6.5})
    .add_household(10, 150.0, labor_ask_price=15.0, inventory={1: 7.0})
    .add_government(201, 2000.0, tax_rate=0.1, unemployment_benefit=2.0)
    .save(DB_PATH)
)

print(f"Created {DB_PATH}")
