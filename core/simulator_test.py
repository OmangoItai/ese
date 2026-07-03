import os
import sqlite3
import tempfile

import pytest
import yaml

from core.clearing_house import ClearingHouse
from core.entities import Firm, Good, Government, Household, Order, WorldState
from core.ledger import Ledger
from core.noise import InformationFriction
from core.simulator import Simulator


def _make_temp_db(rows_dict: dict) -> str:
    """Create a temporary SQLite world DB and return the path.
    rows_dict keys: goods, firms, firm_inventory, firm_employees,
    households, household_inventory, governments.
    Each value is a list of tuples to executemany.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmppath = tmp.name
    tmp.close()
    conn = sqlite3.connect(tmppath)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE goods (
            good_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            good_type TEXT NOT NULL,
            delivery_lag INTEGER NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE firms (
            id INTEGER PRIMARY KEY, cash REAL NOT NULL,
            capacity REAL NOT NULL DEFAULT 0.0,
            collateral REAL NOT NULL DEFAULT 0.0,
            is_active INTEGER NOT NULL DEFAULT 1)"""
    )
    c.execute(
        """CREATE TABLE firm_inventory (
            firm_id INTEGER NOT NULL, good_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (firm_id, good_id))"""
    )
    c.execute(
        """CREATE TABLE firm_employees (
            firm_id INTEGER NOT NULL, household_id INTEGER NOT NULL,
            PRIMARY KEY (firm_id, household_id))"""
    )
    c.execute(
        """CREATE TABLE households (
            id INTEGER PRIMARY KEY, cash REAL NOT NULL,
            labor_ask_price REAL NOT NULL DEFAULT 0.0,
            is_employed INTEGER NOT NULL DEFAULT 0,
            employer_firm_id INTEGER,
            unemployment_ticks INTEGER NOT NULL DEFAULT 0)"""
    )
    c.execute(
        """CREATE TABLE household_inventory (
            household_id INTEGER NOT NULL, good_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (household_id, good_id))"""
    )
    c.execute(
        """CREATE TABLE governments (
            id INTEGER PRIMARY KEY, cash REAL NOT NULL,
            tax_rate REAL NOT NULL DEFAULT 0.0,
            money_supply REAL NOT NULL DEFAULT 0.0,
            unemployment_benefit REAL NOT NULL DEFAULT 0.0)"""
    )

    for table, rows in rows_dict.items():
        if table == "goods":
            c.executemany("INSERT INTO goods VALUES (?,?,?,?)", rows)
        elif table == "firms":
            c.executemany("INSERT INTO firms VALUES (?,?,?,?,?)", rows)
        elif table == "firm_inventory":
            c.executemany("INSERT INTO firm_inventory VALUES (?,?,?)", rows)
        elif table == "firm_employees":
            c.executemany("INSERT INTO firm_employees VALUES (?,?)", rows)
        elif table == "households":
            c.executemany("INSERT INTO households VALUES (?,?,?,?,?,?)", rows)
        elif table == "household_inventory":
            c.executemany("INSERT INTO household_inventory VALUES (?,?,?)", rows)
        elif table == "governments":
            c.executemany("INSERT INTO governments VALUES (?,?,?,?,?)", rows)

    conn.commit()
    conn.close()
    return tmppath


def _make_temp_config(config_dict: dict = None) -> str:
    if config_dict is None:
        config_dict = {
            "seed": 42,
            "base_collateral_ratio": 0.1,
            "noise_type": "none",
            "order_expire_ticks": 30,
            "fulfillment_window_ticks": 30,
            "n_ticks": 30,
            "noise_params": {"sigma": 0.1},
        }
    tmp = tempfile.NamedTemporaryFile(
        suffix=".yaml", mode="w", delete=False, encoding="utf-8"
    )
    yaml.dump(config_dict, tmp)
    tmppath = tmp.name
    tmp.close()
    return tmppath


