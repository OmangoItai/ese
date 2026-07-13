import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Tuple, List

from ese import (
    Engine,
    Good,
    Government,
    MarketIntelligence,
    Order,
    OrderSide,
)

# ============================================================
# 初始化引擎
# ============================================================

ese = Engine(
    "config/default.yaml", "examples/town_world.db", output_dir="./examples/results"
)

# ============================================================
# 企业策略
# ============================================================


@ese.firm
def firm_orchestrator(mi: MarketIntelligence, firm, goods: Dict[int, Good], orders):
    """调度器：按 strategy_label 分发到标签策略"""
    ese.firm.use(firm.strategy_label, mi, firm, goods, orders)


@ese.firm.label("farm")
def farm_strategy(mi: MarketIntelligence, firm, goods: Dict[int, Good], orders):
    """农场：消耗工具 → 产出食物 → 卖食物、买工具"""
    # 生产：1 工具 → 5 食物
    tool_inv = firm.inventory.get(2, 0.0)
    if tool_inv >= 1.0:
        firm.inventory[2] = tool_inv - 1.0
        firm.inventory[1] = firm.inventory.get(1, 0.0) + 5.0

    # 挂单卖食物（留 2 做安全库存）
    food_qty = firm.inventory.get(1, 0.0)
    if food_qty > 2.0:
        sell_qty = min(food_qty - 2.0, 10.0)
        orders.new(
            seller_id=firm.id,
            buyer_id=0,
            good_id=1,
            quantity=sell_qty,
            price=2.0,
            side=OrderSide.SUPPLY,
            description="农场卖食物",
        )

    # 工具库存不足时采购
    if firm.cash > 50.0 and firm.inventory.get(2, 0.0) < 10.0:
        orders.new(
            seller_id=0,
            buyer_id=firm.id,
            good_id=2,
            quantity=2.0,
            price=3.0,
            side=OrderSide.DEMAND,
            description="农场买工具",
        )


@ese.firm.label("workshop")
def workshop_strategy(mi: MarketIntelligence, firm, goods: Dict[int, Good], orders):
    """工坊：消耗食物 → 产出工具 → 卖工具、买食物"""
    # 生产：2 食物 → 3 工具
    food_inv = firm.inventory.get(1, 0.0)
    if food_inv >= 2.0:
        firm.inventory[1] = food_inv - 2.0
        firm.inventory[2] = firm.inventory.get(2, 0.0) + 3.0

    # 挂单卖工具
    tool_qty = firm.inventory.get(2, 0.0)
    if tool_qty > 2.0:
        sell_qty = min(tool_qty - 2.0, 5.0)
        orders.new(
            seller_id=firm.id,
            buyer_id=0,
            good_id=2,
            quantity=sell_qty,
            price=3.0,
            side=OrderSide.SUPPLY,
            description="工坊卖工具",
        )

    # 食物库存不足时采购
    if firm.cash > 50.0 and firm.inventory.get(1, 0.0) < 10.0:
        orders.new(
            seller_id=0,
            buyer_id=firm.id,
            good_id=1,
            quantity=3.0,
            price=2.0,
            side=OrderSide.DEMAND,
            description="工坊买食物",
        )


# ============================================================
# 家庭策略
# ============================================================


@ese.household
def household_strategy(mi: MarketIntelligence, hh, goods: Dict[int, Good], orders):
    """家庭消费：每 tick 拿 20% 现金买东西，70% 买食物、30% 买工具"""
    budget = hh.cash * 0.2
    if budget < 0.5:
        return

    food_budget = budget * 0.7
    if food_budget > 0.5:
        qty = food_budget / 2.0
        if qty > 0.1:
            orders.new(
                seller_id=0,
                buyer_id=hh.id,
                good_id=1,
                quantity=qty,
                price=2.0,
                side=OrderSide.DEMAND,
                description="家庭买食物",
            )

    tool_budget = budget * 0.3
    if tool_budget > 0.5:
        qty = tool_budget / 3.0
        if qty > 0.1:
            orders.new(
                seller_id=0,
                buyer_id=hh.id,
                good_id=2,
                quantity=qty,
                price=3.0,
                side=OrderSide.DEMAND,
                description="家庭买工具",
            )


# ============================================================
# 政府策略
# ============================================================


@ese.government
def government_strategy(mi: MarketIntelligence, gov: Government, goods, orders):
    """税率和失业金在种子数据库中已设定，这里不做额外操作"""
    pass


# ============================================================
# 分配策略（价格优先匹配）
# ============================================================


@ese.allocation
def town_allocation(
    mi: MarketIntelligence,
    supply: List[Order],
    demand: List[Order],
    goods: Dict[int, Good],
    pricing=None,
) -> Tuple[List[Order], List[Order], List[Order]]:
    """价格优先匹配：卖价低者优先，买价高者优先，同商品配对"""
    matched = []
    matched_sids = set()
    matched_dids = set()

    sorted_supply = sorted(
        [(i, o) for i, o in enumerate(supply) if o.quantity > 0],
        key=lambda x: x[1].price,
    )
    sorted_demand = sorted(
        [(i, o) for i, o in enumerate(demand) if o.quantity > 0],
        key=lambda x: -x[1].price,
    )

    for si, s in sorted_supply:
        if si in matched_sids:
            continue
        for di, d in sorted_demand:
            if di in matched_dids:
                continue
            if s.good_id != d.good_id:
                continue
            if s.price > d.price:
                continue

            qty = min(s.quantity, d.quantity)
            price = pricing(s, d, {}) if pricing else (s.price + d.price) / 2.0
            matched_order = Order(
                order_id=f"town_match_{s.good_id}_{s.seller_id}_{d.buyer_id}_{mi.tick}_{len(matched)}",
                seller_id=s.seller_id,
                buyer_id=d.buyer_id,
                good_id=s.good_id,
                quantity=qty,
                price=price,
                side=s.side,
                description=s.description,
            )
            matched.append(matched_order)

            s.quantity -= qty
            d.quantity -= qty
            if s.quantity <= 0:
                matched_sids.add(si)
            if d.quantity <= 0:
                matched_dids.add(di)
            break

    remaining_supply = [o for i, o in enumerate(supply) if i not in matched_sids]
    remaining_demand = [o for i, o in enumerate(demand) if i not in matched_dids]
    return matched, remaining_supply, remaining_demand


# ============================================================
# 定价策略
# ============================================================


@ese.allocation.pricing
def mid_pricing(supply: Order, demand: Order, config: dict) -> float:
    """取买卖双方报价的中间价"""
    return (supply.price + demand.price) / 2.0


# ============================================================
# 运行并输出结果
# ============================================================

snapshots = ese.run(n_ticks=50)
ese.save(snapshots, prefix="town")
