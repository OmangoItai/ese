import sqlite3
import threading
from typing import Dict, List, Optional

from core.entities import (
    Firm,
    Good,
    Government,
    Household,
    Order,
    OrderSide,
    WorldState,
)

VALID_GOOD_TYPES = {"food", "labor", "capital", "consumer", "raw_material"}


class Sequence:
    def __init__(self):
        self._n = 0
        self._lock = threading.Lock()

    def next(self) -> str:
        with self._lock:
            self._n += 1
            return f"order_{self._n}"


class OrderFactory:
    def __init__(self, id_seq: Sequence):
        self._seq = id_seq

    def from_params(
        self,
        *,
        seller_id: int,
        buyer_id: int,
        good_id: int,
        quantity: float,
        price: float,
        side=None,
        description: str = "",
    ) -> Order:
        if side is None:
            side = OrderSide.SUPPLY
        return Order(
            order_id=self._seq.next(),
            seller_id=seller_id,
            buyer_id=buyer_id,
            good_id=good_id,
            quantity=quantity,
            price=price,
            side=side,
            description=description,
        )

    def from_update(self, params: dict) -> Order:
        return self.from_params(**{k: v for k, v in params.items() if k != "order_id"})


class WorldLoader:
    @staticmethod
    def load(db_path: str) -> WorldState:
        conn = sqlite3.connect(db_path)
        try:
            c = conn.cursor()

            goods: Dict[int, Good] = {}
            c.execute("SELECT good_id, name, good_type, delivery_lag FROM goods")
            for row in c.fetchall():
                good_id, name, good_type, delivery_lag = row
                assert delivery_lag >= 1, (
                    f"Good {good_id}: delivery_lag must be >= 1, got {delivery_lag}"
                )
                assert good_type in VALID_GOOD_TYPES, (
                    f"Good {good_id}: invalid good_type '{good_type}'"
                )
                goods[good_id] = Good(
                    good_id=good_id,
                    name=name,
                    good_type=good_type,
                    delivery_lag=delivery_lag,
                )

            firms: Dict[int, Firm] = {}
            c.execute(
                "SELECT id, cash, capacity, collateral, is_active, labels FROM firms"
            )
            cols = [d[0] for d in c.description]
            for row in c.fetchall():
                row_dict = dict(zip(cols, row))
                fid = row_dict["id"]
                kwargs = {
                    "id": fid,
                    "cash": float(row_dict["cash"]),
                    "capacity": float(row_dict["capacity"]),
                    "collateral": float(row_dict["collateral"]),
                    "is_active": bool(row_dict["is_active"]),
                }
                if "labels" in cols:
                    kwargs["labels"] = row_dict["labels"].split(",")
                firms[fid] = Firm(**kwargs)

            c.execute("SELECT firm_id, good_id, quantity FROM firm_inventory")
            for row in c.fetchall():
                firm_id, good_id, quantity = row
                if firm_id in firms:
                    firms[firm_id].inventory[good_id] = float(quantity)

            c.execute("SELECT firm_id, household_id FROM firm_employees")
            for row in c.fetchall():
                firm_id, household_id = row
                if firm_id in firms:
                    firms[firm_id].employees.append(household_id)

            households: Dict[int, Household] = {}
            c.execute(
                "SELECT id, cash, reservation_wage, is_employed, "
                "employer_firm_id, unemployment_ticks, labels FROM households"
            )
            cols = [d[0] for d in c.description]
            for row in c.fetchall():
                row_dict = dict(zip(cols, row))
                hid = row_dict["id"]
                kwargs = {
                    "id": hid,
                    "cash": float(row_dict["cash"]),
                    "reservation_wage": float(row_dict["reservation_wage"]),
                    "is_employed": bool(row_dict["is_employed"]),
                    "employer_firm_id": row_dict["employer_firm_id"],
                    "unemployment_ticks": row_dict["unemployment_ticks"],
                }
                if "labels" in cols:
                    kwargs["labels"] = row_dict["labels"].split(",")
                households[hid] = Household(**kwargs)

            c.execute("SELECT household_id, good_id, quantity FROM household_inventory")
            for row in c.fetchall():
                household_id, good_id, quantity = row
                if household_id in households:
                    households[household_id].inventory[good_id] = float(quantity)

            governments: Dict[int, Government] = {}
            c.execute(
                "SELECT id, cash, tax_rate, money_supply, unemployment_benefit, labels "
                "FROM governments"
            )
            cols = [d[0] for d in c.description]
            for row in c.fetchall():
                row_dict = dict(zip(cols, row))
                gid = row_dict["id"]
                kwargs = {
                    "id": gid,
                    "cash": float(row_dict["cash"]),
                    "tax_rate": float(row_dict["tax_rate"]),
                    "money_supply": float(row_dict["money_supply"]),
                    "unemployment_benefit": float(row_dict["unemployment_benefit"]),
                }
                if "labels" in cols:
                    kwargs["labels"] = row_dict["labels"].split(",")
                governments[gid] = Government(**kwargs)

            if len(governments) != 1:
                raise ValueError(
                    f"Expected exactly 1 government, got {len(governments)}. "
                    "Multi-government is not yet supported (no jurisdiction "
                    "assignment for firms/households)."
                )

            firm_ids = set(firms.keys())
            hh_ids = set(households.keys())
            overlap = firm_ids & hh_ids
            if overlap:
                raise ValueError(
                    f"Firm and Household ID collision: {overlap}. "
                    "All entity(Household, Firm, Government) IDs must be globally unique."
                )

            return WorldState(
                tick=0,
                firms=firms,
                households=households,
                governments=governments,
                goods=goods,
                pending_orders=[],
                all_orders={},
                collateral_pool={},
            )
        finally:
            conn.close()


