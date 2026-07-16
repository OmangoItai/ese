ESE (Economic Simulation Engine)

# 1. 设计约束

## 1.1 四大设计禁令
- 1 — 禁止上帝矩阵：所有算法只能基于历史账本（TradeHistory）进行统计推断，不得直接读取全局精确的投入产出表（A）。
- 2 — 时间具象化：所有生产订单必须有"承诺-交付"的延迟队列；到期未交付则触发违约。
- 3 — 策略可插拔：企业/家庭/政府/分配策略由用户通过 Python 装饰器注册，内核不内置任何策略逻辑。
- 4 — 匹配即制度：ClearingHouse 不得包含任何分配算法。匹配逻辑是用户策略的一部分。结算器只负责不可变物理规则：订单验证、抵押品冻结/释放/没收、破产清算、交易记账。

# 2. 文件与目录结构

```
ese/
├── requirements.txt          # numpy, pandas, pyyaml, matplotlib
├── config/
│   ├── default.yaml          # 运行参数：seed, base_collateral_ratio, noise_type, noise_params, order_expire_ticks, fulfillment_window_ticks, n_ticks
│   └── seed_world.db
├── core/                     # 不可变内核
│   ├── entities.py           # Good, OrderSide, Order, Firm, Household, Government, AgentOrders, WorldState, MarketData
│   ├── clearing_house.py     # 结算器
│   ├── noise.py              # InformationFriction
│   ├── reporter.py           # 指标计算器
│   ├── _registry.py          # 内部策略注册表
│   ├── simulator.py          # 主循环（9 步 tick）
│   ├── engine.py             # 用户入口 Engine（装饰器 + run/save）
│   ├── ledger.py             # TradeHistory + TradeRecord
│   ├── market_intelligence.py# MarketIntelligence + Builder
│   └── data_layer.py         # WorldLoader, WorldBuilder, Sequence, OrderFactory
├── examples/
│   ├── generate_town.py      # WorldBuilder 生成 world 数据库
│   └── town.py
```

# 3. 核心模块

## 核心数据对象

- **MarketIntelligence (MI)** — 宏观情报（引擎构建，策略只读）。Tick 末尾从 WorldState 采集数据，经 Reporter 计算宏观指标，再经 InformationFriction 加噪生成 MI。策略只拿到 gini、失业率、恩格尔、行业均价等统计局级别的汇总数据——不暴露任何个体级财务。自身状态通过 `apply()` 传入的实体实例直接读取，不走 MI。

- **TradeHistory** — 公开交易账本（ClearingHouse 写入，策略/Reporter 查询）。每笔订单状态变更时 ClearingHouse 自动追加 TradeRecord。记录不可篡改的成交事实（谁向谁以什么价格买了多少、履约还是违约）。主体可查询历史成交记录和均价。

- **market (MarketData)** — 统合三个市场数据入口：`market.supply`（卖方挂单池）、`market.demand`（买方挂单池）、`market.history`（TradeHistory）。挂载在 WorldState 上，一个入口查完所有市场数据。

- **pending_orders** — 待交割队列。已配对、等待 settlement_tick 到期的订单。ClearingHouse 到期结算。

- **collateral_pool** — 双边保证金。`"{order_id}_seller"` / `"{order_id}_buyer"` → 冻结金额。仅 ClearingHouse 操作。

- **Order** — 交易订单。状态机：OPEN→ALLOCATED→FULFILLED/DEFAULTED/CANCELLED/EXPIRED。`side: OrderSide`（SUPPLY/DEMAND）决定入哪侧池。

- **Firm / Household / Government** — 经济主体。seed_world.db 定义初始值。均持有 `labels: List[str]` 用于 `apply()` 标签分发。cash / inventory / is_active 仅内核可改。

- **Good** — 商品定义（实验人员配置）。公开知识，策略直接查，不加噪。good_type 决定结算行为，delivery_lag 决定交割延迟。

- **WorldState** — 全局状态容器。承载以上全部对象和池，自身不做决策。

## 3.1 数据实体层 (core/entities.py)

```py
class OrderSide(StrEnum):
    SUPPLY = "supply"
    DEMAND = "demand"

@dataclass
class Good:
    good_id: int
    name: str
    good_type: str = "consumer"         # food | labor | capital | consumer | raw_material
    delivery_lag: int = 1               # >= 1，世界加载时校验

@dataclass
class Order:
    order_id: str
    seller_id: int
    buyer_id: int
    good_id: int
    quantity: float
    price: float                        # 单价
    side: OrderSide = OrderSide.SUPPLY  # 决定入 supply 还是 demand 池
    description: str = ""               # 自由文本标签（如 "foreclosure"）
    creation_tick: int = field(default=0, init=False)
    settlement_tick: int = 0            # 0=未分配哨兵；分配后=tick+delivery_lag
    status: str = "OPEN"                # OPEN→ALLOCATED→FULFILLED|DEFAULTED|CANCELLED|EXPIRED
```

