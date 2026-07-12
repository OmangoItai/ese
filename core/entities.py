from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import deque
from enum import StrEnum


class OrderSide(StrEnum):
    SUPPLY = "supply"
    DEMAND = "demand"


@dataclass
class Good:
    good_id: int
    name: str
    good_type: str = "consumer"  # food | labor | capital | consumer | raw_material
    delivery_lag: int = 1  # >= 1，加载时校验


@dataclass
class Order:
    order_id: str
    seller_id: int
    buyer_id: int
    good_id: int
    quantity: float
    price: float  # 单价
    side: OrderSide = OrderSide.SUPPLY  # 决定进供应池还是需求池
    description: str = ""  # 自由文本标签
    creation_tick: int = field(default=0, init=False)
    settlement_tick: int = 0  # 0=未分配哨兵；分配后=tick+delivery_lag
    status: str = "OPEN"  # OPEN→ALLOCATED→FULFILLED|DEFAULTED|CANCELLED|EXPIRED


@dataclass
class Firm:
    id: int
    cash: float
    inventory: Dict[int, float] = field(default_factory=dict)  # good_id -> quantity
    capacity: float = 0.0
    collateral: float = 0.0  # 自有资产净值（冻结金在 WorldState.collateral_pool）
    is_active: bool = True
    employees: List[int] = field(default_factory=list)
    outstanding_order_ids: Set[str] = field(default_factory=set)
    strategy_label: str = "default"
    _fulfillment_log: deque[Tuple[int, int, int]] = field(
        default_factory=lambda: deque(maxlen=30)
    )  # (fulfilled, defaulted, tick) 按 Tick 聚合，maxlen=30 常数内存

    def outstanding_orders(self, order_book: dict) -> list:
        return [
            order_book[oid]
            for oid in self.outstanding_order_ids
            if order_book.get(oid) and order_book[oid].status in ("OPEN", "ALLOCATED")
        ]


@dataclass
class Household:
    id: int
    cash: float
    inventory: Dict[int, float] = field(default_factory=dict)
    labor_ask_price: float = 0.0  # 期望工资
    is_employed: bool = False
    employer_firm_id: Optional[int] = None
    unemployment_ticks: int = 0
    outstanding_order_ids: Set[str] = field(default_factory=set)
    strategy_label: str = "default"
    _fulfillment_log: deque[Tuple[int, int, int]] = field(
        default_factory=lambda: deque(maxlen=30)
    )  # (fulfilled, defaulted, tick) 按 Tick 聚合，maxlen=30 常数内存

    def outstanding_orders(self, order_book: dict) -> list:
        return [
            order_book[oid]
            for oid in self.outstanding_order_ids
            if order_book.get(oid) and order_book[oid].status in ("OPEN", "ALLOCATED")
        ]


@dataclass
class Government:
    id: int
    cash: float
    tax_rate: float = 0.0
    money_supply: float = 0.0  # 预留，当前版本不启用
    unemployment_benefit: float = 0.0
    outstanding_order_ids: Set[str] = field(default_factory=set)
    strategy_label: str = "default"
    _fulfillment_log: deque[Tuple[int, int, int]] = field(
        default_factory=lambda: deque(maxlen=30)
    )  # (fulfilled, defaulted, tick) 按 Tick 聚合，maxlen=30 常数内存（未来功能预留）

    def outstanding_orders(self, order_book: dict) -> list:
        return [
            order_book[oid]
            for oid in self.outstanding_order_ids
            if order_book.get(oid) and order_book[oid].status in ("OPEN", "ALLOCATED")
        ]


@dataclass
class WorldState:
    tick: int
    firms: Dict[int, Firm] = field(default_factory=dict)
    households: Dict[int, Household] = field(default_factory=dict)
    governments: Dict[int, Government] = field(default_factory=dict)
    goods: Dict[int, Good] = field(default_factory=dict)
    supply_pool: List[Order] = field(default_factory=list)  # 卖方挂单，持久待分配
    demand_pool: List[Order] = field(default_factory=list)  # 买方挂单，持久待分配
    pending_orders: List[Order] = field(default_factory=list)  # 已分配、待交割
    all_orders: Dict[str, Order] = field(
        default_factory=dict
    )  # order_id → Order，全局索引
    collateral_pool: Dict[str, float] = field(
        default_factory=dict
    )  # "{order_id}_seller"/"{order_id}_buyer" → 冻结金额
