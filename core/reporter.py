from typing import Dict
from core.entities import Household, Good, WorldState


class Reporter:
    @staticmethod
    def calc_gini(
        households: Dict[int, Household], goods: Dict[int, Good] = None
    ) -> float:
        wealths = []
        for hh in households.values():
            w = hh.cash
            if goods:
                for good_id, qty in hh.inventory.items():
                    g = goods.get(good_id)
                    if g:
                        w += qty * g.delivery_lag
            wealths.append(w)

        if not wealths or sum(wealths) == 0:
            return 0.0

        sorted_w = sorted(wealths)
        n = len(sorted_w)
        sum_w = sum(sorted_w)

        weighted_sum = sum((i + 1) * w for i, w in enumerate(sorted_w))
        gini = (2 * weighted_sum - (n + 1) * sum_w) / (n * sum_w)
        return gini

    @staticmethod
    def calc_engel(
        households: Dict[int, Household],
        goods: Dict[int, Good],
        ledger: "Ledger",
        n_ticks: int = 30,
    ) -> float:
        if not ledger.records:
            return 0.0

        household_ids = set(households.keys())
        food_good_ids = {gid for gid, g in goods.items() if g.good_type == "food"}

        current_tick = max(r.tick for r in ledger.records)
        min_tick = max(0, current_tick - n_ticks + 1)

        recent = [
            r
            for r in ledger.records
            if r.status == "FULFILLED"
            and min_tick <= r.tick <= current_tick
            and r.buyer_id in household_ids
        ]

        if not recent:
            return 0.0

        food_expenditure = sum(
            r.price * r.quantity for r in recent if r.good_id in food_good_ids
        )
        total_expenditure = sum(r.price * r.quantity for r in recent)

        if total_expenditure == 0:
            return 0.0
        return food_expenditure / total_expenditure

    @staticmethod
    def calc_unemployment(households: Dict[int, Household]) -> float:
        if not households:
            return 0.0
        unemployed = sum(1 for hh in households.values() if not hh.is_employed)
        return unemployed / len(households)

    @staticmethod
    def snapshot(state: WorldState, ledger: "Ledger") -> Dict:
        return {
            "tick": state.tick,
            "gini": Reporter.calc_gini(state.households, state.goods),
            "engel": Reporter.calc_engel(state.households, state.goods, ledger),
            "unemployment": Reporter.calc_unemployment(state.households),
            "active_firms": sum(1 for f in state.firms.values() if f.is_active),
            "active_households": len(state.households),
            "total_firms": len(state.firms),
            "total_households": len(state.households),
        }
