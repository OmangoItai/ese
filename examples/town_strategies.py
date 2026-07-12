# examples/town_strategies.py
from core.entities import Order
from typing import Dict, List, Tuple
from core.entities import Good


# ---- 企业策略 ----
def firm_strategy(obs: Dict, firm, goods: Dict[int, Good]) -> Dict:
    """农场生产食物，工坊生产工具。固定定价，固定产量，按需购买原料。"""
    result = {"new": [], "cancel": [], "update": []}
    tick = obs["tick"]
    food_id = 1
    tool_id = 2

    # ---- 农场 (id=101) ----
    if firm.id == 101:
        # 生产食物：消耗工具，产出食物
        tool_inv = firm.inventory.get(tool_id, 0.0)
        if tool_inv >= 1.0:
            # 消耗1工具，产出5食物
            firm.inventory[tool_id] = tool_inv - 1.0
            firm.inventory[food_id] = firm.inventory.get(food_id, 0.0) + 5.0

        # 挂单卖食物：价格=2.0，数量=max(库存-安全库存,0)
        food_qty = firm.inventory.get(food_id, 0.0)
        if food_qty > 2.0:
            sell_qty = min(food_qty - 2.0, 10.0)  # 每次最多卖10
            result["new"].append(
                Order(
                    order_id=f"f{firm.id}_sell_food_{tick}_{len(result['new'])}",
                    seller_id=firm.id,
                    buyer_id=0,
                    good_id=food_id,
                    quantity=sell_qty,
                    price=2.0,
                    order_type="B2C",
                    creation_tick=tick,
                )
            )
        # 购买工具：当现金>50且工具库存<10
        if firm.cash > 50.0 and firm.inventory.get(tool_id, 0.0) < 10.0:
            result["new"].append(
                Order(
                    order_id=f"f{firm.id}_buy_tool_{tick}_{len(result['new'])}",
                    seller_id=0,
                    buyer_id=firm.id,
                    good_id=tool_id,
                    quantity=2.0,
                    price=3.0,  # 愿意出价3
                    order_type="B2B",
                    creation_tick=tick,
                )
            )

    # ---- 工坊 (id=102) ----
    elif firm.id == 102:
        # 生产工具：消耗食物，产出工具
        food_inv = firm.inventory.get(food_id, 0.0)
        if food_inv >= 2.0:
            firm.inventory[food_id] = food_inv - 2.0
            firm.inventory[tool_id] = firm.inventory.get(tool_id, 0.0) + 3.0

        # 卖工具
        tool_qty = firm.inventory.get(tool_id, 0.0)
        if tool_qty > 2.0:
            sell_qty = min(tool_qty - 2.0, 5.0)
            result["new"].append(
                Order(
                    order_id=f"f{firm.id}_sell_tool_{tick}_{len(result['new'])}",
                    seller_id=firm.id,
                    buyer_id=0,
                    good_id=tool_id,
                    quantity=sell_qty,
                    price=3.0,
                    order_type="B2B",
                    creation_tick=tick,
                )
            )
        # 购买食物
        if firm.cash > 50.0 and firm.inventory.get(food_id, 0.0) < 10.0:
            result["new"].append(
                Order(
                    order_id=f"f{firm.id}_buy_food_{tick}_{len(result['new'])}",
                    seller_id=0,
                    buyer_id=firm.id,
                    good_id=food_id,
                    quantity=3.0,
                    price=2.0,
                    order_type="B2C",
                    creation_tick=tick,
                )
            )

    return result


# ---- 家庭策略 ----
def household_strategy(obs: Dict, hh, goods: Dict[int, Good]) -> Dict:
    """家庭消费：70%收入买食物，30%买工具（若价格可接受）。"""
    result = {"new": [], "cancel": [], "update": []}
    tick = obs["tick"]
    food_id = 1
    tool_id = 2

    # 计算收入：如果有工作，收入是 labor_ask_price（工资已由内核发放，这里只做消费决策）
    # 我们用当前现金的20%作为消费预算（避免花光）
    budget = hh.cash * 0.2
    if budget < 0.5:
        return result  # 没钱不买

    # 买食物：预算70%
    food_budget = budget * 0.7
    if food_budget > 0.5:
        qty = food_budget / 2.0  # 假设食物均价2
        if qty > 0.1:
            result["new"].append(
                Order(
                    order_id=f"h{hh.id}_buy_food_{tick}_{len(result['new'])}",
                    seller_id=0,
                    buyer_id=hh.id,
                    good_id=food_id,
                    quantity=qty,
                    price=2.0,
                    order_type="B2C",
                    creation_tick=tick,
                )
            )

    # 买工具：预算30%
    tool_budget = budget * 0.3
    if tool_budget > 0.5:
        qty = tool_budget / 3.0
        if qty > 0.1:
            result["new"].append(
                Order(
                    order_id=f"h{hh.id}_buy_tool_{tick}_{len(result['new'])}",
                    seller_id=0,
                    buyer_id=hh.id,
                    good_id=tool_id,
                    quantity=qty,
                    price=3.0,
                    order_type="B2C",
                    creation_tick=tick,
                )
            )

    return result


# ---- 政府策略（简单征税并发放少量失业金） ----
def government_strategy(obs: Dict, gov, goods: Dict[int, Good]) -> Dict:
    # 本策略不主动创建订单，仅调整税率和失业金（已在种子中设定）
    return {"new": [], "cancel": [], "update": []}


# ---- 分配策略（价格优先，同价则先到先得） ----
def town_allocation(
    obs: Dict,
    supply_pool: List[Order],
    demand_pool: List[Order],
    goods: Dict[int, Good],
) -> Tuple[List[Order], List[Order], List[Order]]:
    matched = []
    matched_sids = set()
    matched_dids = set()

    # 按价格排序：供应从小到大，需求从大到小（需求价高者优先）
    sorted_supply = sorted(
        [(i, o) for i, o in enumerate(supply_pool) if o.quantity > 0],
        key=lambda x: x[1].price,
    )
    sorted_demand = sorted(
        [(i, o) for i, o in enumerate(demand_pool) if o.quantity > 0],
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
                continue  # 供应价高于需求价，无法成交

            qty = min(s.quantity, d.quantity)
            price = (s.price + d.price) / 2.0  # 折中价（或可改为s.price）
            matched_order = Order(
                order_id=f"town_match_{s.good_id}_{s.seller_id}_{d.buyer_id}_{obs['tick']}_{len(matched)}",
                seller_id=s.seller_id,
                buyer_id=d.buyer_id,
                good_id=s.good_id,
                quantity=qty,
                price=price,
                order_type=s.order_type,
                creation_tick=obs["tick"],
            )
            matched.append(matched_order)

            s.quantity -= qty
            d.quantity -= qty
            if s.quantity <= 0:
                matched_sids.add(si)
            if d.quantity <= 0:
                matched_dids.add(di)
            break

    remaining_supply = [o for i, o in enumerate(supply_pool) if i not in matched_sids]
    remaining_demand = [o for i, o in enumerate(demand_pool) if i not in matched_dids]
    return matched, remaining_supply, remaining_demand
