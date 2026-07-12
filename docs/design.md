ESE (Economic Simulation Engine)

# 1. 设计约束

## 1.1 四大设计禁令
- 1 — 禁止上帝矩阵：所有算法只能基于历史账本（Ledger）进行统计推断，不得直接读取全局精确的投入产出表（A）。
- 2 — 时间具象化：所有生产订单必须有"承诺-交付"的延迟队列；到期未交付则触发违约。
- 3 — 策略可插拔：企业/家庭/政府/分配策略由用户通过 Python 函数注册，内核不内置任何策略逻辑。
- 4 — 匹配即制度：ClearingHouse 不得包含任何分配算法。匹配逻辑是用户策略的一部分。结算器只负责不可变物理规则：订单验证、抵押品冻结/释放/没收、破产清算、交易记账。

# 2. 文件与目录结构

ese/
├── requirements.txt          # numpy, pandas, pyyaml (sqlite3 标准库)
├── config/
│   ├── default.yaml          # 运行参数：Tick数、base_collateral_ratio、noise_type、order_expire_ticks、fulfillment_window_ticks
│   └── seed_world.db
├── core/                     # 不可变内核
│   ├── entities.py           # Good, Firm, Household, Government, Order, WorldState
│   ├── clearing_house.py     # 结算器
│   ├── noise.py              # InformationFriction
│   ├── reporter.py           # 指标计算器
│   ├── registry.py           # 策略注册表
│   ├── simulator.py          # 主循环
│   └── ledger.py             # 历史账本
├── examples/                # 示例策略（demo 参考）
│   ├── generate_town.py       # 生成初始 world 数据库
│   └── town.py

# 3. 核心模块

## 核心数据对象

- **obs** — 经济快照（项目构建，策略只读）。Tick 末尾从 WorldState 采集各主体财务/库存/产能，经 InformationFriction 加噪。策略基于此判断市场状况——拿到的可能是别人的虚报财报。计划体制 noise=none（完美信息，如计委调取企业数据），市场体制注入噪声（企业"打听"到的同行数据不可全信）。自身状态（my_state）不加噪——自己知道自己的真实账。

- **Ledger** — 公开交易账本（项目写入，策略/Reporter 查询）。每笔订单状态变更时 ClearingHouse 自动追加 TradeRecord。记录的是不可篡改的成交事实（谁向谁以什么价格买了多少、履约还是违约）。任何主体可查询历史成交记录和均价——这是"市场上真正发生过什么"，不掺假。

- **supply_pool / demand_pool** — 持久挂单池（项目维护）。策略挂单写入，AllocationPolicy 读取配对，ClearingHouse 清理过期。

- **pending_orders** — 待交割队列（项目）。已配对、等待 settlement_tick 到期的订单。ClearingHouse 到期结算。

- **collateral_pool** — 双边保证金（项目）。`"{order_id}_seller"` / `"{order_id}_buyer"` → 冻结金额。仅 ClearingHouse 操作。

- **price_history** — 成交价缓存（项目）。deque(maxlen=30)，按 good_id 存 (tick, price)。仅用于 liquidate_firm 破产定价。

- **Order** — 交易订单（策略创建，内核管状态）。status 状态机：OPEN→ALLOCATED→FULFILLED/DEFAULTED/CANCELLED/EXPIRED。order_type 标记 B2B / B2C / foreclosure / employment。

- **Firm / Household / Government** — 经济主体。seed_world.db 定义初始值（实验人员）。cash / inventory / is_active 仅内核可改；FirmStrategy 可通过 firm 引用调变属性。

- **Good** — 商品定义（实验人员配置）。goods 公开知识，策略直接查，不加噪。good_type 决定结算行为，delivery_lag 决定交割延迟。

- **WorldState** — 全局状态容器（项目）。承载以上全部对象和池，自身不做决策。

## 3.1 数据实体层 (core/entities.py)

