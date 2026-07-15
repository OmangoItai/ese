from collections import deque
import pytest
from core.clearing_house import ClearingHouse
from core.entities import Firm, Household, Government, Good, Order, WorldState
from core.ledger import TradeHistory


def _make_firm(id_: int, cash: float, **kwargs) -> Firm:
    return Firm(id=id_, cash=cash, **kwargs)


def _make_household(id_: int, cash: float, **kwargs) -> Household:
    return Household(id=id_, cash=cash, **kwargs)


def _make_good(id_: int, name: str, **kwargs) -> Good:
    return Good(good_id=id_, name=name, **kwargs)


def _make_order(
    order_id: str,
    seller_id: int,
    buyer_id: int,
    good_id: int,
    quantity: float,
    price: float,
    **kwargs,
) -> Order:
    return Order(
        order_id=order_id,
        seller_id=seller_id,
        buyer_id=buyer_id,
        good_id=good_id,
        quantity=quantity,
        price=price,
        **kwargs,
    )


class TestFulfillmentRate:
    def test_all_fulfilled_returns_one(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque([(10, 0, 10)], maxlen=30)
        assert ch._fulfillment_rate(f) == 1.0

    def test_all_defaulted_returns_zero(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque([(0, 5, 10)], maxlen=30)
        assert ch._fulfillment_rate(f) == 0.0

    def test_empty_returns_one(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        assert ch._fulfillment_rate(f) == 1.0

    def test_all_zeros_returns_one(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque([(0, 0, 10)], maxlen=30)
        assert ch._fulfillment_rate(f) == 1.0

    def test_mixed_returns_ratio(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque(
            [
                (3, 1, 10),
                (2, 2, 9),
                (5, 0, 8),
            ],
            maxlen=30,
        )
        total_fulfilled = 3 + 2 + 5
        total_defaulted = 1 + 2 + 0
        expected = total_fulfilled / (total_fulfilled + total_defaulted)
        assert ch._fulfillment_rate(f) == expected

    def test_high_volume_in_single_tick(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque([(98, 2, 10)], maxlen=30)
        assert ch._fulfillment_rate(f) == 98.0 / 100.0

    def test_multiple_ticks_aggregate(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque(
            [
                (40, 10, 10),
                (30, 5, 9),
                (20, 0, 8),
            ],
            maxlen=30,
        )
        total_fulfilled = 40 + 30 + 20
        total_defaulted = 10 + 5 + 0
        expected = total_fulfilled / (total_fulfilled + total_defaulted)
        assert ch._fulfillment_rate(f) == expected


class TestDynamicCollateralRatio:
    def test_full_fulfillment_returns_base(self):
        ch = ClearingHouse(TradeHistory(), base_collateral_ratio=0.1)
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque([(10, 0, 10)], maxlen=30)
        assert ch.calc_dynamic_collateral_ratio(f) == 0.1

    def test_zero_fulfillment_returns_max(self):
        ch = ClearingHouse(TradeHistory(), base_collateral_ratio=0.1)
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque([(0, 5, 10)], maxlen=30)
        assert ch.calc_dynamic_collateral_ratio(f) == pytest.approx(0.5)

    def test_50pct_fulfillment(self):
        ch = ClearingHouse(TradeHistory(), base_collateral_ratio=0.1)
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque([(5, 5, 10)], maxlen=30)
        expected = 0.1 + (1.0 - 0.5) * 0.4
        assert ch.calc_dynamic_collateral_ratio(f) == expected

    def test_different_base_ratio(self):
        ch = ClearingHouse(TradeHistory(), base_collateral_ratio=0.2)
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque([(3, 0, 10)], maxlen=30)
        assert ch.calc_dynamic_collateral_ratio(f) == 0.2

    def test_empty_log_returns_base(self):
        ch = ClearingHouse(TradeHistory(), base_collateral_ratio=0.1)
        f = _make_firm(1, 1000.0)
        assert ch.calc_dynamic_collateral_ratio(f) == 0.1


class TestValidateOrder:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def _make_ws(self, firm=None, household=None, goods=None):
        return WorldState(
            tick=0,
            firms={firm.id: firm} if firm else {},
            households={household.id: household} if household else {},
            goods=goods or {},
        )

    def test_validate_success(self):
        seller = _make_firm(1, 5000.0)
        buyer = _make_firm(2, 5000.0)
        ws = self._make_ws(firm=seller)
        ws.firms[2] = buyer
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)

        ok, msg = self.ch.validate_order(ws, order)
        assert ok is True
        assert msg == "OK"

    def test_seller_not_found(self):
        buyer = _make_firm(2, 5000.0)
        ws = self._make_ws()
        ws.firms[2] = buyer
        order = _make_order("o1", 999, 2, 3, quantity=10.0, price=5.0)

        ok, msg = self.ch.validate_order(ws, order)
        assert ok is False
        assert "Seller 999 not found" in msg

    def test_buyer_not_found(self):
        seller = _make_firm(1, 5000.0)
        ws = self._make_ws(firm=seller)
        order = _make_order("o1", 1, 999, 3, quantity=10.0, price=5.0)

        ok, msg = self.ch.validate_order(ws, order)
        assert ok is False
        assert "Buyer 999 not found" in msg

    def test_seller_insufficient_cash(self):
        seller = _make_firm(1, 1.0)
        buyer = _make_firm(2, 5000.0)
        ws = self._make_ws(firm=seller)
        ws.firms[2] = buyer
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)
        ok, msg = self.ch.validate_order(ws, order)
        assert ok is False
        assert "Seller 1 insufficient cash" in msg

    def test_buyer_insufficient_cash(self):
        seller = _make_firm(1, 5000.0)
        buyer = _make_firm(2, 1.0)
        ws = self._make_ws(firm=seller)
        ws.firms[2] = buyer
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)
        ok, msg = self.ch.validate_order(ws, order)
        assert ok is False
        assert "Buyer 2 insufficient cash" in msg

    def test_labor_seller_must_be_household(self):
        hh = _make_household(1, 5000.0)
        firm = _make_firm(2, 5000.0)
        labor_good = _make_good(10, "labor", good_type="labor")
        ws = self._make_ws(firm=firm, household=hh, goods={10: labor_good})
        firm_as_seller = _make_order("o1", 2, 2, 10, quantity=1.0, price=10.0)
        ok, msg = self.ch.validate_order(ws, firm_as_seller)
        assert ok is False
        assert "must be a Household" in msg

    def test_labor_buyer_must_be_firm(self):
        hh1 = _make_household(1, 5000.0)
        hh2 = _make_household(2, 5000.0)
        labor_good = _make_good(10, "labor", good_type="labor")
        ws = self._make_ws(household=hh1, goods={10: labor_good})
        ws.households[2] = hh2
        order = _make_order("o1", 1, 2, 10, quantity=1.0, price=10.0)
        ok, msg = self.ch.validate_order(ws, order)
        assert ok is False
        assert "must be a Firm" in msg

    def test_labor_valid_success(self):
        hh = _make_household(1, 5000.0)
        firm = _make_firm(2, 5000.0)
        labor_good = _make_good(10, "labor", good_type="labor")
        ws = self._make_ws(firm=firm, household=hh, goods={10: labor_good})
        order = _make_order("o1", 1, 2, 10, quantity=1.0, price=10.0)
        ok, msg = self.ch.validate_order(ws, order)
        assert ok is True


class TestFreezeRelease:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def _make_ws_with_two_firms(self, cash1=5000.0, cash2=5000.0):
        f1 = _make_firm(1, cash1)
        f2 = _make_firm(2, cash2)
        ws = WorldState(tick=0, firms={1: f1, 2: f2})
        return ws, f1, f2

    def test_freeze_deducts_cash_and_adds_to_pool(self):
        ws, f1, f2 = self._make_ws_with_two_firms()
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)
        order_value = 10.0 * 5.0

        self.ch.freeze_collateral(ws, order)

        assert len(ws.collateral_pool) == 2
        assert "o1_seller" in ws.collateral_pool
        assert "o1_buyer" in ws.collateral_pool
        assert ws.collateral_pool["o1_seller"] == order_value * 0.1
        assert ws.collateral_pool["o1_buyer"] == order_value * 0.1
        assert f1.cash == 5000.0 - ws.collateral_pool["o1_seller"]
        assert f2.cash == 5000.0 - ws.collateral_pool["o1_buyer"]

    def test_freeze_adds_outstanding_order_ids(self):
        ws, f1, f2 = self._make_ws_with_two_firms()
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)
        self.ch.freeze_collateral(ws, order)
        assert "o1" in f1.outstanding_order_ids
        assert "o1" in f2.outstanding_order_ids

    def test_release_restores_cash_and_removes_from_pool(self):
        ws, f1, f2 = self._make_ws_with_two_firms()
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)
        self.ch.freeze_collateral(ws, order)

        self.ch.release_collateral(ws, order)

        assert len(ws.collateral_pool) == 0
        assert f1.cash == 5000.0
        assert f2.cash == 5000.0

    def test_release_removes_outstanding_order_ids(self):
        ws, f1, f2 = self._make_ws_with_two_firms()
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)
        self.ch.freeze_collateral(ws, order)
        self.ch.release_collateral(ws, order)
        assert "o1" not in f1.outstanding_order_ids
        assert "o1" not in f2.outstanding_order_ids

    def test_freeze_with_dynamic_ratio(self):
        ws, f1, f2 = self._make_ws_with_two_firms()
        f1._fulfillment_log = deque([(0, 5, 0)], maxlen=30)
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)

        self.ch.freeze_collateral(ws, order)

        expected_seller_ratio = 0.5
        expected_buyer_ratio = 0.1
        order_value = 50.0
        assert ws.collateral_pool["o1_seller"] == order_value * expected_seller_ratio
        assert ws.collateral_pool["o1_buyer"] == order_value * expected_buyer_ratio


