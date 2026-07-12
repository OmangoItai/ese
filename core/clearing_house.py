from collections import deque
from typing import Dict, List, Tuple, Union

from core.entities import Firm, Household, Government, Good, Order, WorldState
from core.ledger import Ledger


class ClearingHouse:
    def __init__(
        self,
        ledger: Ledger,
        base_collateral_ratio: float = 0.1,
        fulfillment_window_ticks: int = 30,
    ):
        self.ledger = ledger
        self.base_collateral_ratio = base_collateral_ratio
        self.fulfillment_window_ticks = fulfillment_window_ticks
        self.price_history: Dict[int, deque] = {}

    # ———— Entity lookup ————

    @staticmethod
    def _get_entity(
        state: WorldState, entity_id: int
    ) -> Union[Firm, Household, Government, None]:
        entity = state.firms.get(entity_id)
        if entity is not None:
            return entity
        entity = state.households.get(entity_id)
        if entity is not None:
            return entity
        entity = state.governments.get(entity_id)
        if entity is not None:
            return entity
        return None

    # ———— Fulfillment rate ————

    @staticmethod
    def _fulfillment_rate(entity) -> float:
        log = entity._fulfillment_log
        if len(log) == 0:
            return 1.0
        fulfilled = sum(e[0] for e in log)
        defaulted = sum(e[1] for e in log)
        total = fulfilled + defaulted
        if total == 0:
            return 1.0
        return fulfilled / total

    @staticmethod
    def record_settlement(
        entity: Union[Firm, Household], success: bool, tick: int
    ) -> None:
        log = entity._fulfillment_log
        if len(log) == 0 or log[-1][2] != tick:
            log.append((0, 0, tick))
        fulfilled, defaulted, _ = log.pop()
        if success:
            log.append((fulfilled + 1, defaulted, tick))
        else:
            log.append((fulfilled, defaulted + 1, tick))

    # ———— Dynamic collateral ratio ————

    def calc_dynamic_collateral_ratio(self, entity: Union[Firm, Household]) -> float:
        rate = self._fulfillment_rate(entity)
        return self.base_collateral_ratio + (1.0 - rate) * 0.4

    # ———— Order validation ————

    def validate_order(self, state: WorldState, order: Order) -> Tuple[bool, str]:
        has_seller = order.seller_id != 0
        has_buyer = order.buyer_id != 0

        seller = self._get_entity(state, order.seller_id) if has_seller else None
        buyer = self._get_entity(state, order.buyer_id) if has_buyer else None

        if has_seller and seller is None:
            return False, f"Seller {order.seller_id} not found"
        if has_buyer and buyer is None:
            return False, f"Buyer {order.buyer_id} not found"

        order_value = order.price * order.quantity

        if has_seller:
            seller_ratio = self.calc_dynamic_collateral_ratio(seller)
            seller_freeze = order_value * seller_ratio
            if seller.cash < seller_freeze:
                return False, (
                    f"Seller {order.seller_id} insufficient cash: "
                    f"{seller.cash} < {seller_freeze}"
                )

        if has_buyer:
            buyer_ratio = self.calc_dynamic_collateral_ratio(buyer)
            buyer_freeze = order_value * buyer_ratio
            if buyer.cash < buyer_freeze:
                return False, (
                    f"Buyer {order.buyer_id} insufficient cash: "
                    f"{buyer.cash} < {buyer_freeze}"
                )

        good = state.goods.get(order.good_id)
        if good is not None and good.good_type == "labor":
            if has_seller and not isinstance(seller, Household):
                return False, "Labor order seller must be a Household"
            if has_buyer and not isinstance(buyer, Firm):
                return False, "Labor order buyer must be a Firm"

        return True, "OK"

    # ———— Collateral management ————

    def freeze_collateral(self, state: WorldState, order: Order) -> None:
        has_seller = order.seller_id != 0
        has_buyer = order.buyer_id != 0

        seller = self._get_entity(state, order.seller_id) if has_seller else None
        buyer = self._get_entity(state, order.buyer_id) if has_buyer else None

        order_value = order.price * order.quantity

        if has_seller:
            seller_ratio = self.calc_dynamic_collateral_ratio(seller)
            seller_freeze = order_value * seller_ratio
            seller.cash -= seller_freeze
            state.collateral_pool[f"{order.order_id}_seller"] = seller_freeze
            if isinstance(seller, (Firm, Household, Government)):
                seller.outstanding_order_ids.add(order.order_id)
        else:
            state.collateral_pool[f"{order.order_id}_seller"] = 0.0

        if has_buyer:
            buyer_ratio = self.calc_dynamic_collateral_ratio(buyer)
            buyer_freeze = order_value * buyer_ratio
            buyer.cash -= buyer_freeze
            state.collateral_pool[f"{order.order_id}_buyer"] = buyer_freeze
            if isinstance(buyer, (Firm, Household, Government)):
                buyer.outstanding_order_ids.add(order.order_id)
        else:
            state.collateral_pool[f"{order.order_id}_buyer"] = 0.0

    def release_collateral(self, state: WorldState, order: Order) -> None:
        seller_key = f"{order.order_id}_seller"
        buyer_key = f"{order.order_id}_buyer"

        seller_freeze = state.collateral_pool.pop(seller_key, 0.0)
        buyer_freeze = state.collateral_pool.pop(buyer_key, 0.0)

        seller = self._get_entity(state, order.seller_id)
        buyer = self._get_entity(state, order.buyer_id)

        if seller:
            seller.cash += seller_freeze
            if isinstance(seller, (Firm, Household, Government)):
                seller.outstanding_order_ids.discard(order.order_id)
        if buyer:
            buyer.cash += buyer_freeze
            if isinstance(buyer, (Firm, Household, Government)):
                buyer.outstanding_order_ids.discard(order.order_id)

    def forfeit_collateral(
        self, state: WorldState, order: Order, defaulting_side: str
    ) -> None:
        seller_key = f"{order.order_id}_seller"
        buyer_key = f"{order.order_id}_buyer"

        seller_freeze = state.collateral_pool.pop(seller_key, 0.0)
        buyer_freeze = state.collateral_pool.pop(buyer_key, 0.0)

        seller = self._get_entity(state, order.seller_id)
        buyer = self._get_entity(state, order.buyer_id)

        if defaulting_side == "seller":
            if buyer:
                buyer.cash += buyer_freeze + seller_freeze
                if isinstance(buyer, (Firm, Household, Government)):
                    buyer.outstanding_order_ids.discard(order.order_id)
            if seller and isinstance(seller, (Firm, Household, Government)):
                seller.outstanding_order_ids.discard(order.order_id)
        else:
            if seller:
                seller.cash += seller_freeze + buyer_freeze
                if isinstance(seller, (Firm, Household, Government)):
                    seller.outstanding_order_ids.discard(order.order_id)
            if buyer and isinstance(buyer, (Firm, Household, Government)):
                buyer.outstanding_order_ids.discard(order.order_id)

    # ———— Price tracking ————

    def record_settled_price(self, good_id: int, tick: int, price: float) -> None:
        if good_id not in self.price_history:
            self.price_history[good_id] = deque(maxlen=30)
        self.price_history[good_id].append((tick, price))

    def get_market_price_range(self, good_id: int) -> Tuple[float, float, float]:
        if good_id not in self.price_history or len(self.price_history[good_id]) == 0:
            return (0.0, 0.0, 0.0)
        prices = [p for _, p in self.price_history[good_id]]
        return (min(prices), max(prices), sum(prices) / len(prices))

    # ———— Order settlement ————

    def settle_order(self, state: WorldState, order: Order) -> Tuple[bool, str, bool]:
        """全量结算入口，仅处理 status=ALLOCATED 且 settlement_tick==state.tick 的订单。
        根据 good_type 自动分派到普通商品结算 (_settle_goods) 或劳动力结算 (_settle_labor)。
        返回 (ok, msg, liquidated)：liquidated==True 表示结算过程中触发了破产清算。
        """
        if order.status != "ALLOCATED":
            return False, f"Order {order.order_id} not ALLOCATED", False
        if order.settlement_tick != state.tick:
            return (
                False,
                (
                    f"Order {order.order_id} settlement_tick {order.settlement_tick}"
                    f" != state.tick {state.tick}"
                ),
                False,
            )

        good = state.goods.get(order.good_id)
        is_labor = good is not None and good.good_type == "labor"

        if is_labor:
            return self._settle_labor(state, order)

        return self._settle_goods(state, order)

    def _settle_goods(self, state: WorldState, order: Order) -> Tuple[bool, str, bool]:
        """普通商品 All-or-Nothing 全量结算。
        库存≥quantity 且 买方现金≥price*quantity → 转移库存、划拨货款、release_collateral、
        record_settled_price、双方记录履约成功、status=FULFILLED。
        任一不满足 → 判定违约方（库存不足=seller违约，现金不足=buyer违约），
        forfeit_collateral 将违约方抵押金转给对手方、status=DEFAULTED、双方记录履约失败。
        结算后若 Firm.cash<0 则立即触发 liquidate_firm。
        """
        seller = self._get_entity(state, order.seller_id)
        buyer = self._get_entity(state, order.buyer_id)

        if seller is None or buyer is None:
            return False, "Party not found", False

        seller_inventory = seller.inventory.get(order.good_id, 0.0)
        buyer_cash_sufficient = buyer.cash >= order.price * order.quantity
        seller_inventory_sufficient = seller_inventory >= order.quantity

        if seller_inventory_sufficient and buyer_cash_sufficient:
            seller.inventory[order.good_id] = seller_inventory - order.quantity
            buyer.inventory[order.good_id] = (
                buyer.inventory.get(order.good_id, 0.0) + order.quantity
            )
            buyer.cash -= order.price * order.quantity
            seller.cash += order.price * order.quantity

            self.release_collateral(state, order)
            self.record_settled_price(order.good_id, state.tick, order.price)
            self.record_settlement(seller, True, state.tick)
            self.record_settlement(buyer, True, state.tick)
            order.status = "FULFILLED"
            self.ledger.record_trade(order)

            if isinstance(buyer, (Firm, Household, Government)):
                buyer.outstanding_order_ids.discard(order.order_id)
            if isinstance(seller, (Firm, Household, Government)):
                seller.outstanding_order_ids.discard(order.order_id)

            liquidated = self._check_liquidation(state, buyer)
            if liquidated:
                return True, "FULFILLED", True
            liquidated = self._check_liquidation(state, seller)
            if liquidated:
                return True, "FULFILLED", True

            return True, "FULFILLED", False
        else:
            if not seller_inventory_sufficient:
                defaulting_side = "seller"
            else:
                defaulting_side = "buyer"

            self.forfeit_collateral(state, order, defaulting_side)
            self.record_settlement(seller, False, state.tick)
            self.record_settlement(buyer, False, state.tick)
            order.status = "DEFAULTED"
            self.ledger.record_trade(order)

            if isinstance(seller, (Firm, Household, Government)):
                seller.outstanding_order_ids.discard(order.order_id)
            if isinstance(buyer, (Firm, Household, Government)):
                buyer.outstanding_order_ids.discard(order.order_id)

            liquidated = False
            if defaulting_side == "seller" and isinstance(seller, Firm):
                liquidated = self._check_liquidation(state, seller)
            elif defaulting_side == "buyer" and isinstance(buyer, Firm):
                liquidated = self._check_liquidation(state, buyer)

            return False, f"DEFAULTED by {defaulting_side}", liquidated

    def _settle_labor(self, state: WorldState, order: Order) -> Tuple[bool, str, bool]:
        """劳动力订单结算（good_type="labor"）。
        seller=Household, buyer=Firm → household.is_employed=True, employer_firm_id=buyer.id,
        firm.employees 追加 seller.id。若 Household 此前已有雇主，先从旧 firm 的 employees 移除。
        release_collateral 释放双方抵押金，不记 price_history（劳动力无价格追踪）。
        """
        seller = self._get_entity(state, order.seller_id)
        buyer = self._get_entity(state, order.buyer_id)

        if seller is None or buyer is None:
            return False, "Party not found", False
        if not isinstance(seller, Household):
            return False, "Labor seller must be Household", False
        if not isinstance(buyer, Firm):
            return False, "Labor buyer must be Firm", False
        if not buyer.is_active:
            return False, "Buyer firm not active", False

        if seller.is_employed and seller.employer_firm_id is not None:
            old_employer = state.firms.get(seller.employer_firm_id)
            if old_employer and seller.id in old_employer.employees:
                old_employer.employees.remove(seller.id)

        seller.is_employed = True
        seller.employer_firm_id = buyer.id
        if seller.id not in buyer.employees:
            buyer.employees.append(seller.id)

        self.release_collateral(state, order)
        self.record_settlement(seller, True, state.tick)
        self.record_settlement(buyer, True, state.tick)
        order.status = "FULFILLED"
        self.ledger.record_trade(order)

        if isinstance(buyer, (Firm, Household, Government)):
            buyer.outstanding_order_ids.discard(order.order_id)

        return True, "FULFILLED (labor)", False

    def _check_liquidation(self, state: WorldState, entity) -> bool:
        """检查结算后的实体：若为 Firm 且 is_active 且 cash<0，则立即触发 liquidate_firm。
        返回 True 表示触发了破产清算。
        """
        if isinstance(entity, Firm) and entity.is_active and entity.cash < 0:
            self.liquidate_firm(state, entity.id)
            return True
        return False

    # ———— Batch settlement ————

    def settle_all_expired(self, state: WorldState) -> Dict:
        """批量结算到期订单。
        遍历 pending_orders 中 status=ALLOCATED 且 settlement_tick==state.tick 的订单，
        逐笔调用 settle_order。若结算过程中某 Firm 触发破产清算 (liquidate_firm)，
        则将该 Firm 剩余未到期的 pending_orders 级联标记为 DEFAULTED（由 _cascade_defaulted 处理）。
        结算完成后清理 pending_orders 中已终态的订单。
        返回 {"settled": N, "defaulted": N, "liquidated": [firm_ids]}。
        """
        expired = [
            o
            for o in state.pending_orders
            if o.status == "ALLOCATED" and o.settlement_tick == state.tick
        ]
        settled = 0
        defaulted = 0
        liquidated_firm_ids = []

        for order in expired:
            firm = (
                state.firms.get(order.seller_id)
                if isinstance(self._get_entity(state, order.seller_id), Firm)
                else state.firms.get(order.buyer_id)
                if isinstance(self._get_entity(state, order.buyer_id), Firm)
                else None
            )

            if firm and firm.id in liquidated_firm_ids:
                continue

            ok, _, liquidated_flag = self.settle_order(state, order)

            if ok:
                settled += 1
            else:
                defaulted += 1

            if liquidated_flag:
                lid = self._find_liquidated_firm(state)
                if lid:
                    liquidated_firm_ids.append(lid)
                    self._cascade_defaulted(
                        state, lid, pending_orders=state.pending_orders
                    )

        state.pending_orders = [
            o
            for o in state.pending_orders
            if o.status not in ("FULFILLED", "DEFAULTED", "CANCELLED", "EXPIRED")
        ]

        return {
            "settled": settled,
            "defaulted": defaulted,
            "liquidated": liquidated_firm_ids,
        }

    def _cascade_defaulted(
        self, state: WorldState, firm_id: int, pending_orders: List[Order]
    ) -> None:
        """级联违约：将破产 Firm 在 pending_orders 中的所有 ALLOCATED 订单标记为 DEFAULTED。
        调用 forfeit_collateral 将对手方抵押金释放，破产方抵押金已在 liquidate_firm 步骤(d)中追回。
        """
        firm = state.firms.get(firm_id)
        if firm is None:
            return
        for order in pending_orders:
            if order.status not in ("ALLOCATED",):
                continue
            if order.seller_id == firm_id or order.buyer_id == firm_id:
                defaulting_side = "seller" if order.seller_id == firm_id else "buyer"
                self.forfeit_collateral(state, order, defaulting_side)
                order.status = "DEFAULTED"
                self.ledger.record_trade(order)
                if firm:
                    firm.outstanding_order_ids.discard(order.order_id)

    # ———— Liquidation ————

    def liquidate_firm(self, state: WorldState, firm_id: int) -> Dict:
        """破产清算完整流程（设计 §3.2）。
        (a) 库存按 get_market_price_range.min 折价卖给 Government；
        (d) 追回 Firm 在各 collateral_pool 中的冻结抵押金并入 firm.cash；
        (b) 清偿顺序：拖欠工资（优先）→ 欠税 → 剩余归零（无股东追踪）；
        (c) 解雇所有员工（household.is_employed=False, employer_firm_id=None）；
        (e) 池中 OPEN 订单 → CANCELLED，释放对手方抵押金；
        (f) ALLOCATED 订单 → DEFAULTED，释放对手方抵押金；
        (g) is_active=False。
        返回包含 foreclosure_value、wages_paid 的 dict。
        """
        firm = state.firms.get(firm_id)
        if firm is None or not firm.is_active:
            return {"liquidated_firm": firm_id, "success": False}

        gov = next(iter(state.governments.values()), None)
        result = {
            "liquidated_firm": firm_id,
            "foreclosure_value": 0.0,
            "wages_paid": 0.0,
            "success": True,
        }

        # (a) Foreclosure: inventory → Government at min market price
        for good_id, qty in list(firm.inventory.items()):
            if qty <= 0:
                continue
            min_price, _, _ = self.get_market_price_range(good_id)
            if min_price == 0.0:
                min_price = 1.0
            total = min_price * qty
            if gov:
                gov.cash -= total
            firm.cash += total
            result["foreclosure_value"] += total

            fo = Order(
                order_id=f"foreclosure_{firm_id}_{good_id}_{state.tick}",
                seller_id=firm_id,
                buyer_id=gov.id if gov else -1,
                good_id=good_id,
                quantity=qty,
                price=min_price,
                description="foreclosure",
                creation_tick=state.tick,
                settlement_tick=state.tick,
                status="FULFILLED",
            )
            state.all_orders[fo.order_id] = fo
            self.ledger.record_trade(fo)

        firm.inventory.clear()

        # (d) Recover firm's frozen collateral → firm.cash
        firm_frozen_total = 0.0
        for oid in list(firm.outstanding_order_ids):
            order = state.all_orders.get(oid)
            if order is None:
                firm.outstanding_order_ids.discard(oid)
                continue
            frozen_key = (
                f"{oid}_seller" if order.seller_id == firm_id else f"{oid}_buyer"
            )
            if frozen_key in state.collateral_pool:
                firm_frozen_total += state.collateral_pool.pop(frozen_key, 0.0)

        firm.cash += firm_frozen_total

        # (b) Creditor distribution
        # 1. Wages (priority)
        for emp_id in list(firm.employees):
            hh = state.households.get(emp_id)
            if hh is None:
                continue
            wage = hh.labor_ask_price
            if firm.cash >= wage:
                firm.cash -= wage
                hh.cash += wage
                result["wages_paid"] += wage
            elif firm.cash > 0:
                hh.cash += firm.cash
                result["wages_paid"] += firm.cash
                firm.cash = 0.0
                break
            else:
                break

        # 2. Taxes (residual to government)
        if firm.cash > 0 and gov:
            tax_owed = firm.cash * gov.tax_rate
            firm.cash -= tax_owed
            gov.cash += tax_owed

        # 3. Remaining → absorbed (no shareholder tracking)
        firm.cash = 0.0

        # (c) Dismiss all employees
        for emp_id in list(firm.employees):
            hh = state.households.get(emp_id)
            if hh:
                hh.is_employed = False
                hh.employer_firm_id = None
        firm.employees.clear()

        # (e) & (f) Clean up counterparty orders
        for oid in list(firm.outstanding_order_ids):
            order = state.all_orders.get(oid)
            if order is None:
                firm.outstanding_order_ids.discard(oid)
                continue

            if order.status == "OPEN":
                order.status = "CANCELLED"
                self._release_counterparty(state, order, firm_id)
                if order in state.supply_pool:
                    state.supply_pool.remove(order)
                if order in state.demand_pool:
                    state.demand_pool.remove(order)
                self.ledger.record_trade(order)

            elif order.status == "ALLOCATED":
                order.status = "DEFAULTED"
                self._release_counterparty(state, order, firm_id)
                if order in state.pending_orders:
                    state.pending_orders.remove(order)
                self.ledger.record_trade(order)

            firm.outstanding_order_ids.discard(oid)

        # (g) Deactivate
        firm.is_active = False

        return result

    def _release_counterparty(
        self, state: WorldState, order: Order, firm_id: int
    ) -> None:
        counterparty_key = (
            f"{order.order_id}_buyer"
            if order.seller_id == firm_id
            else f"{order.order_id}_seller"
        )
        counterparty_id = (
            order.buyer_id if order.seller_id == firm_id else order.seller_id
        )
        frozen = state.collateral_pool.pop(counterparty_key, 0.0)
        counterparty = self._get_entity(state, counterparty_id)
        if counterparty:
            counterparty.cash += frozen
            if isinstance(counterparty, (Firm, Household, Government)):
                counterparty.outstanding_order_ids.discard(order.order_id)

    # ———— Pool expiration ————

    def expire_stale_orders(self, state: WorldState, expire_ticks: int) -> int:
        """池过期清理（设计 §3.2）。
        遍历 supply_pool 和 demand_pool 中 status=OPEN 的订单，
        creation_tick + expire_ticks <= state.tick 则标记 EXPIRED、
        release_collateral 释放双方抵押金、移出池。
        返回被过期的订单总数。expire_ticks 由 config 配置（默认 30）。
        """
        expired_count = 0
        for pool in [state.supply_pool, state.demand_pool]:
            to_expire = []
            for order in pool:
                if order.status == "OPEN" and (
                    order.creation_tick + expire_ticks <= state.tick
                ):
                    to_expire.append(order)
            for order in to_expire:
                order.status = "EXPIRED"
                self.release_collateral(state, order)
                self.ledger.record_trade(order)
                pool.remove(order)
                expired_count += 1
        return expired_count