```py
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
    order_type: str = "B2C"            # B2B | B2C | foreclosure | employment
    creation_tick: int
    settlement_tick: int = 0            # 0=未分配哨兵；分配后=state.tick+delivery_lag
    status: str = "OPEN"                # OPEN→ALLOCATED→FULFILLED|DEFAULTED，OPEN→CANCELLED，OPEN→EXPIRED
```
劳动力交易：Good.good_type="labor"，使用标准 Order，结算时特殊处理（建立雇佣关系、内核自动划拨工资，见 §3.2 settle_order）。

```py
@dataclass
class Firm:
    id: int
    cash: float
    inventory: Dict[int, float]         # good_id -> quantity
    capacity: float
    collateral: float = 0               # 自有资产净值（冻结金在 WorldState.collateral_pool）
    is_active: bool = True
    employees: List[int] = field(default_factory=list)
    active_order_ids: Set[str] = field(default_factory=set)  # OPEN/ALLOCATED 状态订单
    _fulfillment_log: deque = field(default_factory=lambda: deque(maxlen=30))  # 存储 (fulfilled, defaulted, tick)

@dataclass
class Household:
    id: int
    cash: float
    inventory: Dict[int, float]
    labor_ask_price: float = 0.0        # 期望工资
    is_employed: bool = False
    employer_firm_id: Optional[int] = None
    unemployment_ticks: int = 0
    _fulfillment_log: deque = field(default_factory=lambda: deque(maxlen=30))  # 存储 (fulfilled, defaulted, tick)

@dataclass
class Government:
    id: int
    cash: float
    tax_rate: float = 0.0
    money_supply: float = 0.0           # 预留，当前版本不启用
    unemployment_benefit: float = 0.0
    _fulfillment_log: deque = field(default_factory=lambda: deque(maxlen=30))  # 存储 (fulfilled, defaulted, tick)（未来功能预留）

@dataclass
class WorldState:
    tick: int
    firms: Dict[int, Firm]
    households: Dict[int, Household]
    governments: Dict[int, Government]
    goods: Dict[int, Good]
    supply_pool: List[Order] = field(default_factory=list)      # 卖方挂单，持久待分配
    demand_pool: List[Order] = field(default_factory=list)      # 买方挂单，持久待分配
    pending_orders: List[Order] = field(default_factory=list)   # 已分配、待交割
    all_orders: Dict[str, Order] = field(default_factory=dict)  # order_id→Order，全局索引
    collateral_pool: Dict[str, float] = field(default_factory=dict)  # "{order_id}_seller"/"{order_id}_buyer" → 冻结金额
```

实现注意事项：
- `_fulfillment_log: deque(maxlen=30)` 按 Tick 聚合存储 `(fulfilled, defaulted, tick)` 元组。同 Tick 内多次交割合并为同一条目（pop/modify/append）。履约率 = Σfulfilled / Σ(fulfilled + defaulted)。deque 为空 → 1.0。maxlen 控制窗口容量（默认 30 个活跃 Tick）。
- `Firm.active_order_ids` 由 ClearingHouse 维护：Order 进入 OPEN/ALLOCATED 时 `add(order_id)`（双方各自加入），进入终止态时 `discard(order_id)`（双方各自移除）。

## 3.2 结算器 (core/clearing_house.py)

结算器是不可变内核，不实现任何分配算法。