劳动力交易：Good.good_type="labor"，使用标准 Order，结算时特殊处理（建立雇佣关系、内核自动划拨工资，见 §3.2 settle_order）。

```py
@dataclass
class Firm:
    id: int
    cash: float
    inventory: Dict[int, float] = field(
        default_factory=lambda: defaultdict(float)
    )                                   # good_id -> quantity，缺货自动返回 0.0
    capacity: float = 0.0
    collateral: float = 0.0             # 自有资产净值（冻结金在 WorldState.collateral_pool）
    is_active: bool = True
    employees: List[int] = field(default_factory=list)
    outstanding_order_ids: Set[str] = field(default_factory=set)  # OPEN/ALLOCATED 状态订单
    labels: List[str] = field(default_factory=lambda: ["default"])
    _fulfillment_log: deque[Tuple[int, int, int]] = field(
        default_factory=lambda: deque(maxlen=30)
    )                                   # (fulfilled, defaulted, tick)

    def outstanding_orders(self, order_book: dict) -> list:
        """返回本实体当前 OPEN/ALLOCATED 状态的 Order 列表。"""

@dataclass
class Household:
    id: int
    cash: float
    inventory: Dict[int, float] = field(default_factory=lambda: defaultdict(float))
    reservation_wage: float = 0.0        # 期望工资
    is_employed: bool = False
    employer_firm_id: Optional[int] = None
    unemployment_ticks: int = 0
    outstanding_order_ids: Set[str] = field(default_factory=set)
    labels: List[str] = field(default_factory=lambda: ["default"])
    _fulfillment_log: deque[Tuple[int, int, int]] = field(
        default_factory=lambda: deque(maxlen=30)
    )

    def outstanding_orders(self, order_book: dict) -> list:
        ...

@dataclass
class Government:
    id: int
    cash: float
    tax_rate: float = 0.0
    money_supply: float = 0.0           # 预留，当前版本不启用
    unemployment_benefit: float = 0.0
    outstanding_order_ids: Set[str] = field(default_factory=set)
    labels: List[str] = field(default_factory=lambda: ["default"])
    _fulfillment_log: deque[Tuple[int, int, int]] = field(
        default_factory=lambda: deque(maxlen=30)
    )

    def outstanding_orders(self, order_book: dict) -> list:
        ...

class AgentOrders:
    """策略中的 orders 参数。可遍历（读取已有订单）且可操作（new/cancel/update）。
    方法调用只记录意图，引擎策略执行后通过 _consume() 统一处理。
    """
    def __init__(self, orders: list, order_factory=None): ...

    def __iter__(self): ...              # 遍历已有订单
    def __getitem__(self, i): ...
    def __len__(self): ...

    def new(self, *, good_id,
            quantity, price, side=None, description="") -> None: ...
    def cancel(self, order_id: str) -> None: ...
    def update(self, order_id: str, *,
               good_id, quantity, price, side=None, description="") -> None: ...

    def _consume(self) -> dict:
        """引擎内部调用。取出并清空积攒的意图，返回 {new, cancel, update}。"""

@dataclass
class MarketData:
    supply: List[Order] = field(default_factory=list)
    demand: List[Order] = field(default_factory=list)
    history: "TradeHistory" = field(default_factory=_get_trade_history)

@dataclass
class WorldState:
    tick: int
    firms: Dict[int, Firm] = field(default_factory=dict)
    households: Dict[int, Household] = field(default_factory=dict)
    governments: Dict[int, Government] = field(default_factory=dict)
    goods: Dict[int, Good] = field(default_factory=dict)
    market: "MarketData" = field(default=None)     # __post_init__ 中初始化
    pending_orders: List[Order] = field(default_factory=list)  # 已分配、待交割
    all_orders: Dict[str, Order] = field(default_factory=dict) # order_id→Order 全局索引
    collateral_pool: Dict[str, float] = field(default_factory=dict)  # "{order_id}_seller"/"{order_id}_buyer" → 冻结金额

    def __post_init__(self):
        if self.market is None:
            self.market = MarketData()
```

实现注意事项：
- `inventory` 使用 `defaultdict(float)` 作为默认工厂，缺货键自动返回 `0.0`，无需 `.get(good_id, 0)`。
- `_fulfillment_log: deque(maxlen=30)` 按 Tick 聚合存储 `(fulfilled, defaulted, tick)` 元组。同 Tick 内多次交割合并为同一条目（pop/modify/append）。履约率 = Σfulfilled / Σ(fulfilled + defaulted)。deque 为空 → 1.0。
- `Firm.outstanding_order_ids` / `Household.outstanding_order_ids` / `Government.outstanding_order_ids` 由 ClearingHouse 维护：freeze_collateral 时 `add(order_id)`（双方各自加入），release_collateral/forfeit_collateral 时 `discard(order_id)`（双方各自移除）。
- `outstanding_orders(order_book)` 返回当前 status 为 OPEN 或 ALLOCATED 的订单实例列表，供 `apply()` 构建 AgentOrders。