class WorldBuilder:
    def __init__(self):
        self._goods: Dict[int, Good] = {}
        self._firms: Dict[int, Firm] = {}
        self._firm_inventory: list[tuple] = []
        self._firm_employees: list[tuple] = []
        self._households: Dict[int, Household] = {}
        self._household_inventory: list[tuple] = []
        self._governments: Dict[int, Government] = {}

    def add_good(
        self, good_id: int, name: str, good_type: str, delivery_lag: int = 1
    ) -> "WorldBuilder":
        self._goods[good_id] = Good(
            good_id=good_id,
            name=name,
            good_type=good_type,
            delivery_lag=delivery_lag,
        )
        return self

    def add_firm(
        self,
        id: int,
        cash: float,
        *,
        capacity: float = 0,
        labels: Optional[List[str]] = None,
        inventory: Optional[Dict[int, float]] = None,
        employees: Optional[list[int]] = None,
    ) -> "WorldBuilder":
        if labels is None:
            labels = ["default"]
        firm = Firm(
            id=id,
            cash=cash,
            capacity=capacity,
            labels=labels,
        )
        if inventory:
            for good_id, qty in inventory.items():
                firm.inventory[good_id] = float(qty)
                self._firm_inventory.append((id, good_id, float(qty)))
        if employees:
            firm.employees = list(employees)
            for eid in employees:
                self._firm_employees.append((id, eid))
        self._firms[id] = firm
        return self

    def add_household(
        self,
        id: int,
        cash: float,
        *,
        reservation_wage: float = 0,
        is_employed: bool = False,
        employer_firm_id: Optional[int] = None,
        inventory: Optional[Dict[int, float]] = None,
        labels: Optional[List[str]] = None,
    ) -> "WorldBuilder":
        if labels is None:
            labels = ["default"]
        hh = Household(
            id=id,
            cash=cash,
            reservation_wage=reservation_wage,
            is_employed=is_employed,
            employer_firm_id=employer_firm_id,
            labels=labels,
        )
        if inventory:
            for good_id, qty in inventory.items():
                hh.inventory[good_id] = float(qty)
                self._household_inventory.append((id, good_id, float(qty)))
        self._households[id] = hh
        return self

    def add_government(
        self,
        id: int,
        cash: float,
        *,
        tax_rate: float = 0,
        unemployment_benefit: float = 0,
        labels: Optional[List[str]] = None,
    ) -> "WorldBuilder":
        if labels is None:
            labels = ["default"]
        self._governments[id] = Government(
            id=id,
            cash=cash,
            tax_rate=tax_rate,
            unemployment_benefit=unemployment_benefit,
            labels=labels,
        )
        return self

    def build(self) -> WorldState:
        return WorldState(
            tick=0,
            firms=dict(self._firms),
            households=dict(self._households),
            governments=dict(self._governments),
            goods=dict(self._goods),
        )

    def save(self, db_path: str) -> None:
        conn = sqlite3.connect(db_path)
        try:
            c = conn.cursor()

            for table in [
                "goods",
                "firms",
                "firm_inventory",
                "firm_employees",
                "households",
                "household_inventory",
                "governments",
            ]:
                c.execute(f"DROP TABLE IF EXISTS {table}")

            c.execute(
                """CREATE TABLE goods (
                    good_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    good_type TEXT NOT NULL,
                    delivery_lag INTEGER NOT NULL)"""
            )
            c.execute(
                """CREATE TABLE firms (
                    id INTEGER PRIMARY KEY,
                    cash REAL NOT NULL,
                    capacity REAL NOT NULL DEFAULT 0.0,
                    collateral REAL NOT NULL DEFAULT 0.0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    labels TEXT NOT NULL DEFAULT 'default')"""
            )
            c.execute(
                """CREATE TABLE firm_inventory (
                    firm_id INTEGER NOT NULL,
                    good_id INTEGER NOT NULL,
                    quantity REAL NOT NULL DEFAULT 0.0,
                    PRIMARY KEY (firm_id, good_id))"""
            )
            c.execute(
                """CREATE TABLE firm_employees (
                    firm_id INTEGER NOT NULL,
                    household_id INTEGER NOT NULL,
                    PRIMARY KEY (firm_id, household_id))"""
            )
            c.execute(
                """CREATE TABLE households (
                    id INTEGER PRIMARY KEY,
                    cash REAL NOT NULL,
                    reservation_wage REAL NOT NULL DEFAULT 0.0,
                    is_employed INTEGER NOT NULL DEFAULT 0,
                    employer_firm_id INTEGER,
                    unemployment_ticks INTEGER NOT NULL DEFAULT 0,
                    labels TEXT NOT NULL DEFAULT 'default')"""
            )
            c.execute(
                """CREATE TABLE household_inventory (
                    household_id INTEGER NOT NULL,
                    good_id INTEGER NOT NULL,
                    quantity REAL NOT NULL DEFAULT 0.0,
                    PRIMARY KEY (household_id, good_id))"""
            )
            c.execute(
                """CREATE TABLE governments (
                    id INTEGER PRIMARY KEY,
                    cash REAL NOT NULL,
                    tax_rate REAL NOT NULL DEFAULT 0.0,
                    money_supply REAL NOT NULL DEFAULT 0.0,
                    unemployment_benefit REAL NOT NULL DEFAULT 0.0,
                    labels TEXT NOT NULL DEFAULT 'default')"""
            )

            for g in self._goods.values():
                c.execute(
                    "INSERT INTO goods VALUES (?,?,?,?)",
                    (g.good_id, g.name, g.good_type, g.delivery_lag),
                )

            for f in self._firms.values():
                c.execute(
                    "INSERT INTO firms (id, cash, capacity, collateral, is_active, labels) VALUES (?,?,?,?,?,?)",
                    (
                        f.id,
                        f.cash,
                        f.capacity,
                        f.collateral,
                        int(f.is_active),
                        ",".join(f.labels),
                    ),
                )
                for inv in self._firm_inventory:
                    if inv[0] == f.id:
                        c.execute("INSERT INTO firm_inventory VALUES (?,?,?)", inv)
                for emp in self._firm_employees:
                    if emp[0] == f.id:
                        c.execute("INSERT INTO firm_employees VALUES (?,?)", emp)

            for hh in self._households.values():
                c.execute(
                    "INSERT INTO households (id, cash, reservation_wage, is_employed, "
                    "employer_firm_id, unemployment_ticks, labels) VALUES (?,?,?,?,?,?,?)",
                    (
                        hh.id,
                        hh.cash,
                        hh.reservation_wage,
                        int(hh.is_employed),
                        hh.employer_firm_id,
                        hh.unemployment_ticks,
                        ",".join(hh.labels),
                    ),
                )
                for inv in self._household_inventory:
                    if inv[0] == hh.id:
                        c.execute("INSERT INTO household_inventory VALUES (?,?,?)", inv)

            for gov in self._governments.values():
                c.execute(
                    "INSERT INTO governments (id, cash, tax_rate, money_supply, "
                    "unemployment_benefit, labels) VALUES (?,?,?,?,?,?)",
                    (
                        gov.id,
                        gov.cash,
                        gov.tax_rate,
                        gov.money_supply,
                        gov.unemployment_benefit,
                        ",".join(gov.labels),
                    ),
                )

            conn.commit()
        finally:
            conn.close()
