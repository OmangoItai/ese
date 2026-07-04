from typing import Dict, List, Tuple

from core.entities import Good, Order


def firm_strategy(obs: Dict, firm: "Firm", goods: Dict[int, Good]) -> Dict:
    result = {"new": [], "cancel": [], "update": []}
    tick = obs["tick"]

    food_ids = [g.good_id for g in goods.values() if g.good_type == "food"]
    raw_ids = [g.good_id for g in goods.values() if g.good_type == "raw_material"]

    for good_id in food_ids:
        qty = firm.inventory.get(good_id, 0.0)
        if qty > 0:
            sell_qty = min(qty, 5.0)
            result["new"].append(
                Order(
                    order_id=f"f{firm.id}_sell_{good_id}_{tick}_{len(result['new'])}",
                    seller_id=firm.id,
                    buyer_id=0,
                    good_id=good_id,
                    quantity=sell_qty,
                    price=2.0,
                    order_type="B2C",
                    creation_tick=tick,
                )
            )

    for good_id in raw_ids:
        if firm.cash > 10.0:
            result["new"].append(
                Order(
                    order_id=f"f{firm.id}_buy_{good_id}_{tick}_{len(result['new'])}",
                    seller_id=0,
                    buyer_id=firm.id,
                    good_id=good_id,
                    quantity=5.0,
                    price=1.0,
                    order_type="B2B",
                    creation_tick=tick,
                )
            )

    return result


def household_strategy(obs: Dict, hh: "Household", goods: Dict[int, Good]) -> Dict:
    result = {"new": [], "cancel": [], "update": []}
    tick = obs["tick"]

    food_ids = [g.good_id for g in goods.values() if g.good_type == "food"]

    for good_id in food_ids:
        current = hh.inventory.get(good_id, 0.0)
        if hh.cash > 5.0 and current < 50.0:
            result["new"].append(
                Order(
                    order_id=f"h{hh.id}_buy_{good_id}_{tick}_{len(result['new'])}",
                    seller_id=0,
                    buyer_id=hh.id,
                    good_id=good_id,
                    quantity=2.0,
                    price=2.0,
                    order_type="B2C",
                    creation_tick=tick,
                )
            )

    return result


def government_strategy(obs: Dict, gov: "Government", goods: Dict[int, Good]) -> Dict:
    return {"new": [], "cancel": [], "update": []}


def demo_allocation(
    obs: Dict,
    supply_pool: List[Order],
    demand_pool: List[Order],
    goods: Dict[int, Good],
) -> Tuple[List[Order], List[Order], List[Order]]:
    matched: List[Order] = []
    matched_sids: set = set()
    matched_dids: set = set()

    for si, supply in enumerate(supply_pool):
        if si in matched_sids:
            continue
        for di, demand in enumerate(demand_pool):
            if di in matched_dids:
                continue
            if supply.good_id != demand.good_id:
                continue
            if supply.price > demand.price:
                continue

            match_qty = min(supply.quantity, demand.quantity)
            match_price = supply.price

            matched_order = Order(
                order_id=(
                    f"match_{supply.good_id}_{supply.seller_id}_"
                    f"{demand.buyer_id}_{obs['tick']}_{len(matched)}"
                ),
                seller_id=supply.seller_id,
                buyer_id=demand.buyer_id,
                good_id=supply.good_id,
                quantity=match_qty,
                price=match_price,
                order_type=supply.order_type,
                creation_tick=obs["tick"],
            )
            matched.append(matched_order)

            supply.quantity -= match_qty
            demand.quantity -= match_qty

            if supply.quantity <= 0:
                matched_sids.add(si)
            if demand.quantity <= 0:
                matched_dids.add(di)
            break

    remaining_supply = [o for i, o in enumerate(supply_pool) if i not in matched_sids]
    remaining_demand = [o for i, o in enumerate(demand_pool) if i not in matched_dids]

    return matched, remaining_supply, remaining_demand