## 3.2 结算器 (core/clearing_house.py)

结算器是不可变内核，不实现任何分配算法。

```py
class ClearingHouse:

    def __init__(self, ledger: TradeHistory, base_collateral_ratio: float = 0.1, fulfillment_window_ticks: int = 30):
        self.ledger = ledger
        self.base_collateral_ratio = base_collateral_ratio
        self.fulfillment_window_ticks = fulfillment_window_ticks
        self.price_history: Dict[int, deque] = {}  # {good_id: deque((tick, price), maxlen=30)}

    # ———— 实体查询 ————
    @staticmethod
    def _get_entity(state, entity_id) -> Union[Firm, Household, Government, None]:
        """按 id 在 firms→households→governments 中依次查找。"""

    # ———— 履约率 ————
    @staticmethod
    def _fulfillment_rate(entity) -> float:
        """entity._fulfillment_log 内 Σfulfilled / Σ(fulfilled+defaulted)。deque 空 → 1.0。"""

    @staticmethod
    def record_settlement(entity: Union[Firm, Household], success: bool, tick: int) -> None:
        """记录一笔结算的履约/违约。按 tick 聚合，同 tick 合并。"""

    # ———— 动态抵押率 ————
    def calc_dynamic_collateral_ratio(self, entity: Union[Firm, Household]) -> float:
        """base_ratio + (1 - fulfillment_rate) * 0.4。履约率 1.0→0.10，0.0→0.50。"""

    # ———— 订单验证 ————
    def validate_order(self, state: WorldState, order: Order) -> Tuple[bool, str]:
        """
        卖方冻结额 = price*quantity*seller_ratio，买方冻结额 = price*quantity*buyer_ratio。
        检查双方余额各 >= 冻结额。劳动力额外校验：seller=Household, buyer=Firm。
        任一方余额不足或类型不匹配 → (False, reason)。
        """

    # ———— 抵押品管理 ————
    def freeze_collateral(self, state: WorldState, order: Order) -> None:
        """双方账户扣款 → collateral_pool，双方 outstanding_order_ids.add(order_id)。"""

    def release_collateral(self, state: WorldState, order: Order) -> None:
        """双方冻结金原路退回账户并 discard(order_id)，删除 collateral_pool 条目。"""

    def forfeit_collateral(self, state: WorldState, order: Order, defaulting_side: str) -> None:
        """违约方冻结金没收 → 转入对手方账户。defaulting_side: 'seller' | 'buyer'。"""

    # ———— 订单结算 ————
    def settle_order(self, state: WorldState, order: Order) -> Tuple[bool, str, bool]:
        """
        All-or-Nothing，仅结算 status="ALLOCATED" 且 settlement_tick==state.tick。
        返回 (ok, message, liquidated)。

        委托 _settle_goods()（普通商品）或 _settle_labor()（劳动力）。
        结算后调用 _check_liquidation()，若 cash<0 → 立即触发 liquidate_firm。
        不存在部分交付。
        """

    def _settle_goods(self, state, order) -> Tuple[bool, str, bool]:
        """
        卖方库存>=quantity 且 买方现金>=price*quantity
          → 转移商品、划拨货款、release_collateral(双方)、record_settled_price()、
            双方 record_settlement(True)
        任一不满足 → 释放非违约方抵押品 + 没收违约方抵押品转对方 +
          status="DEFAULTED" + 双方 record_settlement(False)
        """

    def _settle_labor(self, state, order) -> Tuple[bool, str, bool]:
        """
        seller=Household, buyer=Firm
          → household.is_employed=True, employer_firm_id=buyer.id,
            firm.employees.append(seller.id)
          → release_collateral(双方), 双方 record_settlement(True), 不记 price_history

        雇佣生命周期（跨 Tick）：
          - 工资发放：每 Tick 步骤 2，Simulator._pay_wages() 自动按 reservation_wage
            从 Firm→Household 划拨。Firm 余额不足 → record_settlement(False) 欠薪
          - 解雇：叶子函数从 firm.employees 移除，household.is_employed=False
          - 辞职：叶子函数设置 is_employed=False, employer_firm_id=None
          - 破产：liquidate_firm() 自动解雇所有员工
        """

    def _check_liquidation(self, state, entity) -> bool:
        """若 entity.cash < 0 → liquidate_firm(state, entity.id) → return True。"""

    # ———— 价格追踪 ————
    def record_settled_price(self, good_id: int, tick: int, price: float) -> None:
        """非 labor 商品 FULFILLED 时调用。"""

    def get_market_price_range(self, good_id: int) -> Tuple[float, float, float]:
        """返回 (min, max, avg) 基于 price_history[good_id] 最近成交记录。无记录 → (0, 0, 0)。"""

    # ———— 批量到期结算 ————
    def settle_all_expired(self, state: WorldState) -> Dict:
        """
        遍历 list(state.pending_orders)，结算到期订单。
        每笔结算后 cash<0 → 触发 liquidate_firm，并将该 Firm 剩余 pending_orders
        标记为 DEFAULTED（对手方抵押品按违约规则处理）。
        返回 {"settled": N, "defaulted": N, "liquidated": [firm_ids]}。
        """

    def _cascade_defaulted(self, state, firm_id, pending_orders) -> None:
        """破产企业的剩余 pending_orders 标记 DEFAULTED + forfeit_collateral + record_trade。"""

    # ———— 池维护 ————
    def expire_stale_orders(self, state: WorldState, expire_ticks: int) -> int:
        """
        market.supply/market.demand 中 OPEN 订单，
        creation_tick + expire_ticks <= state.tick → status="EXPIRED"，
        释放双方抵押品，移出池。expire_ticks 由 config 配置（默认 30）。
        返回被过期订单总数。
        """

    # ———— 破产清算 ————
    def liquidate_firm(self, state: WorldState, firm_id: int) -> Dict:
        """
        触发条件：cash < 0。清偿顺序：1.拖欠工资 2.欠税 3.返还股东（当前版本上限归零）。

        执行步骤：
        (a) 库存折价卖给 Government：创建 description="foreclosure" 的 FULFILLED Order，
            get_market_price_range(good_id).min 定价，Gov.cash -= M0守恒，入 all_orders + ledger
        (d) 追回 Firm 在 collateral_pool 的冻结抵押金 → firm.cash
        (b) 清偿顺序：拖欠工资（优先，reservation_wage）→ 欠税（residual*gov.tax_rate）→ 归零
        (c) 解雇所有员工（household.is_employed=False, employer_firm_id=None）
        (e) 池中 OPEN 订单 → CANCELLED，_release_counterparty 释放对手方抵押金
        (f) ALLOCATED 订单 → DEFAULTED，_release_counterparty 释放对手方抵押金
        (g) is_active = False
        返回 {"liquidated_firm", "foreclosure_value", "wages_paid", "success"}。
        """

    def _release_counterparty(self, state, order, firm_id) -> None:
        """释放对手方在指定订单中的抵押金，并 discard 其 outstanding_order_ids。"""
```

