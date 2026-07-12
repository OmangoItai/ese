import pytest
from core.reporter import Reporter
from core.entities import Household, Good, Firm, Government, WorldState, Order
from core.ledger import Ledger


class TestCalcGini:
    def test_ten_extreme_inequality_gini_above_05(self):
        hhs = {}
        hhs[0] = Household(id=0, cash=1000.0)
        for i in range(1, 10):
            hhs[i] = Household(id=i, cash=0.0)
        gini = Reporter.calc_gini(hhs)
        assert gini > 0.5

    def test_all_equal_gini_near_zero(self):
        hhs = {}
        for i in range(10):
            hhs[i] = Household(id=i, cash=100.0)
        gini = Reporter.calc_gini(hhs)
        assert abs(gini) < 0.01

    def test_empty_returns_zero(self):
        gini = Reporter.calc_gini({})
        assert gini == 0.0

    def test_zero_wealth_returns_zero(self):
        hhs = {}
        for i in range(5):
            hhs[i] = Household(id=i, cash=0.0)
        gini = Reporter.calc_gini(hhs)
        assert gini == 0.0

    def test_single_household_returns_zero(self):
        hhs = {0: Household(id=0, cash=500.0)}
        gini = Reporter.calc_gini(hhs)
        assert gini == 0.0

    def test_with_goods_inventory_estimate(self):
        goods = {
            1: Good(good_id=1, name="bread", good_type="food", delivery_lag=1),
            2: Good(good_id=2, name="iron", good_type="raw_material", delivery_lag=4),
        }
        hhs = {
            0: Household(id=0, cash=100.0, inventory={1: 10.0, 2: 5.0}),
            1: Household(id=1, cash=200.0, inventory={1: 0.0, 2: 0.0}),
        }
        gini = Reporter.calc_gini(hhs, goods)
        wealth_0 = 100.0 + 10.0 * 1 + 5.0 * 4  # = 130.0
        wealth_1 = 200.0
        assert wealth_0 != wealth_1
        assert 0 < gini < 1

    def test_without_goods_no_inventory_weight(self):
        goods = None
        hhs = {
            0: Household(id=0, cash=100.0, inventory={1: 100.0}),
            1: Household(id=1, cash=100.0, inventory={1: 0.0}),
        }
        gini = Reporter.calc_gini(hhs, goods)
        assert gini == 0.0


class TestCalcEngel:
    def test_engel_in_zero_one_range(self):
        goods = {
            1: Good(good_id=1, name="bread", good_type="food"),
            2: Good(good_id=2, name="iron", good_type="raw_material"),
        }
        households = {1: Household(id=1, cash=1000.0)}

        ledger = Ledger()
        for i in range(5):
            o = Order(
                order_id=f"food_{i}",
                seller_id=1,
                buyer_id=1,
                good_id=1,
                quantity=2.0,
                price=5.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)
        for i in range(5):
            o = Order(
                order_id=f"iron_{i}",
                seller_id=2,
                buyer_id=1,
                good_id=2,
                quantity=1.0,
                price=10.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)

        engel = Reporter.calc_engel(households, goods, ledger)
        assert 0.0 <= engel <= 1.0
        assert engel == pytest.approx(0.5)

    def test_all_food_engel_is_one(self):
        goods = {1: Good(good_id=1, name="bread", good_type="food")}
        households = {1: Household(id=1, cash=1000.0)}

        ledger = Ledger()
        for i in range(3):
            o = Order(
                order_id=f"f{i}",
                seller_id=1,
                buyer_id=1,
                good_id=1,
                quantity=1.0,
                price=1.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)

        engel = Reporter.calc_engel(households, goods, ledger)
        assert engel == 1.0

    def test_no_food_engel_is_zero(self):
        goods = {
            1: Good(good_id=1, name="bread", good_type="food"),
            2: Good(good_id=2, name="iron", good_type="raw_material"),
        }
        households = {1: Household(id=1, cash=1000.0)}

        ledger = Ledger()
        for i in range(3):
            o = Order(
                order_id=f"n{i}",
                seller_id=1,
                buyer_id=1,
                good_id=2,
                quantity=1.0,
                price=1.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)

        engel = Reporter.calc_engel(households, goods, ledger)
        assert engel == 0.0

    def test_empty_ledger_returns_zero(self):
        goods = {1: Good(good_id=1, name="bread", good_type="food")}
        households = {1: Household(id=1, cash=1000.0)}
        ledger = Ledger()
        engel = Reporter.calc_engel(households, goods, ledger)
        assert engel == 0.0

    def test_non_household_buyer_excluded(self):
        goods = {
            1: Good(good_id=1, name="bread", good_type="food"),
            2: Good(good_id=2, name="iron", good_type="raw_material"),
        }
        households = {1: Household(id=1, cash=1000.0)}

        ledger = Ledger()
        o_food = Order(
            order_id="ff",
            seller_id=2,
            buyer_id=99,
            good_id=1,
            quantity=100.0,
            price=100.0,
            status="FULFILLED",
        )
        ledger.record_trade(o_food)
        o_hh = Order(
            order_id="hh",
            seller_id=2,
            buyer_id=1,
            good_id=2,
            quantity=1.0,
            price=1.0,
            status="FULFILLED",
        )
        ledger.record_trade(o_hh)

        engel = Reporter.calc_engel(households, goods, ledger)
        assert engel == 0.0

    def test_n_ticks_window_filters_old(self):
        goods = {
            1: Good(good_id=1, name="bread", good_type="food"),
            2: Good(good_id=2, name="iron", good_type="raw_material"),
        }
        households = {1: Household(id=1, cash=1000.0)}

        ledger = Ledger()
        o_old_food = Order(
            order_id="old_f",
            seller_id=1,
            buyer_id=1,
            good_id=1,
            quantity=100.0,
            price=1.0,
            status="FULFILLED",
        )
        ledger.record_trade(o_old_food)
        o_new_iron = Order(
            order_id="new_i",
            seller_id=1,
            buyer_id=1,
            good_id=2,
            quantity=1.0,
            price=1.0,
            status="FULFILLED",
        )
        o_new_iron.creation_tick = 10
        ledger.record_trade(o_new_iron)

        engel = Reporter.calc_engel(households, goods, ledger, n_ticks=5)
        assert engel == 0.0

    def test_zero_total_expenditure_returns_zero(self):
        goods = {1: Good(good_id=1, name="bread", good_type="food")}
        households = {1: Household(id=1, cash=1000.0)}
        ledger = Ledger()
        o = Order(
            order_id="z",
            seller_id=1,
            buyer_id=1,
            good_id=1,
            quantity=0.0,
            price=1.0,
            status="FULFILLED",
        )
        ledger.record_trade(o)
        engel = Reporter.calc_engel(households, goods, ledger)
        assert engel == 0.0