class TestForfeitCollateral:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def _make_ws(self):
        f1 = _make_firm(1, 5000.0)
        f2 = _make_firm(2, 5000.0)
        ws = WorldState(tick=0, firms={1: f1, 2: f2})
        return ws, f1, f2

    def test_forfeit_seller_side(self):
        ws, f1, f2 = self._make_ws()
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)
        self.ch.freeze_collateral(ws, order)

        seller_frozen = ws.collateral_pool["o1_seller"]
        buyer_frozen = ws.collateral_pool["o1_buyer"]

        cash1_after_freeze = f1.cash
        cash2_after_freeze = f2.cash

        self.ch.forfeit_collateral(ws, order, "seller")

        assert len(ws.collateral_pool) == 0
        assert f1.cash == cash1_after_freeze
        assert f2.cash == cash2_after_freeze + buyer_frozen + seller_frozen
        assert "o1" not in f1.outstanding_order_ids
        assert "o1" not in f2.outstanding_order_ids

    def test_forfeit_buyer_side(self):
        ws, f1, f2 = self._make_ws()
        order = _make_order("o1", 1, 2, 3, quantity=10.0, price=5.0)
        self.ch.freeze_collateral(ws, order)

        seller_frozen = ws.collateral_pool["o1_seller"]
        buyer_frozen = ws.collateral_pool["o1_buyer"]

        cash1_after_freeze = f1.cash
        cash2_after_freeze = f2.cash

        self.ch.forfeit_collateral(ws, order, "buyer")

        assert len(ws.collateral_pool) == 0
        assert f2.cash == cash2_after_freeze
        assert f1.cash == cash1_after_freeze + seller_frozen + buyer_frozen
        assert "o1" not in f1.outstanding_order_ids
        assert "o1" not in f2.outstanding_order_ids


