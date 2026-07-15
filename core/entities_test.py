from collections import deque
from core.entities import (
    AgentOrders,
    Good,
    Order,
    Firm,
    Household,
    Government,
    WorldState,
    OrderSide,
)


class TestGood:
    def test_default_values(self):
        g = Good(good_id=1, name="bread")
        assert g.good_id == 1
        assert g.name == "bread"
        assert g.good_type == "consumer"
        assert g.delivery_lag == 1

    def test_labor_good(self):
        g = Good(good_id=2, name="labor", good_type="labor", delivery_lag=1)
        assert g.good_type == "labor"

    def test_capital_good(self):
        g = Good(good_id=3, name="oven", good_type="capital", delivery_lag=3)
        assert g.delivery_lag == 3


class TestOrder:
    def test_default_values(self):
        o = Order(
            order_id="ord_1",
            seller_id=1,
            buyer_id=2,
            good_id=1,
            quantity=10.0,
            price=5.0,
        )
        assert o.order_id == "ord_1"
        assert o.description == ""
        assert o.creation_tick == 0
        assert o.settlement_tick == 0
        assert o.status == "OPEN"

    def test_six_status_states(self):
        valid_statuses = {
            "OPEN",
            "ALLOCATED",
            "FULFILLED",
            "DEFAULTED",
            "CANCELLED",
            "EXPIRED",
        }
        o = Order(
            order_id="ord_2",
            seller_id=1,
            buyer_id=2,
            good_id=1,
            quantity=10.0,
            price=5.0,
        )
        for s in valid_statuses:
            o.status = s
            assert o.status == s

    def test_order_side_enum(self):
        from core.entities import OrderSide

        for side in (OrderSide.SUPPLY, OrderSide.DEMAND):
            o = Order(
                order_id="ord_test",
                seller_id=1,
                buyer_id=2,
                good_id=1,
                quantity=10.0,
                price=5.0,
                side=side,
            )
            assert o.side == side

    def test_settlement_tick_sentinel(self):
        o = Order(
            order_id="ord_4",
            seller_id=1,
            buyer_id=2,
            good_id=1,
            quantity=10.0,
            price=5.0,
        )
        assert o.settlement_tick == 0


class TestFirm:
    def test_default_values(self):
        f = Firm(id=1, cash=1000.0)
        assert f.id == 1
        assert f.cash == 1000.0
        assert f.inventory == {}
        assert f.capacity == 0.0
        assert f.collateral == 0.0
        assert f.is_active is True
        assert f.employees == []
        assert f.outstanding_order_ids == set()

    def test_fulfillment_log_initial(self):
        f = Firm(id=1, cash=1000.0)
        assert isinstance(f._fulfillment_log, deque)
        assert f._fulfillment_log.maxlen == 30
        assert len(f._fulfillment_log) == 0

    def test_fulfillment_log_is_independent(self):
        f1 = Firm(id=1, cash=1000.0)
        f2 = Firm(id=2, cash=2000.0)
        f1._fulfillment_log.append((3, 0, 5))
        assert len(f2._fulfillment_log) == 0

    def test_custom_fields(self):
        f = Firm(
            id=5,
            cash=5000.0,
            inventory={1: 100.0, 2: 50.0},
            capacity=20.0,
            collateral=300.0,
            is_active=False,
            employees=[10, 11],
            outstanding_order_ids={"o1", "o2"},
        )
        assert f.inventory == {1: 100.0, 2: 50.0}
        assert f.employees == [10, 11]
        assert f.outstanding_order_ids == {"o1", "o2"}
        assert f.is_active is False


class TestHousehold:
    def test_default_values(self):
        h = Household(id=1, cash=500.0)
        assert h.id == 1
        assert h.cash == 500.0
        assert h.inventory == {}
        assert h.labor_ask_price == 0.0
        assert h.is_employed is False
        assert h.employer_firm_id is None
        assert h.unemployment_ticks == 0

    def test_fulfillment_log_initial(self):
        h = Household(id=1, cash=500.0)
        assert isinstance(h._fulfillment_log, deque)
        assert h._fulfillment_log.maxlen == 30
        assert len(h._fulfillment_log) == 0

    def test_employed_state(self):
        h = Household(id=2, cash=500.0, is_employed=True, employer_firm_id=3)
        assert h.is_employed is True
        assert h.employer_firm_id == 3


class TestGovernment:
    def test_default_values(self):
        g = Government(id=1, cash=10000.0)
        assert g.id == 1
        assert g.cash == 10000.0
        assert g.tax_rate == 0.0
        assert g.money_supply == 0.0
        assert g.unemployment_benefit == 0.0

    def test_fulfillment_log_initial(self):
        g = Government(id=1, cash=10000.0)
        assert isinstance(g._fulfillment_log, deque)
        assert g._fulfillment_log.maxlen == 30
        assert len(g._fulfillment_log) == 0

    def test_with_policy(self):
        g = Government(id=1, cash=10000.0, tax_rate=0.2, unemployment_benefit=50.0)
        assert g.tax_rate == 0.2
        assert g.unemployment_benefit == 50.0