每个导致 order.status 变更的方法末尾须调用 `self.ledger.record_trade(order)`。
ClearHouse 内部保留变量名 `self.ledger`（实际类型为 TradeHistory），不暴露给用户。

## 3.3 信息噪声器 (core/noise.py)

所有策略获取的 MI 数据须经此模块。全局 seed 保证复现性。

```py
class InformationFriction:
    noise_types = ["gaussian", "uniform", "upward_bias", "downward_bias", "none"]

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def apply_noise(self, true_value: float, noise_type: str, params: Dict) -> float:
        """
        none      → 原值
        gaussian  → + N(0, params['sigma'])
        uniform   → + U(-params['range'], +params['range'])
        upward_bias   → * params['factor']  (factor > 1, 瞒报)
        downward_bias → * params['factor']  (factor < 1, 谎报)
        """

    def apply_dict(self, values: Dict[str, float], noise_type: str, params: Dict) -> Dict[str, float]:
        """批量施加噪声。"""
```

## 3.4 经济指标计算器 (core/reporter.py)

```py
class Reporter:
    @staticmethod
    def calc_gini(households: Dict[int, Household], goods: Dict[int, Good] = None) -> float:
        """wealth = cash + inventory 估值。inventory 估值 = qty * delivery_lag（代理单价）。"""

    @staticmethod
    def calc_engel(households: Dict[int, Household], goods: Dict[int, Good],
                   ledger: TradeHistory, n_ticks: int = 30) -> float:
        """食品支出 / 总消费支出。查 TradeHistory 近 n_ticks FULFILLED 记录，
        按 buyer_id 属于 households 且 good_type=="food" 统计。"""

    @staticmethod
    def calc_unemployment(households: Dict[int, Household]) -> float:
        """未就业家庭数 / 总家庭数。"""

    # calc_cpi 暂不实现。

    @staticmethod
    def snapshot(state: WorldState, ledger: TradeHistory) -> Dict:
        """返回 {"tick", "gini", "engel", "unemployment", "active_firms",
        "active_households", "total_firms", "total_households"} 八字段快照。"""
```

## 3.5 模拟器主循环 (core/simulator.py)