```py
class ClearingHouse:

    def __init__(self, ledger: 'Ledger', base_collateral_ratio: float = 0.1, fulfillment_window_ticks: int = 30):
        self.ledger = ledger
        self.base_collateral_ratio = base_collateral_ratio
        self.fulfillment_window_ticks = fulfillment_window_ticks
        self.price_history: Dict[int, deque] = {}  # {good_id: deque((tick, price), maxlen=30)}

    # 每个导致 order.status 变更的方法末尾须调用 self.ledger.record_trade(order)。

    # ———— 价格追踪 ————
    def record_settled_price(self, good_id: int, tick: int, price: float) -> None:
        """非 labor 商品 FULFILLED 时调用。"""

    def get_market_price_range(self, good_id: int) -> Tuple[float, float, float]:
        """返回 (min, max, avg) 基于 price_history[good_id] 最近成交记录。"""

    # ———— 订单验证 ————
    def calc_dynamic_collateral_ratio(self, entity: Union[Firm, Household]) -> float:
        """base_ratio + (1 - fulfillment_rate) * 0.4。履约率 = entity._fulfillment_log 内 Σfulfilled / Σ(fulfilled+defaulted)。履约率 1.0→0.10，0.0→0.50。"""

    def validate_order(self, state: WorldState, order: Order) -> Tuple[bool, str]:
        """
        卖方冻结额 = price*quantity*seller_ratio，买方冻结额 = price*quantity*buyer_ratio。
        检查双方余额各 >= 冻结额。劳动力额外校验：seller=Household, buyer=Firm。
        任一方余额不足或类型不匹配 → (False, reason)。
        """

    # ———— 抵押品管理 ————
    def freeze_collateral(self, state: WorldState, order: Order) -> None:
        """双方账户扣款 → collateral_pool["{order_id}_seller"/"{order_id}_buyer"]。"""

    def release_collateral(self, state: WorldState, order: Order) -> None:
        """双方冻结金原路退回账户，删除 collateral_pool 条目。"""

    def forfeit_collateral(self, state: WorldState, order: Order, defaulting_side: str) -> None:
        """违约方冻结金没收 → 转入对手方账户。defaulting_side: 'seller' | 'buyer'。"""

    # ———— 订单结算 ————
    def settle_order(self, state: WorldState, order: Order) -> Tuple[bool, str]:
        """
        All-or-Nothing，仅结算 status="ALLOCATED" 且 settlement_tick==state.tick。

        普通商品（good_type != "labor"）：
          卖方库存>=quantity 且 买方现金>=price*quantity
          → 转移商品、划拨货款、release_collateral(双方)、record_settled_price()、
            双方 record_settlement(True)
          任一不满足 → 释放非违约方抵押品 + 没收违约方抵押品转对方 +
            status="DEFAULTED" + 双方 record_settlement(False)

        劳动力（good_type="labor"）：
          seller=Household, buyer=Firm
          → household.is_employed=True, employer_firm_id=buyer.id,
            firm.employees.append(seller.id)
          → release_collateral(双方), 双方 record_settlement(True), 不记 price_history

          雇佣生命周期（跨 Tick）：
            - 工资发放：每 Tick 步骤 2，Simulator._pay_wages() 自动按 labor_ask_price
              从 Firm→Household 划拨。Firm 余额不足 → record_settlement(False) 欠薪
            - 解雇：FirmStrategy 从 firm.employees 移除，household.is_employed=False
            - 辞职：HouseholdStrategy 设置 is_employed=False, employer_firm_id=None
            - 破产：liquidate_firm() 自动解雇所有员工

        结算后 cash<0 → 立即触发 liquidate_firm。
        不存在部分交付。
        """

    def settle_all_expired(self, state: WorldState) -> Dict:
        """
        遍历 list(state.pending_orders)，结算到期订单。
        每笔结算后 cash<0 → 触发 liquidate_firm，并将该 Firm 剩余 pending_orders
        标记为 DEFAULTED（对手方抵押品按违约规则处理）。
        返回 {"settled": N, "defaulted": N, "liquidated": [firm_ids]}。
        """

    # ———— 池维护 ————
    def expire_stale_orders(self, state: WorldState, expire_ticks: int) -> int:
        """
        supply_pool/demand_pool 中 OPEN 订单，
        creation_tick + expire_ticks <= state.tick → status="EXPIRED"，
        释放双方抵押品，移出池。expire_ticks 由 config 配置（默认 30）。
        """

    # ———— 破产清算 ————
    def liquidate_firm(self, state: WorldState, firm_id: int) -> Dict:
        """
        触发条件：cash < 0。清偿顺序：1.拖欠工资 2.欠税 3.经营性债务 4.返还股东。
        a. 对每项库存创建 order_type="foreclosure" 的 Order，Government 为买方、
           按 get_market_price_range(good_id).min 定价，即时划拨（Government→Firm），M0 守恒
        b. 按清偿顺序分配残值
        c. 解雇所有员工
        d. 通过 state.all_orders 查找 firm.active_order_ids 的 Order，
           释放该 Firm 在 collateral_pool 的冻结金（对手方冻结金保留，后续 forfeit_collateral）
        e. 池中 OPEN 订单 → CANCELLED（对手方 release_collateral）
        f. ALLOCATED 订单 → DEFAULTED（对手方 forfeit_collateral）
        g. is_active = False
        """
```