class TestWorldState:
    def test_default_construction(self):
        ws = WorldState(tick=0)
        assert ws.tick == 0
        assert ws.firms == {}
        assert ws.households == {}
        assert ws.governments == {}
        assert ws.goods == {}
        assert ws.market.supply == []
        assert ws.market.demand == []
        assert ws.pending_orders == []
        assert ws.all_orders == {}
        assert ws.collateral_pool == {}

    def test_nested_assembly(self):
        bread = Good(good_id=1, name="bread")
        labor = Good(good_id=2, name="labor", good_type="labor")
        firm = Firm(id=1, cash=10000.0, inventory={1: 500.0})
        hh = Household(
            id=1, cash=1000.0, inventory={1: 50.0}, is_employed=True, employer_firm_id=1
        )
        gov = Government(id=1, cash=50000.0, tax_rate=0.15, unemployment_benefit=30.0)

        ws = WorldState(
            tick=0,
            firms={1: firm},
            households={1: hh},
            governments={1: gov},
            goods={1: bread, 2: labor},
        )

        assert len(ws.firms) == 1
        assert len(ws.households) == 1
        assert len(ws.governments) == 1
        assert len(ws.goods) == 2

    def test_worldstate_modify_firm_reflected(self):
        firm = Firm(id=1, cash=5000.0)
        ws = WorldState(tick=0, firms={1: firm})
        ws.firms[1].cash -= 100.0
        assert firm.cash == 4900.0
        assert ws.firms[1].cash == 4900.0

    def test_all_orders_index(self):
        o = Order(
            order_id="o1", seller_id=1, buyer_id=2, good_id=1, quantity=5.0, price=10.0
        )
        ws = WorldState(tick=1, all_orders={"o1": o})
        assert ws.all_orders["o1"].order_id == "o1"
        assert ws.all_orders["o1"].status == "OPEN"

    def test_collateral_pool_empty(self):
        ws = WorldState(tick=0)
        assert isinstance(ws.collateral_pool, dict)
        assert len(ws.collateral_pool) == 0


class TestAgentOrders:
    def _make_order(self, order_id, **kwargs):
        return Order(
            order_id=order_id,
            seller_id=kwargs.get("seller_id", 1),
            buyer_id=kwargs.get("buyer_id", 2),
            good_id=kwargs.get("good_id", 1),
            quantity=kwargs.get("quantity", 10.0),
            price=kwargs.get("price", 5.0),
            side=kwargs.get("side", OrderSide.SUPPLY),
        )

    def test_construction_and_iteration(self):
        o1 = self._make_order("o1")
        o2 = self._make_order("o2")
        orders = AgentOrders([o1, o2])
        assert len(orders) == 2
        assert orders[0].order_id == "o1"
        assert [o.order_id for o in orders] == ["o1", "o2"]

    def test_new_records_intent(self):
        orders = AgentOrders([])
        orders.new(
            seller_id=1,
            buyer_id=2,
            good_id=3,
            quantity=5.0,
            price=10.0,
            side=OrderSide.SUPPLY,
            description="test",
        )
        assert len(orders._new) == 1
        assert orders._new[0]["seller_id"] == 1
        assert orders._new[0]["description"] == "test"

    def test_cancel_records_intent(self):
        orders = AgentOrders([])
        orders.cancel("o1")
        orders.cancel("o2")
        assert orders._cancel == ["o1", "o2"]

    def test_update_records_intent(self):
        orders = AgentOrders([])
        orders.update(
            "old",
            seller_id=1,
            buyer_id=2,
            good_id=3,
            quantity=5.0,
            price=10.0,
            side=OrderSide.DEMAND,
        )
        assert len(orders._update) == 1
        assert orders._update[0]["order_id"] == "old"

    def test_consume_returns_empty_when_no_factory(self):
        orders = AgentOrders([])
        orders.new(seller_id=1, buyer_id=2, good_id=3, quantity=5.0, price=10.0)
        orders.cancel("o1")
        orders.update(
            "oid", seller_id=1, buyer_id=2, good_id=3, quantity=5.0, price=10.0
        )
        result = orders._consume()
        assert result["new"] == []
        assert result["cancel"] == ["o1"]
        assert result["update"] == []
        assert len(orders._new) == 0
        assert len(orders._cancel) == 0

    def test_consume_with_factory_creates_orders(self):
        from core.data_layer import OrderFactory, Sequence

        seq = Sequence()
        factory = OrderFactory(seq)
        o1 = self._make_order("existing")
        orders = AgentOrders([o1], order_factory=factory)
        orders.new(seller_id=1, buyer_id=2, good_id=3, quantity=5.0, price=10.0)
        orders.cancel("existing")
        result = orders._consume()
        assert len(result["new"]) == 1
        assert isinstance(result["new"][0], Order)
        assert result["new"][0].order_id.startswith("order_")
        assert result["cancel"] == ["existing"]