class TestPriceTracking:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def test_record_and_get_price_range(self):
        self.ch.record_settled_price(1, 1, 10.0)
        self.ch.record_settled_price(1, 2, 15.0)
        self.ch.record_settled_price(1, 3, 20.0)

        mn, mx, avg = self.ch.get_market_price_range(1)
        assert mn == 10.0
        assert mx == 20.0
        assert avg == 15.0

    def test_empty_price_history(self):
        mn, mx, avg = self.ch.get_market_price_range(99)
        assert mn == 0.0
        assert mx == 0.0
        assert avg == 0.0

    def test_deque_maxlen_enforced(self):
        self.ch.price_history[1] = deque(maxlen=2)
        self.ch.record_settled_price(1, 1, 10.0)
        self.ch.record_settled_price(1, 2, 20.0)
        self.ch.record_settled_price(1, 3, 30.0)

        mn, mx, avg = self.ch.get_market_price_range(1)
        assert mn == 20.0
        assert mx == 30.0
        assert avg == 25.0

    def test_multiple_goods_tracking(self):
        self.ch.record_settled_price(1, 1, 100.0)
        self.ch.record_settled_price(1, 2, 200.0)
        self.ch.record_settled_price(2, 1, 50.0)
        self.ch.record_settled_price(2, 2, 75.0)

        mn1, mx1, avg1 = self.ch.get_market_price_range(1)
        assert mn1 == 100.0
        assert mx1 == 200.0
        assert avg1 == 150.0

        mn2, mx2, avg2 = self.ch.get_market_price_range(2)
        assert mn2 == 50.0
        assert mx2 == 75.0
        assert avg2 == 62.5