def _make_mini_world_db() -> str:
    """2 firms, 5 households, 3 goods, 1 government — matches seed data."""
    return _make_temp_db(
        {
            "goods": [
                (1, "bread", "food", 1),
                (2, "labor", "labor", 1),
                (3, "iron", "raw_material", 2),
            ],
            "firms": [
                (1, 5000.0, 100.0, 0.0, 1),
                (2, 8000.0, 200.0, 0.0, 1),
            ],
            "firm_inventory": [
                (1, 1, 50.0),
                (1, 3, 10.0),
                (2, 1, 5.0),
                (2, 3, 100.0),
            ],
            "firm_employees": [
                (1, 101),
                (1, 104),
                (2, 102),
            ],
            "households": [
                (101, 200.0, 10.0, 1, 1, 0),
                (102, 200.0, 8.0, 1, 2, 0),
                (103, 150.0, 10.0, 0, None, 0),
                (104, 300.0, 12.0, 1, 1, 0),
                (105, 250.0, 9.0, 0, None, 2),
            ],
            "household_inventory": [
                (101, 1, 20.0),
                (102, 1, 15.0),
                (103, 1, 10.0),
                (104, 1, 25.0),
                (105, 1, 12.0),
            ],
            "governments": [
                (1, 50000.0, 0.1, 0.0, 5.0),
            ],
        }
    )


class TestLoadWorld:
    def test_world_state_matches_sqlite(self):
        db_path = _make_mini_world_db()
        ws = Simulator._load_world(db_path)
        try:
            assert ws.tick == 0
            assert len(ws.firms) == 2
            assert len(ws.households) == 5
            assert len(ws.governments) == 1
            assert len(ws.goods) == 3

            assert ws.firms[1].cash == 5000.0
            assert ws.firms[1].inventory.get(1) == 50.0
            assert ws.firms[1].inventory.get(3) == 10.0
            assert ws.firms[1].is_active is True
            assert ws.firms[1].employees == [101, 104]

            assert ws.firms[2].cash == 8000.0
            assert ws.firms[2].employees == [102]

            assert ws.households[101].cash == 200.0
            assert ws.households[101].labor_ask_price == 10.0
            assert ws.households[101].is_employed is True
            assert ws.households[101].employer_firm_id == 1
            assert ws.households[101].inventory.get(1) == 20.0

            assert ws.households[105].is_employed is False
            assert ws.households[105].unemployment_ticks == 2

            assert ws.governments[1].cash == 50000.0
            assert ws.governments[1].tax_rate == 0.1
            assert ws.governments[1].unemployment_benefit == 5.0

            assert ws.goods[1].good_type == "food"
            assert ws.goods[1].delivery_lag == 1
            assert ws.goods[2].good_type == "labor"
            assert ws.goods[3].good_type == "raw_material"
            assert ws.goods[3].delivery_lag == 2

            assert ws.supply_pool == []
            assert ws.demand_pool == []
            assert ws.pending_orders == []
            assert ws.all_orders == {}
            assert ws.collateral_pool == {}
        finally:
            os.unlink(db_path)

    def test_rejects_bad_delivery_lag(self):
        db_path = _make_temp_db(
            {
                "goods": [(1, "bad", "food", 0)],
                "firms": [],
                "households": [],
                "governments": [],
            }
        )
        try:
            with pytest.raises(AssertionError, match="delivery_lag"):
                Simulator._load_world(db_path)
        finally:
            os.unlink(db_path)

    def test_rejects_bad_good_type(self):
        db_path = _make_temp_db(
            {
                "goods": [(1, "bad", "invalid_type", 1)],
                "firms": [],
                "households": [],
                "governments": [],
            }
        )
        try:
            with pytest.raises(AssertionError, match="good_type"):
                Simulator._load_world(db_path)
        finally:
            os.unlink(db_path)

    def test_empty_world_loads(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [],
                "households": [],
                "governments": [],
            }
        )
        try:
            with pytest.raises(ValueError, match="1 government"):
                Simulator._load_world(db_path)
        finally:
            os.unlink(db_path)

    def test_rejects_multiple_governments(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [],
                "households": [],
                "governments": [
                    (1, 1000.0, 0.1, 0.0, 5.0),
                    (2, 2000.0, 0.05, 0.0, 3.0),
                ],
            }
        )
        try:
            with pytest.raises(ValueError, match="1 government"):
                Simulator._load_world(db_path)
        finally:
            os.unlink(db_path)

    def test_exactly_one_government_loads(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [],
                "households": [],
                "governments": [
                    (1, 1000.0, 0.1, 0.0, 5.0),
                ],
            }
        )
        try:
            ws = Simulator._load_world(db_path)
            assert len(ws.governments) == 1
            assert ws.governments[1].cash == 1000.0
        finally:
            os.unlink(db_path)