## 3.3 信息噪声器 (core/noise.py)

所有策略获取的历史数据须经此模块。全局 seed 保证复现性。

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
    def calc_gini(households: Dict[int, Household]) -> float:
        """基于 household.cash + inventory 市值。"""

    @staticmethod
    def calc_engel(households: Dict[int, Household], goods: Dict[int, Good],
                   ledger: 'Ledger', n_ticks: int = 30) -> float:
        """食品支出 / 总消费支出。查 Ledger 近 n_ticks FULFILLED 记录，按 good_type=="food" 统计。"""

    @staticmethod
    def calc_unemployment(households: Dict[int, Household]) -> float:
        """未就业家庭数 / 总家庭数。"""

    # calc_cpi 暂不实现。

    @staticmethod
    def snapshot(state: WorldState, ledger: 'Ledger') -> Dict:
        """返回当前 Tick 全部经济指标快照。"""
```

## 3.5 模拟器主循环 (core/simulator.py)

```py
class Simulator:
    def __init__(self, config_path: str, world_db_path: str):
        self.config = self._load_config(config_path)
        self.ledger = Ledger()
        self.noise = InformationFriction(seed=self.config.get("seed", 42))
        self.clearing = ClearingHouse(
            ledger=self.ledger,
            base_collateral_ratio=self.config.get("base_collateral_ratio", 0.1),
            fulfillment_window_ticks=self.config.get("fulfillment_window_ticks", 30),
        )
        self.reporter = Reporter()
        self.state = self._load_world(world_db_path)
        self.order_expire_ticks = self.config.get("order_expire_ticks", 30)
        self.last_obs = self._build_observations(self.state)  # tick 0 初始快照

    def tick(self) -> WorldState:
        """9 步 Tick。结算在前策略在后。步骤 9 构建 obs 缓存供下一 Tick 策略使用。"""
        state = self.state

        # 1. 结算到期订单
        self.clearing.settle_all_expired(state)

        # 2. 发放工资（Firm→Household，按 labor_ask_price）
        self._pay_wages(state)

        # 3. 征税（Firm→Government，按 gov.tax_rate）
        self._collect_taxes(state)

        # 4. 发放失业金（Government→失业 Household，按 unemployment_benefit）
        self._disburse_unemployment(state)

        # 5. Strategy：用户策略 → new/cancel/update → validate → freeze → 入池
        self._execute_strategy(self.last_obs, state)

        # 6. Allocation：用户分配策略 → 从池中配对 → ALLOCATED → 入 pending_orders
        self._execute_allocation(self.last_obs, state)

        # 7. 池维护：过期订单释放抵押品
        self.clearing.expire_stale_orders(state, self.order_expire_ticks)

        # 8. 实体 end_tick + Tick++
        self._end_tick_for_all(state)
        state.tick += 1

        # 9. 构建观测数据（含噪声），缓存供下一 Tick 使用
        self.last_obs = self._build_observations(state)

        return state

    def run(self, n_ticks: int) -> List[Dict]:
        """批量运行，返回每 Tick 指标快照列表。"""
        snapshots = []
        for _ in range(n_ticks):
            if not self.tick():
                break
            snapshots.append(self.reporter.snapshot(self.state, self.ledger))
        return snapshots

    def _pay_wages(self, state: WorldState) -> None:
        """遍历 is_active Firm，对在职员工：firm.cash>=wage→划拨；余额不足→record_settlement(False)欠薪。"""
        pass

    def _collect_taxes(self, state: WorldState) -> None:
        """Firm.cash → Government.cash，按 gov.tax_rate。税基由 GovStrategy 通过 tax_rate 间接控制。"""
        pass

    def _disburse_unemployment(self, state: WorldState) -> None:
        """失业 Household（is_employed=False, unemployment_ticks>0）← Government.cash。余额不足按比例递减。"""
        pass

    def _execute_strategy(self, obs: Dict, state: WorldState) -> None:
        """
        按 F→H→G 顺序调用 FirmStrategy/HouseholdStrategy/GovernmentStrategy。
        每个策略接收 (obs, self_entity, state.goods)，返回 {new: [Order], cancel: [order_id], update: [Order]}。
        处理规则：
          - new: validate→freeze→入池。失败单条跳过。
          - cancel: release→从池移除。
          - update: 先 validate(new)，失败则整体跳过（旧订单保留不动）；
            通过后 cancel 旧 + new（同 new 流程）。
        """
        pass

    def _execute_allocation(self, obs: Dict, state: WorldState) -> None:
        """
        调用 AllocationPolicy.allocate(obs, supply_pool, demand_pool)
        → (matched, remaining_supply, remaining_demand)。
        对 matched: status="ALLOCATED", settlement_tick=state.tick+delivery_lag, 入 pending_orders。
        remaining 写回池。
        """
        pass

    def _end_tick_for_all(self, state: WorldState) -> None:
        """所有 Firm/Household/Government 调用 end_tick()（推送履约率窗口）。"""
        pass

    def _build_observations(self, state: WorldState) -> Dict:
        """构建 obs 字典（§4.2），经 InformationFriction 加噪。"""
        pass