```py
class Simulator:
    def __init__(self, config_path: str, world_db_path: str, strategy_registry=None):
        self.config = self._load_config(config_path)
        self.noise = InformationFriction(seed=self.config.get("seed", 42))
        self.reporter = Reporter()
        self._id_seq = Sequence()
        self.order_factory = OrderFactory(self._id_seq)
        self.state = WorldLoader.load(world_db_path)
        self.clearing = ClearingHouse(
            ledger=self.state.market.history,
            base_collateral_ratio=self.config.get("base_collateral_ratio", 0.1),
            fulfillment_window_ticks=self.config.get("fulfillment_window_ticks", 30),
        )
        self.order_expire_ticks = self.config.get("order_expire_ticks", 30)
        self.mi_builder = MarketIntelligenceBuilder(self.noise, self.reporter, self.config)
        self.mi = self.mi_builder.build(self.state, self.state.market.history)
        self._reg = strategy_registry

    def tick(self) -> WorldState:
        """9 步 Tick。结算在前策略在后。步骤 9 构建 MI 缓存供下一 Tick 策略使用。"""
        state = self.state

        # 1. 结算到期订单
        self.clearing.settle_all_expired(state)

        # 2. 发放工资（Firm→Household，按 reservation_wage）
        self._pay_wages(state)

        # 3. 征税（Firm→Government，按 gov.tax_rate）
        self._collect_taxes(state)

        # 4. 发放失业金（Government→失业 Household，按 unemployment_benefit）
        self._disburse_unemployment(state)

        # 5. Strategy：调用注册的宏函数（F→H→G），apply() 内部分发 → new/cancel/update → validate → freeze → 入池
        self._execute_strategy(self.mi, state)

        # 6. Allocation：调用注册的分配策略 → 从池中配对 → ALLOCATED → 入 pending_orders
        self._execute_allocation(self.mi, state)

        # 7. 池维护：过期订单释放抵押品
        self.clearing.expire_stale_orders(state, self.order_expire_ticks)

        # 8. 实体 end_tick：失业 Household unemployment_ticks += 1
        self._end_tick_for_all(state)
        state.tick += 1

        # 9. 构建 MarketIntelligence（含噪声），缓存供下一 Tick 使用
        self.mi = self.mi_builder.build(state, state.market.history)

        return state

    def run(self, n_ticks: int) -> List[Dict]:
        """批量运行，返回每 Tick 指标快照列表。"""
```

### 内部方法

```py
def _pay_wages(self, state):
    """遍历 is_active Firm，对在职员工：firm.cash>=wage→划拨 + record_settlement(True)；
       余额不足→record_settlement(False) 欠薪，不阻塞。"""

def _collect_taxes(self, state):
    """Firm.cash *= (1-tax_rate)；Government.cash += tax_revenue。
       只对 active 且 cash>0 的 Firm 征税。"""

def _disburse_unemployment(self, state):
    """失业 Household（is_employed=False, unemployment_ticks>0）← Government.cash。
       余额不足按比例递减。"""

def _execute_strategy(self, mi, state):
    """按 F→H→G 顺序调用注册的宏函数 fn(mi, goods)。
       宏函数内部通过 _Slot.apply() 分发到实体、构建 AgentOrders、调用 _dispatch_agent_result。"""

def _dispatch_agent_result(self, state, result: Dict):
    """处理 {new, cancel, update} 三字段。
       new: validate→freeze→入 supply/demand 池（失败跳过）。
       cancel: release→从池移除→status=CANCELLED→record_trade。
       update: 先 validate(new)，失败整体跳过；通过后 cancel 旧+new。"""

def _add_new_order(self, state, order):
    """creation_tick=state.tick, status=OPEN, 入 all_orders, freeze_collateral, 按 side 入池。"""

def _cancel_order(self, state, order_id):
    """OPEN 订单 → release_collateral, status=CANCELLED, record_trade, 从池移除。"""

def _execute_allocation(self, mi, state):
    """调用 allocate_fn(mi, supply, demand, goods, market, pricing_fn)。
    返回 (matched, remaining_supply, remaining_demand)。
    matched 订单 → ALLOCATED, settlement_tick=state.tick+delivery_lag, 入 pending_orders, record_trade。
    remaining 写回 market.supply / market.demand。"""

def _end_tick_for_all(self, state):
    """遍历 households：is_employed=False → unemployment_ticks += 1。"""
```

### 关键设计决策

- **state 必须在 clearing 之前创建**：`WorldLoader.load(db_path)` 必须先于 `ClearingHouse(ledger=state.market.history)` 执行。
- **宏函数调度**：_execute_strategy 不遍历实体。每个 slot 只调用一次注册的宏函数 `fn(mi, goods)`。迭代权交给用户，在宏函数内部通过 `apply()` 分发。
- **AgentOrders + OrderFactory**：用户通过 `orders.new()` 记录意图参数（无 order_id），策略执行后 `_consume()` 调用 `OrderFactory.from_params()` 自动注入 thread-safe 的唯一 sequence ID。
- **订单流向**：_add_new_order 时 `creation_tick` 在引擎侧注入（`order.creation_tick = state.tick`），不受策略控制。

## 3.6 世界初始化 (core/data_layer.py)

### WorldLoader（从 SQLite 加载世界）

```py
class WorldLoader:
    @staticmethod
    def load(db_path: str) -> WorldState:
```

建表结构与 §3.1 dataclass 一一对应。关联表：
- `firm_inventory(firm_id, good_id, quantity)`
- `household_inventory(household_id, good_id, quantity)`
- `firm_employees(firm_id, household_id)`

