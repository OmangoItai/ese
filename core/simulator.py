from typing import Dict, List

import yaml

from core.clearing_house import ClearingHouse
from core.data_layer import OrderFactory, Sequence, WorldLoader
from core.entities import AgentOrders, Order, OrderSide, WorldState
from core.market_intelligence import MarketIntelligence, MarketIntelligenceBuilder
from core.noise import InformationFriction
from core.reporter import Reporter


class Simulator:
    def __init__(self, config_path: str, world_db_path: str, strategy_registry=None):
        self.config = self._load_config(config_path)
        self.noise = InformationFriction(seed=self.config.get("seed", 42))
        self.reporter = Reporter()
        self._id_seq = Sequence()
        self.order_factory = OrderFactory(self._id_seq)
        self.state = WorldLoader.load(world_db_path)
        self.clearing = ClearingHouse(
            ledger=self.state.market.history,
            base_collateral_ratio=self.config.get("base_collateral_ratio", 0.1),
            fulfillment_window_ticks=self.config.get("fulfillment_window_ticks", 30),
        )
        self.order_expire_ticks = self.config.get("order_expire_ticks", 30)
        self.mi_builder = MarketIntelligenceBuilder(
            self.noise, self.reporter, self.config
        )
        self.mi = self.mi_builder.build(self.state, self.state.market.history)
        self._reg = strategy_registry

    @staticmethod
    def _load_config(config_path: str) -> Dict:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def tick(self) -> WorldState:
        state = self.state

        # 1. 结算到期订单
        self.clearing.settle_all_expired(state)

        # 2. 发放工资（Firm→Household，按 labor_ask_price）
        self._pay_wages(state)

        # 3. 征税（Firm→Government，按 gov.tax_rate）
        self._collect_taxes(state)

        # 4. 发放失业金（Government→失业 Household，按 unemployment_benefit）
        self._disburse_unemployment(state)

        # 5. Strategy：用户策略 → new/cancel/update → validate → freeze → 入池
        self._execute_strategy(self.mi, state)

        # 6. Allocation：用户分配策略 → 从池中配对 → ALLOCATED → 入 pending_orders
        self._execute_allocation(self.mi, state)

        # 7. 池维护：过期订单释放抵押品
        self.clearing.expire_stale_orders(state, self.order_expire_ticks)

        # 8. 实体 end_tick + Tick++
        self._end_tick_for_all(state)
        state.tick += 1

        # 9. 构建 MarketIntelligence（含噪声），缓存供下一 Tick 使用
        self.mi = self.mi_builder.build(state, state.market.history)

        return state

    def run(self, n_ticks: int) -> List[Dict]:
        snapshots = []
        for _ in range(n_ticks):
            self.tick()
            snapshots.append(
                self.reporter.snapshot(self.state, self.state.market.history)
            )
        return snapshots

    def _pay_wages(self, state: WorldState) -> None:
        for firm in state.firms.values():
            if not firm.is_active:
                continue
            for emp_id in list(firm.employees):
                hh = state.households.get(emp_id)
                if hh is None:
                    firm.employees.remove(emp_id)
                    continue
                wage = hh.labor_ask_price
                if firm.cash >= wage:
                    firm.cash -= wage
                    hh.cash += wage
                    self.clearing.record_settlement(firm, True, state.tick)
                    self.clearing.record_settlement(hh, True, state.tick)
                else:
                    self.clearing.record_settlement(firm, False, state.tick)
                    self.clearing.record_settlement(hh, False, state.tick)

    def _collect_taxes(self, state: WorldState) -> None:
        for gov_id in sorted(state.governments.keys()):
            gov = state.governments[gov_id]
            if gov.tax_rate <= 0:
                continue
            for firm in state.firms.values():
                if not firm.is_active or firm.cash <= 0:
                    continue
                tax = firm.cash * gov.tax_rate
                firm.cash -= tax
                gov.cash += tax

    def _disburse_unemployment(self, state: WorldState) -> None:
        for gov in state.governments.values():
            if gov.unemployment_benefit <= 0 or gov.cash <= 0:
                continue
            unemployed = [
                hh
                for hh in state.households.values()
                if not hh.is_employed and hh.unemployment_ticks > 0
            ]
            if not unemployed:
                continue
            total_needed = len(unemployed) * gov.unemployment_benefit
            if gov.cash >= total_needed:
                for hh in unemployed:
                    gov.cash -= gov.unemployment_benefit
                    hh.cash += gov.unemployment_benefit
            else:
                ratio = gov.cash / total_needed
                for hh in unemployed:
                    amount = gov.unemployment_benefit * ratio
                    gov.cash -= amount
                    hh.cash += amount

    def _execute_strategy(self, mi: MarketIntelligence, state: WorldState) -> None:
        firm_fn = self._reg.get("firm") if self._reg else None
        if firm_fn is not None:
            for firm in state.firms.values():
                if not firm.is_active:
                    continue
                my_orders = firm.outstanding_orders(state.all_orders)
                orders = AgentOrders(my_orders, self.order_factory)
                firm_fn(mi, firm, state.goods, orders)
                self._dispatch_agent_result(state, orders._consume())

        hh_fn = self._reg.get("household") if self._reg else None
        if hh_fn is not None:
            for hh in state.households.values():
                my_orders = hh.outstanding_orders(state.all_orders)
                orders = AgentOrders(my_orders, self.order_factory)
                hh_fn(mi, hh, state.goods, orders)
                self._dispatch_agent_result(state, orders._consume())

        gov_fn = self._reg.get("government") if self._reg else None
        if gov_fn is not None:
            for gov in state.governments.values():
                my_orders = gov.outstanding_orders(state.all_orders)
                orders = AgentOrders(my_orders, self.order_factory)
                gov_fn(mi, gov, state.goods, orders)
                self._dispatch_agent_result(state, orders._consume())

    def _dispatch_agent_result(
        self,
        state: WorldState,
        result: Dict,
    ) -> None:
        if not isinstance(result, dict):
            return

        new_orders = result.get("new", [])
        cancel_ids = result.get("cancel", [])
        update_orders = result.get("update", [])

        for order_id in cancel_ids:
            self._cancel_order(state, order_id)

        for new_order in update_orders:
            if not isinstance(new_order, Order):
                continue
            orig_order_id = new_order.order_id
            ok, _ = self.clearing.validate_order(state, new_order)
            if not ok:
                continue
            self._cancel_order(state, orig_order_id)
            self._add_new_order(state, new_order)

        for new_order in new_orders:
            if not isinstance(new_order, Order):
                continue
            ok, _ = self.clearing.validate_order(state, new_order)
            if not ok:
                continue
            self._add_new_order(state, new_order)

    def _add_new_order(self, state: WorldState, order: Order) -> None:
        order.creation_tick = state.tick
        order.status = "OPEN"
        state.all_orders[order.order_id] = order
        self.clearing.freeze_collateral(state, order)

        if order.side == OrderSide.SUPPLY:
            state.market.supply.append(order)
        elif order.side == OrderSide.DEMAND:
            state.market.demand.append(order)

    def _cancel_order(self, state: WorldState, order_id: str) -> None:
        order = state.all_orders.get(order_id)
        if order is None or order.status != "OPEN":
            return

        self.clearing.release_collateral(state, order)
        order.status = "CANCELLED"
        state.market.history.record_trade(order)

        if order in state.market.supply:
            state.market.supply.remove(order)
        if order in state.market.demand:
            state.market.demand.remove(order)

    def _execute_allocation(self, mi: MarketIntelligence, state: WorldState) -> None:
        allocate_fn = self._reg.get("allocation") if self._reg else None
        if allocate_fn is None:
            return

        pricing_fn = self._reg.get_pricing() if self._reg else None

        matched, remaining_supply, remaining_demand = allocate_fn(
            mi,
            list(state.market.supply),
            list(state.market.demand),
            state.goods,
            pricing_fn,
        )

        state.market.supply = remaining_supply
        state.market.demand = remaining_demand

        for order in matched:
            order.status = "ALLOCATED"
            good = state.goods.get(order.good_id)
            lag = good.delivery_lag if good else 1
            order.settlement_tick = state.tick + lag
            state.all_orders[order.order_id] = order
            state.pending_orders.append(order)
            state.market.history.record_trade(order)

    def _end_tick_for_all(self, state: WorldState) -> None:
        for hh in state.households.values():
            if not hh.is_employed:
                hh.unemployment_ticks += 1