class TestRecordSettlement:
    def test_record_same_tick_merges_into_one_entry(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        ch.record_settlement(f, True, tick=5)
        ch.record_settlement(f, True, tick=5)
        ch.record_settlement(f, False, tick=5)
        assert len(f._fulfillment_log) == 1
        assert f._fulfillment_log[0] == (2, 1, 5)

    def test_record_different_ticks_create_separate_entries(self):
        ch = ClearingHouse(TradeHistory())
        f = _make_firm(1, 1000.0)
        ch.record_settlement(f, True, tick=5)
        ch.record_settlement(f, False, tick=6)
        assert len(f._fulfillment_log) == 2
        assert f._fulfillment_log[0] == (1, 0, 5)
        assert f._fulfillment_log[1] == (0, 1, 6)

    def test_deque_maxlen_evicts_oldest(self):
        f = _make_firm(1, 1000.0)
        f._fulfillment_log = deque(maxlen=3)
        ch = ClearingHouse(TradeHistory())
        ch.record_settlement(f, True, tick=5)
        ch.record_settlement(f, True, tick=6)
        ch.record_settlement(f, True, tick=7)
        ch.record_settlement(f, False, tick=8)
        assert len(f._fulfillment_log) == 3
        assert f._fulfillment_log[0] == (1, 0, 6)
        assert f._fulfillment_log[-1] == (0, 1, 8)

    def test_deque_maxlen_default_thirty(self):
        f = _make_firm(1, 1000.0)
        assert f._fulfillment_log.maxlen == 30


class TestSettleOrderGoods:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def _make_ws(self, seller_cash=5000.0, buyer_cash=5000.0, goods=None):
        good = _make_good(1, "bread", good_type="consumer", delivery_lag=1)
        seller = _make_firm(1, seller_cash)
        seller.inventory = {1: 100.0}
        buyer = _make_firm(2, buyer_cash)
        buyer.inventory = {1: 0.0}
        all_goods = goods or {1: good}
        return WorldState(tick=5, firms={1: seller, 2: buyer}, goods=all_goods)

    def test_settle_success_transfers_goods_and_money(self):
        ws = self._make_ws()
        order = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=10.0,
            price=3.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)

        seller_cash_original = ws.firms[1].cash
        buyer_cash_original = ws.firms[2].cash

        self.ch.freeze_collateral(ws, order)
        ws.pending_orders.append(order)

        seller_inv_before = ws.firms[1].inventory[1]
        buyer_inv_before = ws.firms[2].inventory.get(1, 0.0)

        ok, msg, liquidated = self.ch.settle_order(ws, order)

        assert ok is True
        assert msg == "FULFILLED"
        assert liquidated is False
        assert order.status == "FULFILLED"
        assert ws.firms[1].inventory[1] == seller_inv_before - 10.0
        assert ws.firms[2].inventory.get(1, 0.0) == buyer_inv_before + 10.0
        assert ws.firms[1].cash == seller_cash_original + 30.0
        assert ws.firms[2].cash == buyer_cash_original - 30.0
        assert len(ws.collateral_pool) == 0

    def test_settle_seller_insufficient_inventory_defaults(self):
        ws = self._make_ws(seller_cash=5000.0, buyer_cash=5000.0)
        order = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=999.0,
            price=3.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)
        self.ch.freeze_collateral(ws, order)
        ws.pending_orders.append(order)

        seller_cash_after_freeze = ws.firms[1].cash
        buyer_cash_after_freeze = ws.firms[2].cash

        ok, msg, liquidated = self.ch.settle_order(ws, order)

        assert ok is False
        assert "DEFAULTED" in msg
        assert order.status == "DEFAULTED"
        assert len(ws.collateral_pool) == 0
        assert ws.firms[1].cash == seller_cash_after_freeze
        assert ws.firms[2].cash == buyer_cash_after_freeze + (999.0 * 3.0 * 0.1) * 2

    def test_settle_buyer_insufficient_cash_defaults(self):
        ws = self._make_ws(seller_cash=5000.0, buyer_cash=200.0)
        order = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=10.0,
            price=100.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)
        self.ch.freeze_collateral(ws, order)
        ws.pending_orders.append(order)

        seller_cash_after_freeze = ws.firms[1].cash
        buyer_cash_after_freeze = ws.firms[2].cash

        ok, msg, liquidated = self.ch.settle_order(ws, order)

        assert ok is False
        assert "DEFAULTED" in msg
        assert order.status == "DEFAULTED"
        assert len(ws.collateral_pool) == 0
        assert ws.firms[1].cash > seller_cash_after_freeze
        assert ws.firms[2].cash == buyer_cash_after_freeze

    def test_settle_not_allocated_returns_false(self):
        ws = self._make_ws()
        order = _make_order(
            "o1", 1, 2, 1, quantity=10.0, price=3.0, status="OPEN", settlement_tick=5
        )
        ok, msg, liquidated = self.ch.settle_order(ws, order)
        assert ok is False
        assert "not ALLOCATED" in msg

    def test_settle_wrong_tick_returns_false(self):
        ws = self._make_ws()
        order = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=10.0,
            price=3.0,
            status="ALLOCATED",
            settlement_tick=99,
        )
        ok, msg, liquidated = self.ch.settle_order(ws, order)
        assert ok is False
        assert "settlement_tick" in msg

    def test_settle_records_fulfillment_log(self):
        ws = self._make_ws()
        order = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=10.0,
            price=3.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)
        self.ch.freeze_collateral(ws, order)
        ws.pending_orders.append(order)

        self.ch.settle_order(ws, order)

        seller_log = ws.firms[1]._fulfillment_log
        buyer_log = ws.firms[2]._fulfillment_log
        assert len(seller_log) == 1
        assert len(buyer_log) == 1
        assert seller_log[0] == (1, 0, 5)
        assert buyer_log[0] == (1, 0, 5)

    def test_settle_records_default_fulfillment_log(self):
        ws = self._make_ws(seller_cash=5000.0, buyer_cash=5000.0)
        order = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=999.0,
            price=3.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)
        self.ch.freeze_collateral(ws, order)
        ws.pending_orders.append(order)

        self.ch.settle_order(ws, order)

        seller_log = ws.firms[1]._fulfillment_log
        buyer_log = ws.firms[2]._fulfillment_log
        assert seller_log[0] == (0, 1, 5)
        assert buyer_log[0] == (0, 1, 5)