关键约束：
- `delivery_lag >= 1`、`good_type IN ('food','labor','capital','consumer','raw_material')`
- `governments` 表恰好 1 行
- Firm ID 与 Household ID 无冲突（加载时校验，冲突则抛 ValueError）
- 所有实体表包含 `labels TEXT NOT NULL DEFAULT 'default'` 列（逗号分隔字符串，加载时 split(",") 还原为 list）

加载流程：
1. sqlite3.connect → 逐表读取
2. 构造 WorldState, tick=0
3. MarketData（含 supply/demand/history）由 `WorldState.__post_init__` 自动创建
4. pending_orders / all_orders / collateral_pool 初始化为空

### WorldBuilder（流式 API 构建世界）

替代手写 SQL 的世界生成方式，提供链式调用构建 WorldState 并持久化到 SQLite：

```py
class WorldBuilder:
    def add_good(self, good_id, name, good_type, delivery_lag=1) -> 'WorldBuilder': ...
    def add_firm(self, id, cash, *, capacity=0, labels=None, inventory=None, employees=None) -> 'WorldBuilder': ...
    def add_household(self, id, cash, *, reservation_wage=0, is_employed=False,
                      employer_firm_id=None, inventory=None, labels=None) -> 'WorldBuilder': ...
    def add_government(self, id, cash, *, tax_rate=0, unemployment_benefit=0, labels=None) -> 'WorldBuilder': ...
    def build(self) -> WorldState: ...   # 不写 DB，直接返回 WorldState
    def save(self, db_path) -> None: ...  # 持久化到 SQLite（覆盖或新建）
```

### Sequence + OrderFactory

```py
class Sequence:
    """线程安全的单调递增 ID 生成器。next() -> 'order_1', 'order_2', ..."""

class OrderFactory:
    """从 AgentOrders.new()/update() 积攒的参数 dict 构造 Order，自动注入 order_id。"""
    def __init__(self, id_seq: Sequence): ...
    def from_params(self, **kwargs) -> Order: ...
```

# 4. 策略接口

## 4.1 策略架构

ESE 的策略架构只有三个层次：

| 概念 | 在哪写 | 管什么 |
|------|--------|--------|
| **宏函数** | `@ese.firm` / `@ese.household` / `@ese.government` 装饰的函数 | 每 slot 每 Tick 调一次。接收 `(mi, goods)`。内部通过 `apply()` 分发到实体。 |
| **apply()** | 宏函数内部调用 `ese.firm.apply(label, leaf_fn, **params)` | 筛选 `label in entity.labels` 的实体 → 构造 AgentOrders → 调用叶子函数 |
| **叶子函数** | 普通 Python 函数 `(entity, orders, **params)` | 每个实体每轮具体做什么。无需装饰器。 |

### 宏函数签名

```py
@ese.firm
def firm_macro(mi: MarketIntelligence, goods: Dict[int, Good], market: MarketData):
    ese.firm.apply("farm", farm_behavior)
    ese.firm.apply("workshop", workshop_behavior)

@ese.household
def hh_macro(mi: MarketIntelligence, goods: Dict[int, Good], market: MarketData):
    ese.household.apply("default", household_spend)

@ese.government
def gov_macro(mi: MarketIntelligence, goods: Dict[int, Good], market: MarketData):
    gov = list(ese._simulator.state.governments.values())[0]
    if mi.unemployment_rate > 0.3:
        gov.unemployment_benefit *= 1.5
```

### apply() 工作机制

```py
def apply(self, label: str, leaf_fn, **params):
    state = self._sim.state
    results = []
    for entity in self._get_entities():
        if hasattr(entity, "is_active") and not entity.is_active:
            continue                            # 跳过已退出 Firm
        if label not in entity.labels:
            continue
        my_orders = entity.outstanding_orders(state.all_orders)
        orders = AgentOrders(
            my_orders, self._sim.order_factory, entity_id=entity.id
        )
        result = leaf_fn(entity, orders, self._sim.mi, state.market, **params)
        results.append(result)
        self._sim._dispatch_agent_result(state, orders._consume())
    return results
```

- `label in entity.labels` 匹配（一个实体可以有多个标签，如 `["steel", "tech"]`）
- 叶子函数是普通 Python 函数，不注册、不装饰器，`apply()` 直接传入实体实例
- 叶子函数可以同时 `orders.new()` 下单和 `return` 数据给宏函数
- `self._sim.mi` 和 `state.market` 作为固定第三、第四位置参数注入叶子函数，`**params` 链式透传

### 叶子函数签名