class TestCalcUnemployment:
    def test_two_of_five_unemployed(self):
        hhs = {}
        hhs[0] = Household(id=0, cash=100.0, is_employed=True)
        hhs[1] = Household(id=1, cash=100.0, is_employed=True)
        hhs[2] = Household(id=2, cash=100.0, is_employed=True)
        hhs[3] = Household(id=3, cash=100.0, is_employed=False)
        hhs[4] = Household(id=4, cash=100.0, is_employed=False)
        rate = Reporter.calc_unemployment(hhs)
        assert rate == 0.4

    def test_all_employed(self):
        hhs = {}
        for i in range(10):
            hhs[i] = Household(id=i, cash=100.0, is_employed=True)
        rate = Reporter.calc_unemployment(hhs)
        assert rate == 0.0

    def test_all_unemployed(self):
        hhs = {}
        for i in range(5):
            hhs[i] = Household(id=i, cash=100.0, is_employed=False)
        rate = Reporter.calc_unemployment(hhs)
        assert rate == 1.0

    def test_empty_returns_zero(self):
        rate = Reporter.calc_unemployment({})
        assert rate == 0.0


class TestSnapshot:
    def test_snapshot_contains_all_keys(self):
        goods = {1: Good(good_id=1, name="bread", good_type="food")}
        firms = {1: Firm(id=1, cash=1000.0, is_active=True)}
        households = {
            1: Household(id=1, cash=200.0, is_employed=True, inventory={1: 5.0})
        }
        governments = {1: Government(id=1, cash=10000.0)}
        state = WorldState(
            tick=5,
            firms=firms,
            households=households,
            governments=governments,
            goods=goods,
        )
        ledger = Ledger()

        snap = Reporter.snapshot(state, ledger)

        expected_keys = {
            "tick",
            "gini",
            "engel",
            "unemployment",
            "active_firms",
            "active_households",
            "total_firms",
            "total_households",
        }
        assert set(snap.keys()) == expected_keys
        assert snap["tick"] == 5
        assert snap["active_firms"] == 1
        assert snap["total_firms"] == 1
        assert snap["active_households"] == 1
        assert snap["total_households"] == 1

    def test_snapshot_inactive_firm_counted(self):
        goods = {}
        firms = {
            1: Firm(id=1, cash=1000.0, is_active=True),
            2: Firm(id=2, cash=500.0, is_active=False),
        }
        state = WorldState(tick=0, firms=firms, goods=goods)
        ledger = Ledger()
        snap = Reporter.snapshot(state, ledger)
        assert snap["active_firms"] == 1
        assert snap["total_firms"] == 2

    def test_snapshot_gini_and_unemployment_correct(self):
        goods = {}
        households = {
            0: Household(id=0, cash=100.0, is_employed=True),
            1: Household(id=1, cash=100.0, is_employed=True),
            2: Household(id=2, cash=100.0, is_employed=False),
            3: Household(id=3, cash=100.0, is_employed=False),
            4: Household(id=4, cash=100.0, is_employed=True),
        }
        state = WorldState(tick=0, households=households, goods=goods)
        ledger = Ledger()
        snap = Reporter.snapshot(state, ledger)
        assert snap["gini"] == pytest.approx(0.0, abs=0.01)
        assert snap["unemployment"] == 0.4
