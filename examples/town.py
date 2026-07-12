import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Tuple, List

from ese import Engine
from core.entities import Order, Firm, Good, Government, Household, OrderSide
from core.market_intelligence import MarketIntelligence
import pandas as pd
import matplotlib.pyplot as plt

# ============================================================
# 初始化引擎
# ============================================================

ese = Engine("config/default.yaml", "town_world.db")

# ============================================================
# 企业策略
# ============================================================


@ese.firm
def firm_orchestrator(
    mi: MarketIntelligence, firm: Firm, goods: Dict[int, Good], orders
):
    """调度器：按 strategy_label 分发到标签策略"""
    return ese.firm.use(firm.strategy_label, mi, firm, goods, orders)


@ese.firm.label("farm")
def farm_strategy(mi: MarketIntelligence, firm: Firm, goods: Dict[int, Good], orders):
    """农场：消耗工具 → 产出食物 → 卖食物、买工具"""
    result = {"new": [], "cancel": [], "update": []}
    tick = mi.tick

    # 生产：1 工具 → 5 食物
    tool_inv = firm.inventory.get(2, 0.0)
    if tool_inv >= 1.0:
        firm.inventory[2] = tool_inv - 1.0
        firm.inventory[1] = firm.inventory.get(1, 0.0) + 5.0

    # 挂单卖食物（留 2 做安全库存）
    food_qty = firm.inventory.get(1, 0.0)
    if food_qty > 2.0:
        sell_qty = min(food_qty - 2.0, 10.0)
        result["new"].append(
            Order(
                order_id=f"f{firm.id}_sell_food_{tick}_{len(result['new'])}",
                seller_id=firm.id,
                buyer_id=0,
                good_id=1,
                quantity=sell_qty,
                price=2.0,
                side=OrderSide.SUPPLY,
                description="农场卖食物",
                creation_tick=tick,
            )
        )

    # 工具库存不足时采购
    if firm.cash > 50.0 and firm.inventory.get(2, 0.0) < 10.0:
        result["new"].append(
            Order(
                order_id=f"f{firm.id}_buy_tool_{tick}_{len(result['new'])}",
                seller_id=0,
                buyer_id=firm.id,
                good_id=2,
                quantity=2.0,
                price=3.0,
                side=OrderSide.DEMAND,
                description="农场买工具",
                creation_tick=tick,
            )
        )

    return result


@ese.firm.label("workshop")
def workshop_strategy(
    mi: MarketIntelligence, firm: Firm, goods: Dict[int, Good], orders
):
    """工坊：消耗食物 → 产出工具 → 卖工具、买食物"""
    result = {"new": [], "cancel": [], "update": []}
    tick = mi.tick

    # 生产：2 食物 → 3 工具
    food_inv = firm.inventory.get(1, 0.0)
    if food_inv >= 2.0:
        firm.inventory[1] = food_inv - 2.0
        firm.inventory[2] = firm.inventory.get(2, 0.0) + 3.0

    # 挂单卖工具
    tool_qty = firm.inventory.get(2, 0.0)
    if tool_qty > 2.0:
        sell_qty = min(tool_qty - 2.0, 5.0)
        result["new"].append(
            Order(
                order_id=f"f{firm.id}_sell_tool_{tick}_{len(result['new'])}",
                seller_id=firm.id,
                buyer_id=0,
                good_id=2,
                quantity=sell_qty,
                price=3.0,
                side=OrderSide.SUPPLY,
                description="工坊卖工具",
                creation_tick=tick,
            )
        )

    # 食物库存不足时采购
    if firm.cash > 50.0 and firm.inventory.get(1, 0.0) < 10.0:
        result["new"].append(
            Order(
                order_id=f"f{firm.id}_buy_food_{tick}_{len(result['new'])}",
                seller_id=0,
                buyer_id=firm.id,
                good_id=1,
                quantity=3.0,
                price=2.0,
                side=OrderSide.DEMAND,
                description="工坊买食物",
                creation_tick=tick,
            )
        )

    return result


# ============================================================
# 家庭策略
# ============================================================


@ese.household
def household_strategy(
    mi: MarketIntelligence, hh: Household, goods: Dict[int, Good], orders
):
    """家庭消费：每 tick 拿 20% 现金买东西，70% 买食物、30% 买工具"""
    result = {"new": [], "cancel": [], "update": []}
    tick = mi.tick

    budget = hh.cash * 0.2
    if budget < 0.5:
        return result

    food_budget = budget * 0.7
    if food_budget > 0.5:
        qty = food_budget / 2.0
        if qty > 0.1:
            result["new"].append(
                Order(
                    order_id=f"h{hh.id}_buy_food_{tick}_{len(result['new'])}",
                    seller_id=0,
                    buyer_id=hh.id,
                    good_id=1,
                    quantity=qty,
                    price=2.0,
                    side=OrderSide.DEMAND,
                    description="家庭买食物",
                    creation_tick=tick,
                )
            )

    tool_budget = budget * 0.3
    if tool_budget > 0.5:
        qty = tool_budget / 3.0
        if qty > 0.1:
            result["new"].append(
                Order(
                    order_id=f"h{hh.id}_buy_tool_{tick}_{len(result['new'])}",
                    seller_id=0,
                    buyer_id=hh.id,
                    good_id=2,
                    quantity=qty,
                    price=3.0,
                    side=OrderSide.DEMAND,
                    description="家庭买工具",
                    creation_tick=tick,
                )
            )

    return result


# ============================================================
# 政府策略
# ============================================================


@ese.government
def government_strategy(
    mi: MarketIntelligence, gov: Government, goods: Dict[int, Good], orders
):
    """税率和失业金在种子数据库中已设定，这里不做额外操作"""
    return {"new": [], "cancel": [], "update": []}


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
                creation_tick=mi.tick,
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

df = pd.DataFrame(snapshots)
df.to_csv("town_results.csv", index=False)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
axes[0, 0].plot(df["tick"], df["gini"])
axes[0, 0].set_title("Gini")
axes[0, 1].plot(df["tick"], df["unemployment"], color="r")
axes[0, 1].set_title("Unemployment")
axes[1, 0].plot(df["tick"], df["engel"], color="g")
axes[1, 0].set_title("Engel")
axes[1, 1].plot(df["tick"], df["active_firms"], color="m")
axes[1, 1].set_title("Active Firms")
plt.tight_layout()
plt.savefig("town_results.png")
print("Done. Saved town_results.csv and town_results.png")