```

## 3.6 世界初始化 (SQLite)

`_load_world(db_path)` 从 SQLite 加载。建表字段与 §3.1 dataclass 一对一对应。关联表：
- `firm_inventory(firm_id, good_id, quantity)`
- `household_inventory(household_id, good_id, quantity)`
- `firm_employees(firm_id, household_id)`

关键约束：`delivery_lag >= 1`，`good_type IN ('food','labor','capital','consumer','raw_material')`，`governments` 表恰好 1 行（多政府尚未支持——缺乏 Firm/Household 的管辖权归属字段）。

加载流程：
1. sqlite3.connect → 逐表读取
2. 构造 WorldState, tick=0
3. 初始化空 supply_pool/demand_pool/pending_orders/all_orders/collateral_pool
4. 各实体 `_fulfillment_log` 自动初始化为 `deque(maxlen=30)` 空窗。Simulator 可根据 config 重建 maxlen 匹配 `fulfillment_window_ticks`。

# 4. 策略接口

## 4.1 策略签名（四类插槽，用户编写）

策略类型           | 签名                                                              | 返回
———————————————————|———————————————————————————————————|————————————————————
FirmStrategy       | decide(obs: Dict, firm: Firm, goods: Dict[int, Good]) → Dict    | {new: [Order], cancel: [id], update: [Order]}
HouseholdStrategy  | decide(obs: Dict, hh: Household, goods: Dict[int, Good]) → Dict | 同上
GovernmentStrategy | decide(obs: Dict, gov: Government, goods: Dict[int, Good]) → Dict | 同上
AllocationPolicy   | allocate(obs, supply_pool, demand_pool, goods) → (matched, remaining_supply, remaining_demand) | 配对分配

生产逻辑内化于 FirmStrategy。劳动力走标准 Order(good_type="labor")，由 AllocationPolicy 统一分配。
内核按 F→H→G 固定顺序调用。策略只读 obs，goods 为公开知识不加噪。

## 4.2 观测字典

obs 全员开放相同结构，经 InformationFriction 加噪。计划/市场的唯一区别：noise_type="none"/"gaussian"。

 ```py
