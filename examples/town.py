import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Tuple, List

from ese import (
    Engine,
    Good,
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
# 叶子函数：无装饰器的普通 Python 函数，由 apply() 直接传入实体实例
# ============================================================


def farm_decide(firm, orders, mi, market):
    """农场：消耗工具 → 产出食物 → 卖食物、买工具"""
    tool_inv = firm.inventory[2]
    if tool_inv >= 1.0:
        firm.inventory[2] = tool_inv - 1.0
        firm.inventory[1] = firm.inventory[1] + 5.0

    food_qty = firm.inventory[1]
    if food_qty > 2.0:
        sell_qty = min(food_qty - 2.0, 10.0)
        orders.new(
            good_id=1,
            quantity=sell_qty,
            price=2.0,
            side=OrderSide.SUPPLY,
            description="农场卖食物",
        )

    if firm.cash > 50.0 and firm.inventory[2] < 10.0:
        orders.new(
            good_id=2,
            quantity=2.0,
            price=3.0,
            side=OrderSide.DEMAND,
            description="农场买工具",
        )


def workshop_decide(firm, orders, mi, market):
    """工坊：消耗食物 → 产出工具 → 卖工具、买食物"""
    food_inv = firm.inventory[1]
    if food_inv >= 2.0:
        firm.inventory[1] = food_inv - 2.0
        firm.inventory[2] = firm.inventory[2] + 3.0

    tool_qty = firm.inventory[2]
    if tool_qty > 2.0:
        sell_qty = min(tool_qty - 2.0, 5.0)
        orders.new(
            good_id=2,
            quantity=sell_qty,
            price=3.0,
            side=OrderSide.SUPPLY,
            description="工坊卖工具",
        )

    if firm.cash > 50.0 and firm.inventory[1] < 10.0:
        orders.new(
            good_id=1,
            quantity=3.0,
            price=2.0,
            side=OrderSide.DEMAND,
            description="工坊买食物",
        )


def household_spend(hh, orders, mi, market):
    """家庭消费：每 tick 拿 20% 现金买东西，70% 买食物、30% 买工具"""
    budget = hh.cash * 0.2
    if budget < 0.5:
        return

    food_budget = budget * 0.7
    if food_budget > 0.5:
        qty = food_budget / 2.0
        if qty > 0.1:
            orders.new(
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
                good_id=2,
                quantity=qty,
                price=3.0,
                side=OrderSide.DEMAND,
                description="家庭买工具",
            )


# ============================================================
# 宏函数：每 slot 只调一次，内部用 apply() 分发到实体
# ============================================================


@ese.firm
def firm_macro(mi: MarketIntelligence, goods: Dict[int, Good], market):
    """企业宏函数：按 labels 分发到叶子函数"""
    ese.firm.apply("farm", farm_decide)
    ese.firm.apply("workshop", workshop_decide)


@ese.household
def household_macro(mi: MarketIntelligence, goods: Dict[int, Good], market):
    """家庭宏函数：所有家庭走同一个消费逻辑"""
    ese.household.apply("default", household_spend)


@ese.government
def government_macro(mi: MarketIntelligence, goods: Dict[int, Good], market):
    """政府宏函数：税率和失业金在种子数据库中已设定，这里不做额外操作"""
    pass


# ============================================================
# 分配策略（不变）
# ============================================================


@ese.allocation
def town_allocation(
    mi: MarketIntelligence,
    supply: List[Order],
    demand: List[Order],
    goods: Dict[int, Good],
    market,
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
            price = pricing(s, d, {}, market) if pricing else (s.price + d.price) / 2.0
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
# 定价策略（不变）
# ============================================================


@ese.allocation.pricing
def mid_pricing(supply: Order, demand: Order, config: dict, market) -> float:
    """取买卖双方报价的中间价"""
    return (supply.price + demand.price) / 2.0


# ============================================================
# 运行并输出结果
# ============================================================

snapshots = ese.run(n_ticks=50)
ese.save(snapshots, prefix="town")
