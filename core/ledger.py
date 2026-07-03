from dataclasses import dataclass, field
from typing import Dict, List
from core.entities import Order


@dataclass
class TradeRecord:
    tick: int
    order_id: str
    seller_id: int
    buyer_id: int
    good_id: int
    quantity: float
    price: float
    status: str


class Ledger:
    def __init__(self):
        self.records: List[TradeRecord] = []

    def record_trade(self, order: Order) -> None:
        tr = TradeRecord(
            tick=order.creation_tick,
            order_id=order.order_id,
            seller_id=order.seller_id,
            buyer_id=order.buyer_id,
            good_id=order.good_id,
            quantity=order.quantity,
            price=order.price,
            status=order.status,
        )
        self.records.append(tr)

    def get_trades_by_agent(self, agent_id: int, n: int = 30) -> List[TradeRecord]:
        matched = [
            r for r in self.records if r.seller_id == agent_id or r.buyer_id == agent_id
        ]
        return matched[-n:] if len(matched) > n else matched

    def get_avg_price_by_good(self, good_id: int, n: int = 30) -> float:
        fulfilled = [
            r for r in self.records if r.good_id == good_id and r.status == "FULFILLED"
        ]
        recent = fulfilled[-n:] if len(fulfilled) > n else fulfilled
        if not recent:
            return 0.0
        return sum(r.price for r in recent) / len(recent)

    def get_all_recent_prices(self, n: int = 30) -> Dict[int, List[float]]:
        fulfilled = [r for r in self.records if r.status == "FULFILLED"]
        recent = fulfilled[-n:] if len(fulfilled) > n else fulfilled
        result: Dict[int, List[float]] = {}
        for r in recent:
            if r.good_id not in result:
                result[r.good_id] = []
            result[r.good_id].append(r.price)
        return result