class TestSettleOrderLabor:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def _make_ws(self):
        labor_good = _make_good(10, "labor", good_type="labor", delivery_lag=1)
        hh = _make_household(1, 1000.0, labor_ask_price=10.0)
        firm = _make_firm(2, 5000.0)
        return WorldState(
            tick=5,
            firms={2: firm},
            households={1: hh},
            goods={10: labor_good},
        )

    def test_labor_settle_creates_employment(self):
        ws = self._make_ws()
        order = _make_order(
            "o1",
            1,
            2,
            10,
            quantity=1.0,
            price=10.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)
        self.ch.freeze_collateral(ws, order)
        ws.pending_orders.append(order)

        hh_cash_before = ws.households[1].cash
        firm_cash_before = ws.firms[2].cash

        ok, msg, liquidated = self.ch.settle_order(ws, order)

        assert ok is True
        assert "FULFILLED" in msg
        assert liquidated is False
        assert order.status == "FULFILLED"
        assert ws.households[1].is_employed is True
        assert ws.households[1].employer_firm_id == 2
        assert 1 in ws.firms[2].employees
        assert len(ws.collateral_pool) == 0

    def test_labor_settle_switches_employer(self):
        ws = self._make_ws()
        old_firm = _make_firm(3, 5000.0)
        ws.firms[3] = old_firm
        ws.households[1].is_employed = True
        ws.households[1].employer_firm_id = 3
        ws.firms[3].employees.append(1)

        order = _make_order(
            "o1",
            1,
            2,
            10,
            quantity=1.0,
            price=12.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)
        self.ch.freeze_collateral(ws, order)
        ws.pending_orders.append(order)

        self.ch.settle_order(ws, order)

        assert ws.households[1].employer_firm_id == 2
        assert 1 not in ws.firms[3].employees
        assert 1 in ws.firms[2].employees

    def test_labor_seller_not_household_fails(self):
        ws = self._make_ws()
        labor_good = ws.goods[10]
        ws.firms[2] = _make_firm(2, 5000.0)
        ws.households = {}
        ws.firms[1] = _make_firm(1, 5000.0)
        order = _make_order(
            "o1",
            1,
            2,
            10,
            quantity=1.0,
            price=10.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        ok, msg, _ = self.ch.settle_order(ws, order)
        assert ok is False
        assert "must be Household" in msg


class TestLiquidateFirm:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def test_liquidate_firm_foreclosure_and_dismiss(self):
        good = _make_good(1, "iron", good_type="raw_material")
        self.ch.record_settled_price(1, 1, 10.0)
        self.ch.record_settled_price(1, 2, 20.0)
        self.ch.record_settled_price(1, 3, 30.0)

        firm = _make_firm(1, 100.0)
        firm.inventory = {1: 50.0}
        firm.employees = [2, 3]

        hh1 = _make_household(
            2, 200.0, labor_ask_price=5.0, is_employed=True, employer_firm_id=1
        )
        hh2 = _make_household(
            3, 200.0, labor_ask_price=8.0, is_employed=True, employer_firm_id=1
        )

        gov = Government(id=1, cash=10000.0)

        ws = WorldState(
            tick=10,
            firms={1: firm},
            households={2: hh1, 3: hh2},
            governments={1: gov},
            goods={1: good},
        )

        result = self.ch.liquidate_firm(ws, 1)

        assert result["success"] is True
        assert firm.is_active is False
        assert len(firm.inventory) == 0
        assert len(firm.employees) == 0
        assert hh1.is_employed is False
        assert hh1.employer_firm_id is None
        assert hh2.is_employed is False
        assert hh2.employer_firm_id is None

    def test_liquidate_firm_clears_open_orders(self):
        good = _make_good(1, "bread", good_type="consumer")
        self.ch.record_settled_price(1, 1, 5.0)

        firm = _make_firm(1, 1000.0)
        counterparty = _make_firm(2, 5000.0)

        gov = Government(id=1, cash=10000.0)

        ws = WorldState(
            tick=10,
            firms={1: firm, 2: counterparty},
            governments={1: gov},
            goods={1: good},
        )

        order = _make_order("o1", 1, 2, 1, quantity=10.0, price=5.0, status="OPEN")
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)
        self.ch.freeze_collateral(ws, order)

        cpty_cash_after_freeze = counterparty.cash

        self.ch.liquidate_firm(ws, 1)

        assert order.status == "CANCELLED"
        assert order not in ws.market.supply
        assert counterparty.cash > cpty_cash_after_freeze

    def test_liquidate_firm_clears_allocated_orders(self):
        good = _make_good(1, "bread", good_type="consumer")
        self.ch.record_settled_price(1, 1, 5.0)

        firm = _make_firm(1, 1000.0)
        counterparty = _make_firm(2, 5000.0)

        gov = Government(id=1, cash=10000.0)

        ws = WorldState(
            tick=10,
            firms={1: firm, 2: counterparty},
            governments={1: gov},
            goods={1: good},
        )

        order = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=10.0,
            price=5.0,
            status="ALLOCATED",
        )
        ws.all_orders["o1"] = order
        ws.pending_orders.append(order)
        self.ch.freeze_collateral(ws, order)

        cpty_cash_after_freeze = counterparty.cash

        self.ch.liquidate_firm(ws, 1)

        assert order.status == "DEFAULTED"
        assert order not in ws.pending_orders
        assert counterparty.cash > cpty_cash_after_freeze

    def test_liquidate_firm_pays_wages_from_foreclosure(self):
        good = _make_good(1, "iron", good_type="raw_material")
        self.ch.record_settled_price(1, 1, 10.0)

        firm = _make_firm(1, 10.0)
        firm.inventory = {1: 10.0}
        firm.employees = [2]

        hh = _make_household(
            2, 0.0, labor_ask_price=50.0, is_employed=True, employer_firm_id=1
        )

        gov = Government(id=1, cash=10000.0)

        ws = WorldState(
            tick=10,
            firms={1: firm},
            households={2: hh},
            governments={1: gov},
            goods={1: good},
        )

        self.ch.liquidate_firm(ws, 1)

        assert firm.is_active is False
        assert hh.cash > 0.0

    def test_liquidate_firm_inactive_firm_returns_false(self):
        ws = WorldState(tick=0)
        result = self.ch.liquidate_firm(ws, 99)
        assert result["success"] is False


