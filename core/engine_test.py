from core._registry import _StrategyRegistry
from core.entities import (
    AgentOrders,
    Firm,
    Government,
    Good,
    Household,
    Order,
    OrderSide,
    WorldState,
)
from core.data_layer import OrderFactory, Sequence
from core.engine import _AllocationSlot, _Slot


class _MockSimulator:
    def __init__(self, state: WorldState):
        self.state = state
        self.mi = None
        self.order_factory = OrderFactory(Sequence())

    def _dispatch_agent_result(self, state, result):
        pass


def _make_mock_sim(firms=None, households=None, governments=None):
    ws = WorldState(
        tick=0,
        firms=firms or {},
        households=households or {},
        governments=governments or {},
    )
    return _MockSimulator(ws)


class TestSlotRegistration:
    def test_call_registers_primary(self):
        reg = _StrategyRegistry()
        sim = _make_mock_sim()
        slot = _Slot(reg, "firm", lambda: [], sim)

        @slot
        def my_macro(mi, goods):
            pass

        assert reg.get("firm") is my_macro

    def test_call_returns_function(self):
        reg = _StrategyRegistry()
        sim = _make_mock_sim()
        slot = _Slot(reg, "firm", lambda: [], sim)

        @slot
        def my_macro(mi, goods):
            pass

        assert my_macro.__name__ == "my_macro"


class TestAllocationSlotPricing:
    def test_pricing_registers_and_retrieves(self):
        reg = _StrategyRegistry()
        sim = _make_mock_sim()
        slot = _AllocationSlot(reg, lambda: None, sim)

        @slot.pricing
        def mid_price(s, d, cfg, market):
            return (s.price + d.price) / 2.0

        assert reg.get_pricing() is mid_price


class TestSlotApply:
    def test_apply_dispatches_to_matching_entities(self):
        reg = _StrategyRegistry()
        firms = {
            1: Firm(id=1, cash=100.0, labels=["farm"]),
            2: Firm(id=2, cash=200.0, labels=["workshop"]),
        }
        sim = _make_mock_sim(firms=firms)
        slot = _Slot(reg, "firm", lambda: list(sim.state.firms.values()), sim)

        called = []

        def leaf_fn(entity, orders, mi, market):
            called.append(entity.id)

        results = slot.apply("farm", leaf_fn)

        assert len(called) == 1
        assert called[0] == 1
        assert len(results) == 1

    def test_apply_skips_non_matching_labels(self):
        reg = _StrategyRegistry()
        firms = {
            1: Firm(id=1, cash=100.0, labels=["farm"]),
            2: Firm(id=2, cash=200.0, labels=["workshop"]),
        }
        sim = _make_mock_sim(firms=firms)
        slot = _Slot(reg, "firm", lambda: list(sim.state.firms.values()), sim)

        called = []

        def leaf_fn(entity, orders, mi, market):
            called.append(entity.id)

        slot.apply("nonexistent", leaf_fn)

        assert len(called) == 0

    def test_apply_skips_inactive_entities(self):
        reg = _StrategyRegistry()
        firms = {
            1: Firm(id=1, cash=100.0, labels=["farm"], is_active=False),
            2: Firm(id=2, cash=200.0, labels=["farm"], is_active=True),
        }
        sim = _make_mock_sim(firms=firms)
        slot = _Slot(reg, "firm", lambda: list(sim.state.firms.values()), sim)

        called = []

        def leaf_fn(entity, orders, mi, market):
            called.append(entity.id)

        results = slot.apply("farm", leaf_fn)

        assert len(called) == 1
        assert called[0] == 2
        assert len(results) == 1

    def test_apply_hits_multiple_matching_labels(self):
        reg = _StrategyRegistry()
        firms = {
            1: Firm(id=1, cash=100.0, labels=["farm", "food"]),
            2: Firm(id=2, cash=200.0, labels=["workshop"]),
            3: Firm(id=3, cash=300.0, labels=["farm", "tech"]),
        }
        sim = _make_mock_sim(firms=firms)
        slot = _Slot(reg, "firm", lambda: list(sim.state.firms.values()), sim)

        called = []

        def leaf_fn(entity, orders, mi, market):
            called.append(entity.id)

        results = slot.apply("farm", leaf_fn)

        assert sorted(called) == [1, 3]
        assert len(results) == 2

    def test_apply_returns_leaf_fn_results(self):
        reg = _StrategyRegistry()
        firms = {
            1: Firm(id=1, cash=100.0, labels=["farm"]),
        }
        sim = _make_mock_sim(firms=firms)
        slot = _Slot(reg, "firm", lambda: list(sim.state.firms.values()), sim)

        def leaf_fn(entity, orders, mi, market):
            return {"capacity": entity.cash}

        results = slot.apply("farm", leaf_fn)

        assert len(results) == 1
        assert results[0] == {"capacity": 100.0}

    def test_apply_passes_extra_params_to_leaf(self):
        reg = _StrategyRegistry()
        firms = {
            1: Firm(id=1, cash=100.0, labels=["farm"]),
        }
        sim = _make_mock_sim(firms=firms)
        slot = _Slot(reg, "firm", lambda: list(sim.state.firms.values()), sim)

        received_params = {}

        def leaf_fn(entity, orders, mi, market, **kwargs):
            received_params.update(kwargs)

        slot.apply("farm", leaf_fn, target=500.0, quota={"output": 10})

        assert received_params == {"target": 500.0, "quota": {"output": 10}}

    def test_apply_to_household_slot(self):
        reg = _StrategyRegistry()
        households = {
            101: Household(id=101, cash=200.0, labels=["worker"]),
            102: Household(id=102, cash=50.0, labels=["unemployed"]),
        }
        sim = _make_mock_sim(households=households)
        slot = _Slot(reg, "household", lambda: list(sim.state.households.values()), sim)

        called = []

        def leaf_fn(entity, orders, mi, market):
            called.append(entity.id)

        results = slot.apply("worker", leaf_fn)

        assert called == [101]
        assert len(results) == 1

    def test_apply_to_government_slot(self):
        reg = _StrategyRegistry()
        govs = {
            1: Government(id=1, cash=50000.0, labels=["default"]),
        }
        sim = _make_mock_sim(governments=govs)
        slot = _Slot(
            reg, "government", lambda: list(sim.state.governments.values()), sim
        )

        called = []

        def leaf_fn(entity, orders, mi, market):
            called.append(entity.id)

        results = slot.apply("default", leaf_fn)

        assert called == [1]
        assert len(results) == 1