class TestPayWages:
    def test_pay_wages_correct_cash_movement(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [
                    (1, 100.0, 10.0, 0.0, 1),
                ],
                "firm_inventory": [],
                "firm_employees": [
                    (1, 101),
                    (1, 102),
                ],
                "households": [
                    (101, 50.0, 10.0, 1, 1, 0),
                    (102, 50.0, 15.0, 1, 1, 0),
                ],
                "household_inventory": [],
                "governments": [
                    (1, 1000.0, 0.0, 0.0, 0.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            assert state.firms[1].cash == 100.0
            assert state.households[101].cash == 50.0
            assert state.households[102].cash == 50.0

            sim._pay_wages(state)

            assert state.firms[1].cash == 100.0 - 10.0 - 15.0  # 75.0
            assert state.households[101].cash == 50.0 + 10.0  # 60.0
            assert state.households[102].cash == 50.0 + 15.0  # 65.0
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_insufficient_cash_skips_payment(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [
                    (1, 5.0, 10.0, 0.0, 1),
                ],
                "firm_inventory": [],
                "firm_employees": [
                    (1, 101),
                ],
                "households": [
                    (101, 50.0, 10.0, 1, 1, 0),
                ],
                "household_inventory": [],
                "governments": [
                    (1, 1000.0, 0.0, 0.0, 0.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            sim._pay_wages(state)

            assert state.households[101].cash == 50.0

            log = state.firms[1]._fulfillment_log
            assert len(log) == 1
            assert log[0][0] == 0
            assert log[0][1] == 1
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_pay_wages_skips_inactive_firm(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [
                    (1, 100.0, 10.0, 0.0, 0),
                ],
                "firm_inventory": [],
                "firm_employees": [
                    (1, 101),
                ],
                "households": [
                    (101, 50.0, 10.0, 1, 1, 0),
                ],
                "household_inventory": [],
                "governments": [
                    (1, 1000.0, 0.0, 0.0, 0.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            sim._pay_wages(state)

            assert state.firms[1].cash == 100.0
            assert state.households[101].cash == 50.0
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestCollectTaxes:
    def test_taxes_increase_government_cash(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [
                    (1, 1000.0, 10.0, 0.0, 1),
                    (2, 2000.0, 20.0, 0.0, 1),
                ],
                "firm_inventory": [],
                "firm_employees": [],
                "households": [],
                "household_inventory": [],
                "governments": [
                    (1, 10000.0, 0.2, 0.0, 0.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state

            initial_gov_cash = state.governments[1].cash
            sim._collect_taxes(state)

            tax_1 = 1000.0 * 0.2
            tax_2 = 2000.0 * 0.2
            assert state.firms[1].cash == 1000.0 - tax_1
            assert state.firms[2].cash == 2000.0 - tax_2
            assert state.governments[1].cash == initial_gov_cash + tax_1 + tax_2
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_zero_tax_rate_no_change(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [
                    (1, 1000.0, 10.0, 0.0, 1),
                ],
                "firm_inventory": [],
                "firm_employees": [],
                "households": [],
                "household_inventory": [],
                "governments": [
                    (1, 10000.0, 0.0, 0.0, 0.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            initial_firm_cash = state.firms[1].cash
            initial_gov_cash = state.governments[1].cash
            sim._collect_taxes(state)

            assert state.firms[1].cash == initial_firm_cash
            assert state.governments[1].cash == initial_gov_cash
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_inactive_firm_not_taxed(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [
                    (1, 1000.0, 10.0, 0.0, 0),
                    (2, 2000.0, 20.0, 0.0, 1),
                ],
                "firm_inventory": [],
                "firm_employees": [],
                "households": [],
                "household_inventory": [],
                "governments": [
                    (1, 10000.0, 0.1, 0.0, 0.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            sim._collect_taxes(state)

            assert state.firms[1].cash == 1000.0
            assert state.firms[2].cash == 2000.0 * 0.9
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestDisburseUnemployment:
    def test_unemployment_benefit_paid(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [],
                "firm_inventory": [],
                "firm_employees": [],
                "households": [
                    (1, 100.0, 10.0, 1, 1, 0),
                    (2, 50.0, 10.0, 0, None, 3),
                ],
                "household_inventory": [],
                "governments": [
                    (1, 1000.0, 0.0, 0.0, 10.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            sim._disburse_unemployment(state)

            assert state.households[1].cash == 100.0
            assert state.households[2].cash == 50.0 + 10.0
            assert state.governments[1].cash == 1000.0 - 10.0
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_no_unemployment_ticks_no_benefit(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [],
                "firm_inventory": [],
                "firm_employees": [],
                "households": [
                    (1, 50.0, 10.0, 0, None, 0),
                ],
                "household_inventory": [],
                "governments": [
                    (1, 1000.0, 0.0, 0.0, 10.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            sim._disburse_unemployment(state)

            assert state.households[1].cash == 50.0
            assert state.governments[1].cash == 1000.0
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_insufficient_government_cash_proportional(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [],
                "firm_inventory": [],
                "firm_employees": [],
                "households": [
                    (1, 50.0, 10.0, 0, None, 1),
                    (2, 50.0, 10.0, 0, None, 1),
                ],
                "household_inventory": [],
                "governments": [
                    (1, 10.0, 0.0, 0.0, 10.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            sim._disburse_unemployment(state)

            assert state.governments[1].cash < 0.01
            assert state.households[1].cash == 50.0 + 5.0
            assert state.households[2].cash == 50.0 + 5.0
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestEndTick:
    def test_unemployment_ticks_incremented(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [],
                "firm_inventory": [],
                "firm_employees": [],
                "households": [
                    (1, 100.0, 10.0, 1, 1, 0),
                    (2, 50.0, 10.0, 0, None, 5),
                ],
                "household_inventory": [],
                "governments": [
                    (1, 1000.0, 0.0, 0.0, 0.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            state = sim.state
            sim._end_tick_for_all(state)

            assert state.households[1].unemployment_ticks == 0
            assert state.households[2].unemployment_ticks == 6
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_tick_incremented(self):
        db_path = _make_mini_world_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            assert sim.state.tick == 0
            sim.tick()
            assert sim.state.tick == 1
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestInit:
    def test_init_creates_all_components(self):
        db_path = _make_mini_world_db()
        config_path = _make_temp_config({"noise_type": "gaussian"})
        try:
            sim = Simulator(config_path, db_path)

            assert isinstance(sim.ledger, Ledger)
            assert isinstance(sim.noise, InformationFriction)
            assert sim.state.tick == 0
            assert sim.last_obs is not None
            assert sim.last_obs["tick"] == 0
            assert "all_firms" in sim.last_obs
            assert "all_households" in sim.last_obs
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_load_config_defaults(self):
        db_path = _make_mini_world_db()
        config_path = _make_temp_config({})
        try:
            sim = Simulator(config_path, db_path)
            assert sim.order_expire_ticks == 30
            assert sim.clearing.base_collateral_ratio == 0.1
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestTickAndRun:
    def test_five_ticks_no_crash(self):
        db_path = _make_mini_world_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            for i in range(5):
                sim.tick()
                assert sim.state.tick == i + 1
            assert sim.state.tick == 5
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_run_returns_snapshots(self):
        db_path = _make_mini_world_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            snapshots = sim.run(3)

            assert len(snapshots) == 3
            for snap in snapshots:
                assert "tick" in snap
                assert "gini" in snap
                assert "unemployment" in snap
                assert "engel" in snap
            assert snapshots[0]["tick"] == 1
            assert snapshots[1]["tick"] == 2
            assert snapshots[2]["tick"] == 3
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_wages_and_taxes_integrated(self):
        db_path = _make_temp_db(
            {
                "goods": [],
                "firms": [
                    (1, 100.0, 10.0, 0.0, 1),
                ],
                "firm_inventory": [],
                "firm_employees": [
                    (1, 101),
                ],
                "households": [
                    (101, 50.0, 10.0, 1, 1, 0),
                ],
                "household_inventory": [],
                "governments": [
                    (1, 1000.0, 0.2, 0.0, 5.0),
                ],
            }
        )
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            sim.tick()

            state = sim.state
            assert state.tick == 1
            assert state.firms[1].cash == (100.0 - 10.0) * 0.8  # 72.0
            assert state.households[101].cash == 50.0 + 10.0  # 60.0
            assert state.governments[1].cash == 1000.0 + 90.0 * 0.2  # 1018.0
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestBuildObservations:
    def test_obs_structure_without_strategies(self):
        db_path = _make_mini_world_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            obs = sim._build_observations(sim.state)

            assert "all_firms" in obs
            assert "all_households" in obs
            assert "governments" in obs
            assert "tick" in obs
            assert obs["tick"] == 0
            assert len(obs["all_firms"]) == 2
            assert len(obs["all_households"]) == 5
            assert len(obs["governments"]) == 1
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_obs_deepcopy_no_mutation(self):
        db_path = _make_mini_world_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            obs = sim._build_observations(sim.state)

            obs["all_firms"][0].cash = 999.0
            assert sim.state.firms[1].cash == 5000.0
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


def _make_one_firm_one_hh_db() -> str:
    return _make_temp_db(
        {
            "goods": [
                (1, "bread", "food", 1),
                (3, "iron", "raw_material", 2),
            ],
            "firms": [
                (1, 5000.0, 100.0, 0.0, 1),
            ],
            "firm_inventory": [
                (1, 1, 50.0),
                (1, 3, 20.0),
            ],
            "firm_employees": [],
            "households": [
                (101, 200.0, 10.0, 0, None, 0),
            ],
            "household_inventory": [
                (101, 1, 5.0),
            ],
            "governments": [
                (1, 50000.0, 0.0, 0.0, 0.0),
            ],
        }
    )


class TestStrategyRegistry:
    def test_register_and_get(self):
        from policies.registry import Registry

        r = Registry()

        def dummy_firm(obs, firm, goods):
            return {"new": [], "cancel": [], "update": []}

        r.register("firm", dummy_firm)
        assert r.get("firm") is dummy_firm
        assert r.get("household") is None

    def test_register_invalid_slot_raises(self):
        from policies.registry import Registry

        r = Registry()
        with pytest.raises(ValueError, match="Unknown slot"):
            r.register("invalid", lambda x: x)

    def test_get_invalid_slot_raises(self):
        from policies.registry import Registry

        r = Registry()
        with pytest.raises(ValueError, match="Unknown slot"):
            r.get("invalid")


class TestFirmDemoStrategy:
    def test_firm_demo_grows_supply_pool(self):
        from policies.demo_strategies import firm_strategy
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("firm", firm_strategy)
            sim.set_registry(reg)

            assert len(sim.state.supply_pool) == 0

            sim.tick()

            supply_order_ids = {o.order_id for o in sim.state.supply_pool}
            assert len(supply_order_ids) > 0
            for o in sim.state.supply_pool:
                assert o.seller_id == 1
                assert o.good_id == 1
                assert o.status == "OPEN"
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_firm_demo_buy_raw_material_grows_demand_pool(self):
        from policies.demo_strategies import firm_strategy
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("firm", firm_strategy)
            sim.set_registry(reg)

            assert len(sim.state.demand_pool) == 0

            sim.tick()

            demand_iron = [o for o in sim.state.demand_pool if o.good_id == 3]
            assert len(demand_iron) > 0
            for o in demand_iron:
                assert o.buyer_id == 1
                assert o.status == "OPEN"
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestHouseholdDemoStrategy:
    def test_household_demo_grows_demand_pool(self):
        from policies.demo_strategies import household_strategy
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("household", household_strategy)
            sim.set_registry(reg)

            assert len(sim.state.demand_pool) == 0

            sim.tick()

            hh_orders = [o for o in sim.state.demand_pool if o.buyer_id == 101]
            assert len(hh_orders) > 0
            for o in hh_orders:
                assert o.good_id == 1
                assert o.order_type == "B2C"
                assert o.status == "OPEN"
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestAllocationPolicy:
    def test_allocation_creates_matched_orders(self):
        from policies.demo_strategies import (
            firm_strategy,
            household_strategy,
            demo_allocation,
        )
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("firm", firm_strategy)
            reg.register("household", household_strategy)
            reg.register("allocation", demo_allocation)
            sim.set_registry(reg)

            assert len(sim.state.pending_orders) == 0

            sim.tick()

            allocated = [o for o in sim.state.pending_orders if o.status == "ALLOCATED"]
            assert len(allocated) > 0
            for o in allocated:
                assert o.seller_id != 0
                assert o.buyer_id != 0
                assert o.settlement_tick == 1  # tick(0) + delivery_lag(1)
                assert o.order_id in sim.state.all_orders
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_allocation_price_lowest_supply_first(self):
        from policies.demo_strategies import demo_allocation

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)

            tick = sim.state.tick
            supply_cheap = Order(
                order_id="s_cheap",
                seller_id=1,
                buyer_id=0,
                good_id=1,
                quantity=3.0,
                price=1.0,
                order_type="B2C",
                creation_tick=tick,
            )
            supply_expensive = Order(
                order_id="s_exp",
                seller_id=1,
                buyer_id=0,
                good_id=1,
                quantity=3.0,
                price=5.0,
                order_type="B2C",
                creation_tick=tick,
            )
            demand = Order(
                order_id="d1",
                seller_id=0,
                buyer_id=1,
                good_id=1,
                quantity=3.0,
                price=3.0,
                order_type="B2C",
                creation_tick=tick,
            )

            sim.state.all_orders["s_cheap"] = supply_cheap
            sim.state.all_orders["s_exp"] = supply_expensive
            sim.state.all_orders["d1"] = demand
            sim.state.supply_pool = [supply_cheap, supply_expensive]
            sim.state.demand_pool = [demand]
            sim.clearing.freeze_collateral(sim.state, supply_cheap)
            sim.clearing.freeze_collateral(sim.state, supply_expensive)
            sim.clearing.freeze_collateral(sim.state, demand)

            matched, _, _ = demo_allocation(
                sim.last_obs,
                list(sim.state.supply_pool),
                list(sim.state.demand_pool),
                sim.state.goods,
            )

            assert len(matched) == 1
            assert matched[0].price == 1.0
            assert matched[0].seller_id == 1
            assert matched[0].buyer_id == 1
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestFullTickPipeline:
    def test_full_tick_inventory_transfer(self):
        from policies.demo_strategies import (
            firm_strategy,
            household_strategy,
            demo_allocation,
        )
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("firm", firm_strategy)
            reg.register("household", household_strategy)
            reg.register("allocation", demo_allocation)
            sim.set_registry(reg)

            firm = sim.state.firms[1]
            hh = sim.state.households[101]

            firm_bread_before = firm.inventory.get(1, 0.0)
            hh_bread_before = hh.inventory.get(1, 0.0)
            firm_cash_before = firm.cash
            hh_cash_before = hh.cash

            sim.tick()

            pending = [o for o in sim.state.pending_orders if o.status == "ALLOCATED"]
            assert len(pending) > 0, "Should have allocated orders after tick 0"

            sim.tick()

            assert hh.inventory.get(1, 0.0) > hh_bread_before, (
                "Household bread should increase after settlement"
            )
            assert firm.inventory.get(1, 0.0) < firm_bread_before, (
                "Firm bread should decrease after settlement"
            )
            assert hh.cash < hh_cash_before, (
                "Household cash should decrease after paying for bread"
            )
            assert firm.cash > firm_cash_before, (
                "Firm cash should increase after selling bread"
            )
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_government_strategy_does_nothing(self):
        from policies.demo_strategies import government_strategy
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("government", government_strategy)
            sim.set_registry(reg)

            pools_before = len(sim.state.supply_pool) + len(sim.state.demand_pool)

            sim.tick()

            pools_after = len(sim.state.supply_pool) + len(sim.state.demand_pool)
            assert pools_after == pools_before
        finally:
            os.unlink(db_path)
            os.unlink(config_path)


class TestObsNoise:
    def test_agent_obs_my_state_noiseless(self):
        from policies.demo_strategies import firm_strategy
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config(
            {
                "noise_type": "gaussian",
                "noise_params": {"sigma": 0.1},
            }
        )
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("firm", firm_strategy)
            sim.set_registry(reg)

            shared = sim._build_observations(sim.state)
            agent_obs = sim._agent_obs(shared, sim.state, 1, "firm")

            assert agent_obs["my_id"] == 1
            assert agent_obs["my_state"] is not None
            assert agent_obs["my_state"].cash == sim.state.firms[1].cash

            noisy_cash = agent_obs["all_firms"][0].cash
            assert noisy_cash != pytest.approx(agent_obs["my_state"].cash, abs=0.001), (
                "all_firms should have noisy cash while my_state has original"
            )
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_agent_obs_none_noise_identical(self):
        from policies.demo_strategies import firm_strategy
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("firm", firm_strategy)
            sim.set_registry(reg)

            shared = sim._build_observations(sim.state)
            agent_obs = sim._agent_obs(shared, sim.state, 1, "firm")

            assert agent_obs["my_state"].cash == agent_obs["all_firms"][0].cash
        finally:
            os.unlink(db_path)
            os.unlink(config_path)

    def test_agent_obs_includes_pool_orders(self):
        from policies.demo_strategies import firm_strategy
        from policies.registry import Registry

        db_path = _make_one_firm_one_hh_db()
        config_path = _make_temp_config({"noise_type": "none"})
        try:
            sim = Simulator(config_path, db_path)
            reg = Registry()
            reg.register("firm", firm_strategy)
            sim.set_registry(reg)

            sim.tick()

            shared = sim._build_observations(sim.state)
            agent_obs = sim._agent_obs(shared, sim.state, 1, "firm")

            assert len(agent_obs["my_supply_orders"]) > 0
            assert "my_demand_orders" in agent_obs
        finally:
            os.unlink(db_path)
            os.unlink(config_path)