class TestSettleAllExpired:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def test_settle_all_expired_processes_orders(self):
        good = _make_good(1, "bread", good_type="consumer", delivery_lag=1)
        seller = _make_firm(1, 5000.0)
        seller.inventory = {1: 100.0}
        buyer = _make_firm(2, 5000.0)
        buyer.inventory = {1: 0.0}

        ws = WorldState(
            tick=5,
            firms={1: seller, 2: buyer},
            goods={1: good},
        )

        order1 = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=10.0,
            price=5.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        order2 = _make_order(
            "o2",
            1,
            2,
            1,
            quantity=5.0,
            price=5.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        order_future = _make_order(
            "o3",
            1,
            2,
            1,
            quantity=3.0,
            price=5.0,
            status="ALLOCATED",
            settlement_tick=99,
        )

        for o in [order1, order2, order_future]:
            ws.all_orders[o.order_id] = o
            self.ch.freeze_collateral(ws, o)
            ws.pending_orders.append(o)

        result = self.ch.settle_all_expired(ws)

        assert result["settled"] == 2
        assert len(ws.pending_orders) == 1
        assert order1.status == "FULFILLED"
        assert order2.status == "FULFILLED"
        assert order_future.status == "ALLOCATED"

    def test_settle_all_expired_handles_default(self):
        good = _make_good(1, "bread", good_type="consumer", delivery_lag=1)
        seller = _make_firm(1, 5000.0)
        seller.inventory = {1: 1.0}
        buyer = _make_firm(2, 5000.0)

        ws = WorldState(
            tick=5,
            firms={1: seller, 2: buyer},
            goods={1: good},
        )

        order = _make_order(
            "o1",
            1,
            2,
            1,
            quantity=10.0,
            price=5.0,
            status="ALLOCATED",
            settlement_tick=5,
        )
        ws.all_orders["o1"] = order
        self.ch.freeze_collateral(ws, order)
        ws.pending_orders.append(order)

        result = self.ch.settle_all_expired(ws)

        assert result["defaulted"] == 1
        assert order.status == "DEFAULTED"


class TestExpireStaleOrders:
    def setup_method(self):
        self.ledger = TradeHistory()
        self.ch = ClearingHouse(self.ledger, base_collateral_ratio=0.1)

    def test_expire_stale_orders_removes_expired(self):
        good = _make_good(1, "bread", good_type="consumer")
        seller = _make_firm(1, 5000.0)
        buyer = _make_firm(2, 5000.0)

        ws = WorldState(
            tick=40,
            firms={1: seller, 2: buyer},
            goods={1: good},
        )

        order_old = _make_order("o1", 1, 2, 1, quantity=10.0, price=5.0, status="OPEN")
        order_new = _make_order("o2", 1, 2, 1, quantity=5.0, price=5.0, status="OPEN")
        order_old.creation_tick = 5
        order_new.creation_tick = 35

        for o in [order_old, order_new]:
            ws.all_orders[o.order_id] = o
            ws.market.supply.append(o)
            self.ch.freeze_collateral(ws, o)

        count = self.ch.expire_stale_orders(ws, expire_ticks=30)

        assert count == 1
        assert order_old.status == "EXPIRED"
        assert order_old not in ws.market.supply
        assert order_new.status == "OPEN"
        assert order_new in ws.market.supply

    def test_expire_stale_orders_releases_collateral(self):
        good = _make_good(1, "bread", good_type="consumer")
        seller = _make_firm(1, 5000.0)
        buyer = _make_firm(2, 5000.0)

        ws = WorldState(
            tick=40,
            firms={1: seller, 2: buyer},
            goods={1: good},
        )

        order = _make_order("o1", 1, 2, 1, quantity=10.0, price=5.0, status="OPEN")
        order.creation_tick = 5
        ws.all_orders["o1"] = order
        ws.market.supply.append(order)
        self.ch.freeze_collateral(ws, order)

        seller_cash_after_freeze = seller.cash
        buyer_cash_after_freeze = buyer.cash

        self.ch.expire_stale_orders(ws, expire_ticks=30)

        assert len(ws.collateral_pool) == 0
        assert seller.cash > seller_cash_after_freeze
        assert buyer.cash > buyer_cash_after_freeze

    def test_expire_stale_orders_from_demand_pool(self):
        good = _make_good(1, "bread", good_type="consumer")
        seller = _make_firm(1, 5000.0)
        buyer = _make_firm(2, 5000.0)

        ws = WorldState(
            tick=40,
            firms={1: seller, 2: buyer},
            goods={1: good},
        )

        order = _make_order("o1", 1, 2, 1, quantity=10.0, price=5.0, status="OPEN")
        order.creation_tick = 5
        ws.all_orders["o1"] = order
        ws.market.demand.append(order)
        self.ch.freeze_collateral(ws, order)

        count = self.ch.expire_stale_orders(ws, expire_ticks=30)
        assert count == 1
        assert order.status == "EXPIRED"
        assert order not in ws.market.demand
