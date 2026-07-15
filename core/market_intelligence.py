from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from core.entities import Order, WorldState
from core.ledger import TradeHistory
from core.noise import InformationFriction
from core.reporter import Reporter


@dataclass
class MarketIntelligence:
    tick: int
    gini: float
    unemployment_rate: float
    engel: float
    sector_avg_price: Dict[int, float] = field(default_factory=dict)
    sector_total_supply: Dict[int, float] = field(default_factory=dict)
    sector_total_demand: Dict[int, float] = field(default_factory=dict)
    tax_rate: float = 0.0
    unemployment_benefit: float = 0.0
    active_firms: int = 0


class MarketIntelligenceBuilder:
    def __init__(self, noise: InformationFriction, reporter: Reporter, config: Dict):
        self.noise = noise
        self.reporter = reporter
        self.config = config

    def build(self, state: WorldState, ledger: TradeHistory) -> MarketIntelligence:
        raw = self._collect_raw(state, ledger)
        noised = self._apply_noise(raw)
        return MarketIntelligence(**noised)

    def _collect_raw(self, state: WorldState, ledger: TradeHistory) -> dict:
        return {
            "tick": state.tick,
            "gini": self.reporter.calc_gini(state.households, state.goods),
            "unemployment_rate": self.reporter.calc_unemployment(state.households),
            "engel": self.reporter.calc_engel(state.households, state.goods, ledger),
            "sector_avg_price": self._aggregate_pool(state.market.supply, agg="avg"),
            "sector_total_supply": self._aggregate_pool(state.market.supply, agg="sum"),
            "sector_total_demand": self._aggregate_pool(state.market.demand, agg="sum"),
            "tax_rate": self._get_gov_attr(state, "tax_rate"),
            "unemployment_benefit": self._get_gov_attr(state, "unemployment_benefit"),
            "active_firms": sum(1 for f in state.firms.values() if f.is_active),
        }

    def _apply_noise(self, data: dict) -> dict:
        noise_type = self.config.get("noise_type", "none")
        noise_params = self.config.get("noise_params", {})

        for key in ["sector_avg_price", "sector_total_supply", "sector_total_demand"]:
            if key in data and isinstance(data[key], dict):
                data[key] = {
                    k: self.noise.apply_noise(v, noise_type, noise_params)
                    for k, v in data[key].items()
                }

        for key in ["gini", "unemployment_rate", "engel"]:
            if key in data:
                data[key] = self.noise.apply_noise(data[key], noise_type, noise_params)

        return data

    @staticmethod
    def _aggregate_pool(pool: List[Order], agg: str = "sum") -> Dict[int, float]:
        result = {}
        if not pool:
            return result
        by_good = defaultdict(list)
        for order in pool:
            if order.quantity > 0:
                by_good[order.good_id].append(order)
        for gid, orders in by_good.items():
            if agg == "sum":
                result[gid] = sum(o.quantity for o in orders)
            elif agg == "avg":
                total_qty = sum(o.quantity for o in orders)
                if total_qty > 0:
                    weighted = sum(o.price * o.quantity for o in orders)
                    result[gid] = weighted / total_qty
                else:
                    result[gid] = 0.0
        return result

    @staticmethod
    def _get_gov_attr(state: WorldState, attr: str) -> float:
        for gov in state.governments.values():
            return float(getattr(gov, attr, 0.0))
        return 0.0