```py
# Firm 叶子
def farm_behavior(firm: Firm, orders: AgentOrders, mi: MarketIntelligence, market: MarketData):
    if firm.inventory[2] >= 1.0:               # defaultdict(float) 自动返回 0.0
        firm.inventory[2] -= 1.0
        firm.inventory[1] = firm.inventory[1] + 5.0
    if firm.inventory[1] > 2.0:
        orders.new(good_id=1,
                   quantity=min(firm.inventory[1] - 2, 10), price=2.0,
                   side=OrderSide.SUPPLY)

# Household 叶子
def household_spend(hh: Household, orders: AgentOrders, mi: MarketIntelligence, market: MarketData):
    budget = hh.cash * 0.2
    if budget < 0.5:
        return
    orders.new(good_id=1,
               quantity=budget * 0.7 / 2.0, price=2.0, side=OrderSide.DEMAND)
```

### 分配策略

```py
@ese.allocation
def alloc(mi, supply, demand, goods, market, pricing=None):
    # 配对逻辑
    return matched, remaining_supply, remaining_demand

@ese.allocation.pricing
def mid_price(supply_order, demand_order, config, market):
    return (supply_order.price + demand_order.price) / 2.0
```

- allocation 宏函数接收 `(mi, supply, demand, goods, market, pricing=None)`，返回 `(matched, remaining_supply, remaining_demand)`
- pricing 子槽通过 `@ese.allocation.pricing` 注册，引擎在调用 allocation 时自动注入 `market` 和 `pricing`

### 三种制度的策略差异

引擎不变、结算器不变、破产规则不变。区别仅在于宏函数怎么用 `apply()`：

**市场**：`apply()` 只管分发，叶子自己读 MI、自己下单。不关心返回值。

**计划**：`apply()` 跑多轮。第一轮叶子 `return` 产能/库存上报，宏函数在中间做全局修订，最后一轮叶子才下单。

**混合**：基线是市场。MI 指标触发后临时改为计划式写法（同一 Tick 内 `apply()` 在"不返回值"和"返回值"之间无缝切换）。

## 4.2 市场情报 (MarketIntelligence)

每 Tick 末尾由 `MarketIntelligenceBuilder.build()` 从 WorldState 聚合生成，经 InformationFriction 加噪后缓存为 `self.mi`，供下一 Tick 策略使用。

```py
@dataclass
class MarketIntelligence:
    tick: int
    gini: float                          # 基尼系数（经噪声）
    unemployment_rate: float             # 失业率（经噪声）
    engel: float                         # 恩格尔系数（经噪声）
    sector_avg_price: Dict[int, float]   # 各 good_id 挂单加权均价（经噪声）
    sector_total_supply: Dict[int, float]# 各 good_id 总供给量（经噪声）
    sector_total_demand: Dict[int, float]# 各 good_id 总需求量（经噪声）
    tax_rate: float                      # 税率（直接读取）
    unemployment_benefit: float          # 失业金（直接读取）
    active_firms: int                    # 活跃企业数
```

关键规则：
- 所有 `sector_*` 聚合字段和 `gini` / `unemployment_rate` / `engel` 经 InformationFriction 加噪
- MI 不包含任何企业个体数据（无 `all_firms` / `all_households` 字段）
- 策略获取自身状态通过 `apply()` 传入的实体实例直接读取（vendor_inventory、cash 等），不经过 MI
- 自身订单状态通过 `entity.outstanding_orders()` + AgentOrders 读取，不经过 MI
- 计划/市场的唯一区别：config 中 `noise_type="none"`（计划，完美信息）vs `"gaussian"`（市场，加噪）

### 数据对象语义映射

| 对象 | 现实对应 | 使用者 | 噪声 |
|------|---------|-------|------|
| market.supply | 市场挂单（卖方报价簿） | 策略写入，Allocation 读取 | 否 |
| market.demand | 市场询价（买方求购簿） | 策略写入，Allocation 读取 | 否 |
| pending_orders | 已分配、待交割的远期合约 | ClearingHouse 读写 | 否 |
| collateral_pool | 交易保证金账户 | ClearingHouse 读写 | 否 |
| MarketIntelligence | 上一 Tick 结束时的统计局汇总报表 | 策略只读决策 | **是** |
| goods | 商品分类目录（公开知识） | 策略可查，不加噪 | 否 |
| TradeHistory | 不可篡改的审计账本 | 策略/Reporter 查询，ClearingHouse 写入 | 否 |

## 4.3 历史账本 (core/ledger.py)

```py
@dataclass
class TradeRecord:
    tick: int; order_id: str
    seller_id: int; buyer_id: int; good_id: int
    quantity: float; price: float
    status: str  # OPEN/ALLOCATED/FULFILLED/DEFAULTED/CANCELLED/EXPIRED

class TradeHistory:
    def __init__(self):
        self.records: List[TradeRecord] = []

    def record_trade(self, order: Order) -> None:
        """追加订单生命周期事件。tick 取 order.creation_tick。"""

    def get_trades_by_agent(self, agent_id: int, n: int = 30) -> List[TradeRecord]:
        """某主体最近 n 笔记录（seller_id 或 buyer_id 匹配）。"""

    def get_avg_price_by_good(self, good_id: int, n: int = 30) -> float:
        """某商品最近 n 笔 FULFILLED 单价的简单平均。无记录 → 0.0。"""

    def get_all_recent_prices(self, n: int = 30) -> Dict[int, List[float]]:
        """所有商品最近 n 笔 FULFILLED 价格列表，按 good_id 分组。"""
```