obs = {
    "my_id": int,
    "my_state": Firm | Household | Government,    # 自身完整状态（无噪声）
    "my_supply_orders": List[Order],               # 自身在 supply_pool 的订单
    "my_demand_orders": List[Order],               # 自身在 demand_pool 的订单
    "all_firms": List[Firm],                       # 经噪声
    "all_households": List[Household],             # 经噪声
    "governments": List[Government],               # 经噪声
    "tick": int,
}
```

### 数据对象语义映射

| 对象 | 现实对应 | 使用者 | 噪声 |
|------|---------|-------|------|
| supply_pool | 市场挂单（卖方报价簿） | 策略写入，AllocationPolicy 读取 | 否 |
| demand_pool | 市场询价（买方求购簿） | 策略写入，AllocationPolicy 读取 | 否 |
| pending_orders | 已分配、待交割的远期合约 | ClearingHouse 读写 | 否 |
| collateral_pool | 交易保证金账户 | ClearingHouse 读写 | 否 |
| obs | 上一 Tick 结束时的经济快照（财报/行情/公开报表） | 策略只读决策 | **是** |
| goods | 商品分类目录（公开知识） | 策略可查，不加噪 | 否 |
| Ledger | 不可篡改的审计账本 | 策略/Reporter 查询，ClearingHouse 写入 | 否 |

## 4.3 历史账本 (core/ledger.py)

```py
@dataclass
class TradeRecord:
    tick: int; order_id: str
    seller_id: int; buyer_id: int; good_id: int
    quantity: float; price: float
    status: str  # OPEN/ALLOCATED/FULFILLED/DEFAULTED/CANCELLED/EXPIRED

class Ledger:
    def __init__(self):
        self.records: List[TradeRecord] = []

    def record_trade(self, order: Order) -> None:
        """追加订单生命周期事件。"""

    def get_trades_by_agent(self, agent_id: int, n: int = 30) -> List[TradeRecord]:
        """某主体最近 n 笔记录。"""

    def get_avg_price_by_good(self, good_id: int, n: int = 30) -> float:
        """某商品最近 n 笔 FULFILLED 均价。"""

    def get_all_recent_prices(self, n: int = 30) -> Dict[int, List[float]]:
        """所有商品最近 n 笔 FULFILLED 价格列表。"""
```

Ledger 用于策略查询和审计。ClearingHouse 内部维护独立的 `price_history` 用于破产定价，两者不交叉。

# 5. 性能与规模估算
- 目标规模：50 企业、500 家庭
- 单 Tick 耗时：~0.03~0.05 秒
- 五年（1825 Tick）批量运行：约 2~4 分钟

# 6. 编码指令

遵守 §1.1 四大禁令。所有随机性通过 InformationFriction 注入。Good.delivery_lag >= 1 加载时强制校验。

按 §2 目录结构生成文件。MVP 优先级：
- core/entities.py — 完整数据类 + 履约率追踪
- core/clearing_house.py — 全部方法（价格追踪、双向冻结、All-or-Nothing 结算含劳动力、破产清算含 active_order_ids 清理、池过期）
- core/simulator.py — 9 步 tick() + run() + _load_world()
- core/ledger.py + core/noise.py + core/reporter.py — 完整实现
- core/registry.py — 注册表
- config/default.yaml — 运行参数

# 附录：待解决问题

## A. 政府赤字
若 Government.cash 不足以覆盖失业金支出，当前未定义 fallback。备选：按比例递减 / 停发 / 自动发债（需引入国债机制）。

## B. 多政府架构
当前 `_load_world` 强制校验恰好 1 个政府。`WorldState.governments` 保留为 `Dict[int, Government]`（与 firms/households 数据结构一致），但多政府场景需引入 jurisdiction 机制后方可启用：
- Firm/Household 增加 `government_id` 字段（管辖权归属）
- `_collect_taxes` 改为按管辖征税（而非所有政府对所有 Firm 征税）
- `_disburse_unemployment` 改为各政府仅对自己管辖的 Household 发放福利
- 跨辖区贸易（关税、转移支付等）需独立设计
