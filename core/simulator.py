import sqlite3
from copy import deepcopy
from typing import Dict, List

import yaml

from core.clearing_house import ClearingHouse
from core.entities import Firm, Good, Government, Household, Order, WorldState
from core.ledger import Ledger
from core.noise import InformationFriction
from core.reporter import Reporter
from core.registry import Registry

VALID_GOOD_TYPES = {"food", "labor", "capital", "consumer", "raw_material"}


class Simulator:
    def __init__(self, config_path: str, world_db_path: str):
        self.config = self._load_config(config_path)
        self.ledger = Ledger()
        self.noise = InformationFriction(seed=self.config.get("seed", 42))
        self.clearing = ClearingHouse(
            ledger=self.ledger,
            base_collateral_ratio=self.config.get("base_collateral_ratio", 0.1),
            fulfillment_window_ticks=self.config.get("fulfillment_window_ticks", 30),
        )
        self.reporter = Reporter()
        self.state = self._load_world(world_db_path)
        self.order_expire_ticks = self.config.get("order_expire_ticks", 30)
        self.last_obs = self._build_observations(self.state)
        self.registry = Registry()

    def set_registry(self, registry: "Registry") -> None:
        self.registry = registry

    @staticmethod
    def _load_config(config_path: str) -> Dict:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def _load_world(db_path: str) -> WorldState:
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
            c.execute("SELECT id, cash, capacity, collateral, is_active FROM firms")
            for row in c.fetchall():
                fid, cash, capacity, collateral, is_active = row
                firms[fid] = Firm(
                    id=fid,
                    cash=float(cash),
                    capacity=float(capacity),
                    collateral=float(collateral),
                    is_active=bool(is_active),
                )

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
                "SELECT id, cash, labor_ask_price, is_employed, "
                "employer_firm_id, unemployment_ticks FROM households"
            )
            for row in c.fetchall():
                hid, cash, labor_ask_price, is_employed, employer_firm_id, uticks = row
                households[hid] = Household(
                    id=hid,
                    cash=float(cash),
                    labor_ask_price=float(labor_ask_price),
                    is_employed=bool(is_employed),
                    employer_firm_id=employer_firm_id,
                    unemployment_ticks=uticks,
                )

            c.execute("SELECT household_id, good_id, quantity FROM household_inventory")
            for row in c.fetchall():
                household_id, good_id, quantity = row
                if household_id in households:
                    households[household_id].inventory[good_id] = float(quantity)

            governments: Dict[int, Government] = {}
            c.execute(
                "SELECT id, cash, tax_rate, money_supply, unemployment_benefit "
                "FROM governments"
            )
            for row in c.fetchall():
                gid, cash, tax_rate, money_supply, unemployment_benefit = row
                governments[gid] = Government(
                    id=gid,
                    cash=float(cash),
                    tax_rate=float(tax_rate),
                    money_supply=float(money_supply),
                    unemployment_benefit=float(unemployment_benefit),
                )

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
                supply_pool=[],
                demand_pool=[],
                pending_orders=[],
                all_orders={},
                collateral_pool={},
            )
        finally:
            conn.close()

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
        self._execute_strategy(self.last_obs, state)

        # 6. Allocation：用户分配策略 → 从池中配对 → ALLOCATED → 入 pending_orders
        self._execute_allocation(self.last_obs, state)

        # 7. 池维护：过期订单释放抵押品
        self.clearing.expire_stale_orders(state, self.order_expire_ticks)

        # 8. 实体 end_tick + Tick++
        self._end_tick_for_all(state)
        state.tick += 1

        # 9. 构建观测数据（含噪声），缓存供下一 Tick 使用
        self.last_obs = self._build_observations(state)

        return state

    def run(self, n_ticks: int) -> List[Dict]:
        snapshots = []
        for _ in range(n_ticks):
            self.tick()
            snapshots.append(self.reporter.snapshot(self.state, self.ledger))
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

    def _execute_strategy(self, obs: Dict, state: WorldState) -> None:
        for firm in state.firms.values():
            if not firm.is_active:
                continue
            strategy = self.registry.get("firm")
            if strategy is None:
                continue
            agent_obs = self._agent_obs(obs, state, firm.id, "firm")
            self._dispatch_agent_result(
                agent_obs,
                state,
                firm.id,
                "firm",
                strategy(agent_obs, firm, state.goods),
            )

        for hh in state.households.values():
            strategy = self.registry.get("household")
            if strategy is None:
                continue
            agent_obs = self._agent_obs(obs, state, hh.id, "household")
            self._dispatch_agent_result(
                agent_obs,
                state,
                hh.id,
                "household",
                strategy(agent_obs, hh, state.goods),
            )

        for gov in state.governments.values():
            strategy = self.registry.get("government")
            if strategy is None:
                continue
            agent_obs = self._agent_obs(obs, state, gov.id, "government")
            self._dispatch_agent_result(
                agent_obs,
                state,
                gov.id,
                "government",
                strategy(agent_obs, gov, state.goods),
            )

    def _dispatch_agent_result(
        self,
        agent_obs: Dict,
        state: WorldState,
        entity_id: int,
        role: str,
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

        if order.seller_id != 0:
            state.supply_pool.append(order)
        if order.buyer_id != 0:
            state.demand_pool.append(order)

    def _cancel_order(self, state: WorldState, order_id: str) -> None:
        order = state.all_orders.get(order_id)
        if order is None or order.status != "OPEN":
            return

        self.clearing.release_collateral(state, order)
        order.status = "CANCELLED"
        self.ledger.record_trade(order)

        if order in state.supply_pool:
            state.supply_pool.remove(order)
        if order in state.demand_pool:
            state.demand_pool.remove(order)

    def _execute_allocation(self, obs: Dict, state: WorldState) -> None:
        allocate_fn = self.registry.get("allocation")
        if allocate_fn is None:
            return

        matched, remaining_supply, remaining_demand = allocate_fn(
            obs, list(state.supply_pool), list(state.demand_pool), state.goods
        )

        state.supply_pool = remaining_supply
        state.demand_pool = remaining_demand

        for order in matched:
            order.status = "ALLOCATED"
            good = state.goods.get(order.good_id)
            lag = good.delivery_lag if good else 1
            order.settlement_tick = state.tick + lag
            state.all_orders[order.order_id] = order
            state.pending_orders.append(order)
            self.ledger.record_trade(order)

    def _end_tick_for_all(self, state: WorldState) -> None:
        for hh in state.households.values():
            if not hh.is_employed:
                hh.unemployment_ticks += 1

    def _build_observations(self, state: WorldState) -> Dict:
        noise_type = self.config.get("noise_type", "none")
        noise_params = self.config.get("noise_params", {})

        all_firms = [deepcopy(f) for f in state.firms.values() if f.is_active]
        all_households = [deepcopy(h) for h in state.households.values()]
        governments_list = [deepcopy(g) for g in state.governments.values()]

        for f in all_firms:
            f.cash = self.noise.apply_noise(float(f.cash), noise_type, noise_params)
            f.collateral = self.noise.apply_noise(
                float(f.collateral), noise_type, noise_params
            )

        for h in all_households:
            h.cash = self.noise.apply_noise(float(h.cash), noise_type, noise_params)

        for g in governments_list:
            g.cash = self.noise.apply_noise(float(g.cash), noise_type, noise_params)

        return {
            "all_firms": all_firms,
            "all_households": all_households,
            "governments": governments_list,
            "tick": state.tick,
            "_firms_map": state.firms,
            "_households_map": state.households,
            "_governments_map": state.governments,
        }

    def _agent_obs(
        self, shared_obs: Dict, state: WorldState, agent_id: int, role: str
    ) -> Dict:
        entity = None
        if role == "firm":
            entity = state.firms.get(agent_id)
        elif role == "household":
            entity = state.households.get(agent_id)
        elif role == "government":
            entity = state.governments.get(agent_id)

        my_supply = [
            o
            for o in state.supply_pool
            if (o.seller_id == agent_id or o.buyer_id == agent_id)
        ]
        my_demand = [
            o
            for o in state.demand_pool
            if (o.seller_id == agent_id or o.buyer_id == agent_id)
        ]

        return {
            "my_id": agent_id,
            "my_state": deepcopy(entity) if entity is not None else None,
            "my_supply_orders": my_supply,
            "my_demand_orders": my_demand,
            "all_firms": shared_obs["all_firms"],
            "all_households": shared_obs["all_households"],
            "governments": shared_obs["governments"],
            "tick": shared_obs["tick"],
        }