TradeHistory 嵌入在 `WorldState.market.history` 中，不再由 Simulator 单独持有。
ClearingHouse 内部保留变量名 `self.ledger`（实际类型为 TradeHistory）。ClearingHouse 内部还维护独立的 `price_history` 用于破产定价，两者不交叉。

# 5. 用户入口 Engine (core/engine.py)

Engine 是用户面向的唯一入口类，封装 Simulator + _StrategyRegistry，提供装饰器风格的策略注册和 run/save 方法。

```py
class Engine:
    def __init__(self, config_path: str, world_db_path: str, output_dir: str = "./output"):
        self._registry = _StrategyRegistry()
        self._simulator = Simulator(config_path, world_db_path, self._registry)

        self.firm = _Slot(self._registry, "firm",
            get_entities_fn=lambda: list(self._simulator.state.firms.values()),
            simulator=self._simulator)
        self.household = _Slot(...)   # 同理
        self.government = _Slot(...)  # 同理
        self.allocation = _AllocationSlot(self._registry,
            get_entities_fn=lambda: None, simulator=self._simulator)

    def run(self, n_ticks: int) -> List[Dict]:
        """委托 self._simulator.run(n_ticks)。"""

    def save(self, snapshots: List[Dict], prefix: str = "ese") -> str:
        """将 snapshot 列表导出为 CSV 和 PNG 图表（gini, unemployment, engel, active_firms 四图）。"""
```

# 6. _Slot 与 apply()

```py
class _Slot:
    def __init__(self, registry, slot_name, get_entities_fn, simulator): ...

    def __call__(self, func):
        """装饰器：self._reg.set_primary(self._name, func) → return func。"""

    def apply(self, label: str, leaf_fn, **params):
        """筛选 label in entity.labels 的实体 → AgentOrders → leaf_fn(entity, orders, mi, market) → _consume。"""
```

```py
class _AllocationSlot(_Slot):
    """继承 _Slot，新增 .pricing property 装饰器用于注册定价函数。"""

    @property
    def pricing(self):
        """装饰器：self._reg.set_pricing(func)。"""
```

# 7. 内部策略注册表 (core/_registry.py)

```py
class _Slot:
    def __init__(self, name): self.primary = None
    def set_primary(self, func): ...
    def get(self) -> Optional[Callable]: ...

class _StrategyRegistry:
    def __init__(self):
        self._slots = {"firm": _Slot(...), "household": _Slot(...),
                       "government": _Slot(...), "allocation": _Slot(...)}
        self._pricing = None

    def set_primary(self, slot, func): ...
    def set_pricing(self, func): ...
    def get(self, slot): ...
    def get_pricing(self): ...
```

# 8. 性能与规模估算
- 目标规模：50 企业、500 家庭
- 单 Tick 耗时：~0.03~0.05 秒
- 五年（1825 Tick）批量运行：约 2~4 分钟

# 9. 编码指令

遵守 §1.1 四大禁令。所有随机性通过 InformationFriction 注入。Good.delivery_lag >= 1 加载时强制校验。

MVP 优先级：
- core/entities.py — 完整数据类 + AgentOrders + MarketData + 履约率追踪
- core/clearing_house.py — 全部方法（价格追踪、双向冻结、All-or-Nothing 结算含劳动力、破产清算、池过期、级联违约）
- core/simulator.py — 9 步 tick() + run() + _dispatch_agent_result + 宏函数调度
- core/data_layer.py — WorldLoader + WorldBuilder + Sequence + OrderFactory
- core/engine.py — Engine + _Slot + _AllocationSlot
- core/ledger.py + core/noise.py + core/reporter.py + core/market_intelligence.py + core/_registry.py — 完整实现
- config/default.yaml — 运行参数

# 附录：待解决问题

## A. 政府赤字
当前 `_disburse_unemployment` 中 Government.cash 不足时按比例递减发放，已解决 fallback 问题。

## B. 多政府架构
当前 `WorldLoader.load()` 强制校验恰好 1 个政府。`WorldState.governments` 保留为 `Dict[int, Government]`（与 firms/households 数据结构一致），但多政府场景需引入 jurisdiction 机制后方可启用：
- Firm/Household 增加 `government_id` 字段（管辖权归属）
- `_collect_taxes` 改为按管辖征税
- `_disburse_unemployment` 改为各政府仅对自己管辖的 Household 发放福利
- 跨辖区贸易（关税、转移支付等）需独立设计

## C. 信息可见性
当前全员共享同一个 MarketIntelligence（只含宏观汇总指标），无 per-agent obs 视图。计划/市场的唯一区别是 config 中 `noise_type="none"` / `"gaussian"`。
