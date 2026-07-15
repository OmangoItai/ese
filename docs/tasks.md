# ESE 分步实施任务

按依赖顺序执行。每轮完成后验证通过才进入下一轮。

---

## 1. 数据骨架

**产出**：`core/entities.py`、`core/entities_test.py`

**依据**：design.md §3.1

- [x] 1.1 创建 `ese/core/` 目录，新建 `ese/core/__init__.py`
- [x] 1.2 实现 `Good` dataclass（good_id, name, good_type, delivery_lag）
- [x] 1.3 实现 `Order` dataclass（含 status 状态机六态、order_type 四类）
- [x] 1.4 实现 `Firm` dataclass（cash, inventory, capacity, collateral, is_active, employees, active_order_ids）
- [x] 1.5 实现 `Household` dataclass（cash, inventory, labor_ask_price, is_employed, employer_firm_id, unemployment_ticks）
- [x] 1.6 实现 `Government` dataclass（cash, tax_rate, money_supply, unemployment_benefit）
- [x] 1.7 实现 `WorldState` dataclass（tick, firms, households, governments, goods, supply_pool, demand_pool, pending_orders, all_orders, collateral_pool）
- [x] 1.8 为 Firm/Household/Government 添加 `_fulfillment_log: deque[Tuple[int,int,int]]` 字段（(fulfilled, defaulted, tick) 按 Tick 聚合，maxlen=30 常数内存）
- [x] 1.9 编写 `core/entities_test.py`：实例化所有类、断言默认值、WorldState 嵌套组装
- [x] 1.10 验证：`uv run pytest core/entities_test.py -v` 全绿

---

## 2. Ledger + Noise（纯函数模块）

**产出**：`core/ledger.py`、`core/noise.py`、`core/ledger_test.py`、`core/noise_test.py`

**依据**：design.md §3.3（InformationFriction）、§4.3（Ledger + TradeRecord）

- [x] 2.1 实现 `TradeRecord` dataclass（tick, order_id, seller_id, buyer_id, good_id, quantity, price, status）
- [x] 2.2 实现 `Ledger` 类：`record_trade(order)` 追加 TradeRecord
- [x] 2.3 实现 `Ledger.get_trades_by_agent(agent_id, n)` 按主体倒序取最近 n 条
- [x] 2.4 实现 `Ledger.get_avg_price_by_good(good_id, n)` 取 FULFILLED 均价
- [x] 2.5 实现 `Ledger.get_all_recent_prices(n)` 按商品分组返回价格列表
- [x] 2.6 编写 `core/ledger_test.py`：20 条混合记录 → get_avg_price_by_good 与手动计算一致
- [x] 2.7 实现 `InformationFriction` 类：`__init__(seed)` 固定 seed
- [x] 2.8 实现 `apply_noise(value, noise_type, params)` 支持 5 种噪声（gaussian/uniform/upward_bias/downward_bias/none）
- [x] 2.9 实现 `apply_dict(values, noise_type, params)` 批量施加噪声
- [x] 2.10 编写 `core/noise_test.py`：seed=42 时 1000 次 gaussian(sigma=0.1) 均值偏差 < 0.05；bias 检验方向正确
- [x] 2.11 验证：`uv run pytest core/ledger_test.py core/noise_test.py -v` 全绿

---

## 3. 结算器

### 3a. 抵押品管理 + 价格追踪 + 履约率

**产出**：`core/clearing_house.py`（部分）、`core/clearing_house_test.py`

**依据**：design.md §3.2 前半段

- [x] 3a.1 创建 `ClearingHouse` 类：`__init__(ledger, base_collateral_ratio, fulfillment_window_ticks=30)`，初始化 `price_history: Dict[int, deque(maxlen=30)]`
- [x] 3a.2 实现履约率追踪：`_fulfillment_log: deque(maxlen=30)` 存储 `(fulfilled, defaulted, tick)`，同 Tick 聚合；`_fulfillment_rate` = Σfulfilled / Σ(fulfilled+defaulted)，空 deque → 1.0
- [x] 3a.3 实现 `calc_dynamic_collateral_ratio(entity)`：`base_ratio + (1 - fulfillment_rate) * 0.4`
- [x] 3a.4 实现 `validate_order(state, order)`：计算双方冻结额，检查余额；labor 额外检验 buyer=Firm seller=Household
- [x] 3a.5 实现 `freeze_collateral(state, order)`：双方 cash 扣款 → collateral_pool 写入两个键
- [x] 3a.6 实现 `release_collateral(state, order)`：collateral_pool 退 → 双方 cash，删除条目
- [x] 3a.7 实现 `forfeit_collateral(state, order, defaulting_side)`：违约方冻结金 → 对手方账户
- [x] 3a.8 实现 `record_settled_price(good_id, tick, price)`：非 labor 商品成交价入 price_history
- [x] 3a.9 实现 `get_market_price_range(good_id)`：返回 (min, max, avg) based on price_history
- [x] 3a.10 编写测试：履约率 100% → ratio=0.1；0% → ratio=0.5
- [x] 3a.11 编写测试：freeze → cash 减少 collateral_pool 有键；release → 恢复并删除
- [x] 3a.12 编写测试：forfeit("seller") → 卖方 cash 不恢复，买方 cash 增加卖方冻结额
- [x] 3a.13 编写测试：3 笔成交价记录 → get_market_price_range 返回正确 (min, max, avg)
- [x] 3a.14 验证：`uv run pytest core/clearing_house_test.py -v` 全绿

### 3b. 结算 + 破产 + 池过期

**产出**：补完 `core/clearing_house.py`、扩展 `core/clearing_house_test.py`

**依据**：design.md §3.2 后半段

- [x] 3b.1 实现 `settle_order(state, order)`：仅处理 status=ALLOCATED 且 settlement_tick==state.tick
- [x] 3b.2 settle_order 普通商品逻辑：库存≥quantity 且 买方cash≥price*quantity → 转移库存、划拨货款、release_collateral、record_settled_price、履约率入 True
- [x] 3b.3 settle_order 普通商品不足 → 释放非违约方抵押品、没收违约方抵押品转对方、status=DEFAULTED、履约率入 False
- [x] 3b.4 settle_order labor 逻辑：seller=Household buyer=Firm → is_employed=True, employer_firm_id=buyer.id, firm.employees.append(seller.id), release_collateral
- [x] 3b.5 settle_order 结算后 cash<0 → 立即调用 `liquidate_firm(state, firm_id)`
- [x] 3b.6 实现 `settle_all_expired(state)`：遍历 pending_orders 到期订单逐笔 settle_order；中间触发 liquidation 则将同 Firm 剩余 pending_orders 标记 DEFAULTED
- [x] 3b.7 实现 `liquidate_firm(state, firm_id)`：库存 foreclosure 折现（Government 为买方，get_market_price_range.min 定价）
- [x] 3b.8 liquidate_firm 清偿顺序：拖欠工资 → 欠税 → 经营性债务 → 返还股东
- [x] 3b.9 liquidate_firm 解雇所有员工（household.is_employed=False, employer_firm_id=None）
- [x] 3b.10 liquidate_firm 清理 active_order_ids：池中 OPEN → CANCELLED（对手方 release）；ALLOCATED → DEFAULTED（对手方 forfeit）；释放破产方在 collateral_pool 的冻结金
- [x] 3b.11 liquidate_firm 最后设置 is_active=False
- [x] 3b.12 实现 `expire_stale_orders(state, expire_ticks)`：池中 OPEN 订单 creation_tick+expire_ticks<=state.tick → EXPIRED，release_collateral，移出池
- [x] 3b.13 编写测试：库存/现金充足 → FULFILLED（商品转移+价款划拨+抵押品释放）
- [x] 3b.14 编写测试：库存不足 → DEFAULTED（卖方 forfeit + 买方 release + 买方收到赔偿）
- [x] 3b.15 编写测试：labor 结算 → household.is_employed=True, firm.employees 包含 household_id
- [x] 3b.16 编写测试：结算后 firm.cash<0 → liquidate_firm 触发，员工 is_employed=False
- [x] 3b.17 编写测试：池中订单超时 → EXPIRED，抵押品释放
- [x] 3b.18 验证：`uv run pytest core/clearing_house_test.py -v` 全绿

---

## 4. Reporter（指标计算）

**产出**：`core/reporter.py`、`core/reporter_test.py`

**依据**：design.md §3.4

- [x] 4.1 创建 `Reporter` 类（纯静态方法）
- [x] 4.2 实现 `calc_gini(households)`：wealth = cash + inventory_estimate，本阶段 estimate 用常数（goods 的 delivery_lag 作为 weight）
- [x] 4.3 实现 `calc_engel(households, goods, ledger, n_ticks)`：查 Ledger 近 n_ticks FULFILLED 记录，food 支出/总消费
- [x] 4.4 实现 `calc_unemployment(households)`：is_employed=False 占比
- [x] 4.5 实现 `snapshot(state, ledger)`：聚合 gini + engel + unemployment + tick + active_entities 数 → 字典
- [x] 4.6 编写测试：10 户极贫富分布 → gini > 0.5
- [x] 4.7 编写测试：全部等值 → gini ≈ 0（容忍 0.01）
- [x] 4.8 编写测试：造一批 food 交易 → engel 在 0~1 区间
- [x] 4.9 编写测试：5 户中 2 户失业 → unemployment == 0.4
- [x] 4.10 编写测试：snapshot 返回字典包含全部指标键
- [x] 4.11 验证：`uv run pytest core/reporter_test.py -v` 全绿

---

## 5. Simulator 内核（世界加载 + tick 流水线不含策略）

**产出**：`core/simulator.py`、`config/default.yaml`、`config/seed_world.db`、`core/simulator_test.py`

**依据**：design.md §3.5、§3.6

- [x] 5.1 创建 `config/default.yaml`：seed, base_collateral_ratio, noise_type, order_expire_ticks, fulfillment_window_ticks, n_ticks
- [x] 5.2 创建 `config/seed_world.db`：最小世界（2 企业、5 家庭、3 种商品 good_type 各不同、1 政府）
- [x] 5.3 实现 `_load_config(config_path)`：读 YAML 返回 dict
- [x] 5.4 实现 `_load_world(db_path)`：从 SQLite 逐表读取，构造 WorldState(tick=0)，校验 delivery_lag>=1、good_type 枚举、governments 恰好 1 行（多政府未支持）
- [x] 5.5 实现 `_pay_wages(state)`：遍历 is_active Firm，employed Household ← firm.cash -= labor_ask_price；余额不足跳过不阻塞
- [x] 5.6 实现 `_collect_taxes(state)`：Firm.cash *= (1-tax_rate)；Government.cash += tax_revenue
- [x] 5.7 实现 `_disburse_unemployment(state)`：Government.cash -= unemployment_benefit → 失业 Household
- [x] 5.8 实现 `_end_tick_for_all(state)`：失业 Household 的 unemployment_ticks 递增；`_fulfillment_log` 无需维护（deque maxlen 自动驱逐，结算时实时写入）
- [x] 5.9 实现 `Simulator.__init__`：load_config → Ledger → InformationFriction → ClearingHouse → Reporter → load_world → 初始 obs
- [x] 5.10 实现 `tick()` 9 步循环（步骤 5 `_execute_strategy` 和步骤 6 `_execute_allocation` 留空 pass）
- [x] 5.11 实现 `run(n_ticks)`：循环 tick() 收集 snapshot
- [x] 5.12 编写测试：load_world → WorldState 与 SQLite 数据一致
- [x] 5.13 编写测试：pay_wages → firm.cash 减少、household.cash 增加，金额正确
- [x] 5.14 编写测试：collect_taxes → Government.cash 增加
- [x] 5.15 编写测试：连续 5 个 tick 循环不崩溃
- [x] 5.16 验证：`uv run pytest core/simulator_test.py -v` 全绿

---

## 6. 策略层 + 分配层

**产出**：`core/registry.py`、`examples/demo_strategies.py`、补完 `core/simulator.py`

**依据**：design.md §4.1（四类策略签名）、§4.2（obs 结构）

- [x] 6.1 创建 `core/registry.py`
- [x] 6.2 实现 `Registry`：四槽字典 `{"firm": None, "household": None, "government": None, "allocation": None}`，`register()` 和 `get()` 方法
- [x] 6.3 实现 `simulator._build_observations(state)`：按 §4.2 结构构建 obs，含 my_supply_orders/my_demand_orders，经 InformationFriction 加噪（自身 my_state 不加噪）
- [x] 6.4 实现 `simulator._execute_strategy(obs, state)`：按 F→H→G 顺序调用注册策略，处理 `{new, cancel, update}` 返回值
- [x] 6.5 _execute_strategy 中 new 订单：validate → freeze → 入池（失败跳过不阻塞）
- [x] 6.6 _execute_strategy 中 cancel：release_collateral → 从池移除 → status=CANCELLED → ledger.record_trade
- [x] 6.7 _execute_strategy 中 update：新订单 validate 失败则整体跳过；通过后 cancel 旧 + new
- [x] 6.8 实现 `simulator._execute_allocation(obs, state)`：调用 AllocationPolicy.allocate() → matched → ALLOCATED + settlement_tick=state.tick+delivery_lag → pending_orders；remaining 写回池
- [x] 6.9 创建 `examples/demo_strategies.py`：FirmStrategy（生产 consumer good，挂 supply_pool）
- [x] 6.10 demo：HouseholdStrategy（用 cash 买 food，挂 demand_pool）
- [x] 6.11 demo：GovernmentStrategy（调整 tax_rate，不参与交易）
- [x] 6.12 demo：AllocationPolicy.allocate()（同 good_id 配对，价低 supply 优先）
- [x] 6.13 编写测试：Firm demo → supply_pool 增长
- [x] 6.14 编写测试：Household demo → demand_pool 增长
- [x] 6.15 编写测试：Allocation 配对 → pending_orders 有 ALLOCATED 订单
- [x] 6.16 编写测试：完整 1 tick → Firm inventory 减少、Household inventory 增加、双方 cash 变更
- [x] 6.17 编写测试：obs 中 my_state 无噪声，all_firms 有噪声
- [x] 6.18 验证：`uv run pytest core/simulator_test.py -v` 全绿

---

## 7. obs 重构为 MarketIntelligence（宏观情报层）

**产出**：`core/market_intelligence.py`、修改 `core/simulator.py`、修改所有策略文件

**依据**：docs/update.md §4、docs/context.md（禁止上帝视角、统计局报表模拟）

**动机**：

- 当前 `obs` 字典传递的是**个体级裸数据**（all_firms/all_households 的完整快照 + 噪声），等同于上帝视野
- 真实世界中，企业/政府决策依赖的是**统计机构汇总报表**和**公开市场情报**（GDP、CPI、行业均价、失业率），不存在个体级数据
- 重构后将 `obs` 拆为两层：策略通过 `entity` 参数获取自身完整状态，通过 `MarketIntelligence` 获取宏观/中观聚合情报

---

### 7.1 新建 `MarketIntelligence` 数据结构

- [x] 7.1.1 创建 `core/market_intelligence.py`
- [x] 7.1.2 实现 `MarketIntelligence` dataclass，字段如下：

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `tick` | `int` | `state.tick` | 当前周期 |
| `gini` | `float` | Reporter.calc_gini | 基尼系数 |
| `unemployment_rate` | `float` | Reporter.calc_unemployment | 失业率 |
| `engel` | `float` | Reporter.calc_engel | 恩格尔系数 |
| `sector_avg_price` | `Dict[int, float]` | 从 supply_pool 聚合 | 各 good_id 挂单均价 |
| `sector_total_supply` | `Dict[int, float]` | 从 supply_pool 聚合 | 各 good_id 总挂单量 |
| `sector_total_demand` | `Dict[int, float]` | 从 demand_pool 聚合 | 各 good_id 总询价量 |
| `tax_rate` | `float` | Government.tax_rate | 税率 |
| `unemployment_benefit` | `float` | Government.unemployment_benefit | 失业金 |
| `active_firms` | `int` | 计数 | 活跃企业数 |

> 暂不包含：`gdp`、`cpi`、`central_bank_rate`、`labor_income_share`、`sector_cr3`、`government_announcement`、`data_lag`、`reporting_bias`（依赖尚未实现的 MetricsCalculator 或央行实体，留待 P2 阶段补充）

- [x] 7.1.3 为各 `sector_*` 字段添加 `InformationFriction` 噪声注入点（调用现有 `self.noise.apply_noise(value, noise_type, params)`）

### 7.2 实现 `MarketIntelligenceBuilder`

- [x] 7.2.1 在 `core/market_intelligence.py` 中实现 `MarketIntelligenceBuilder` 类
- [x] 7.2.2 `__init__(self, noise, reporter, config)`：持有 noise 实例、reporter 实例、config 引用
- [x] 7.2.3 `build(self, state, ledger)` 方法：从 `state` 收集原始数据 → 计算指标 → 加噪 → 返回 `MarketIntelligence` 实例
- [x] 7.2.4 `_collect_raw(self, state, ledger)` 私有方法：遍历 `supply_pool`/`demand_pool` 聚合各 good_id 均价和总量；调 Reporter 算 gini/unemployment/engel
- [x] 7.2.5 `_aggregate_pool(pool, agg)` 辅助方法：返回各 good 的均价（agg="avg"）或总量（agg="sum"）

### 7.3 修改 `core/simulator.py`

- [x] 7.3.1 在 `Simulator.__init__` 中初始化 `self.mi_builder = MarketIntelligenceBuilder(self.noise, self.reporter, self.config)`
- [x] 7.3.2 删除 `_build_observations` 方法（不再构建个体级 obs 字典）
- [x] 7.3.3 删除 `_agent_obs` 方法（不再需要 per-agent 观测视图）
- [x] 7.3.4 tick() 步骤 9 改为 `self.mi = self.mi_builder.build(state, self.ledger)`（替换 `self.last_obs = self._build_observations(state)`）
- [x] 7.3.5 修改 `_execute_strategy`：策略调用从 `strategy(agent_obs, entity, state.goods)` 改为 `strategy(mi, entity, state.goods)`；删除 `_agent_obs` 调用链
- [x] 7.3.6 修改 `_execute_allocation`：分配调用从 `allocate_fn(obs, ...)` 改为 `allocate_fn(mi, ...)`

**策略签名变更汇总：**

| 插槽 | 旧签名 | 新签名 |
|------|--------|--------|
| firm | `(obs, firm, goods)` | `(mi, firm, goods)` |
| household | `(obs, hh, goods)` | `(mi, hh, goods)` |
| government | `(obs, gov, goods)` | `(mi, gov, goods)` |
| allocation | `(obs, supply_pool, demand_pool, goods)` | `(mi, supply_pool, demand_pool, goods)` |

### 7.4 迁移现有策略

- [x] 7.4.1 修改 `examples/town_strategies.py`：所有策略函数 `obs` 参数改为 `mi`，`obs["tick"]` 改为 `mi.tick`，其余逻辑不变
- [x] 7.4.2 修改 `examples/demo_strategies.py`（如存在）：N/A（文件不存在，现有策略仅 town_strategies.py）
- [x] 7.4.3 检查策略中是否有依赖 `obs` 中已删除字段的逻辑——无，所有策略仅使用 `obs["tick"]`

### 7.5 更新测试

- [x] 7.5.1 修改 `core/simulator_test.py`：`TestBuildObservations` → `TestMarketIntelligence`；`TestObsNoise` → `TestMiNoise`；所有 obs 字典断言调整为 mi 字段断言
- [x] 7.5.2 新增 `core/market_intelligence_test.py`：MI 测试内嵌于 `simulator_test.py` 的 `TestMarketIntelligence` 和 `TestMiNoise` 类中
- [x] 7.5.3 验证：`uv run pytest core/simulator_test.py -v` **36/36 全绿**
- [x] 7.5.4 验证：`uv run pytest core/ -v` **158/158 全绿**
- [x] 7.5.5 端到端验证：`uv run python examples/generate_town.py && uv run python examples/town.py` → **正常跑完 50 tick，输出 CSV/图表**

---

## 8. 策略注册重构：Registry → Engine + _Slot

**产出**：`core/_registry.py`、`core/engine.py`、`ese/__init__.py`；删除 `core/registry.py`；修改 `core/entities.py`、`core/simulator.py`；重写 `examples/town_strategies.py`、`examples/town.py`

**依据**：docs/update.md §0、§1、§2、§7

**动机**：

- 当前 `Registry` 使用魔术字符串 `reg.register("firm", fn)` + `reg.get("firm")`，无 IDE 补全，`reg` 既要注册又要 get 语义混乱
- 新设计用 `Engine` 作为唯一入口，槽名即方法名：`@ese.firm`、`@ese.firm.label("farm")`、`ese.firm.use("farm", mi, firm, goods)`
- `@ese.firm` 是调度器（orchestrator），`@ese.firm.label("x")` 是标签策略，调度器通过 `ese.firm.use(...)` 分发。不是并列关系，是包含关系
- pricing 挂载为 `@ese.allocation.pricing` 子槽，引擎执行 allocation 时自动注入
- 无匹配标签时 `ese.firm.use(...)` 发 `RuntimeWarning` + 返回空 result，不抛异常
- 新增顶层 `ese/` 包作为对外唯一 facade

---

### 8.1 新建内部查表层 `core/_registry.py`

- [x] 8.1.1 实现 `_Slot` 类：`__init__(name)`，属性 `name`、`primary: Optional[Callable]`、`labeled: Dict[str, Callable]`
- [x] 8.1.2 `_Slot.set_primary(func)`：设置主策略（调度器）
- [x] 8.1.3 `_Slot.set_labeled(label, func)`：设置标签策略
- [x] 8.1.4 `_Slot.get(label=None) -> Optional[Callable]`：`label` 为 `None` 返回 primary，否则返回 `labeled[label]`（不存在返回 `None`）
- [x] 8.1.5 实现 `_StrategyRegistry` 类：`__init__()` 创建四个 `_Slot`（firm/household/government/allocation）+ `_pricing: Optional[Callable]`
- [x] 8.1.6 `_StrategyRegistry.set_primary(slot, func)` / `set_labeled(slot, label, func)` / `set_pricing(func)` / `get(slot, label=None)` / `get_pricing()`

### 8.2 新建用户入口层 `core/engine.py`

- [x] 8.2.1 实现 `_Slot` 类（装饰器代理，与 `_registry._Slot` 不同）：
  - `__init__(registry: _StrategyRegistry, slot_name: str)`：持有 `_reg` 和 `_name`
  - `__call__(func)`：装饰器，`_reg.set_primary(_name, func)`，返回 `func`
  - `label(label: str)`：返回装饰器，内层 `_reg.set_labeled(_name, label, func)`
  - `use(label: str, mi, entity, goods)`：`strategy = _reg.get(_name, label)`；找到则 `strategy(mi, entity, goods)`；找不到则 `warnings.warn(RuntimeWarning)` + 返回 `{"new": [], "cancel": [], "update": []}`
- [x] 8.2.2 实现 `_AllocationSlot(_Slot)`：
  - 继承 `_Slot`，`__init__` 调用 `super().__init__(registry, "allocation")`
  - `pricing` 属性（`@property`）：返回装饰器，内层 `_reg.set_pricing(func)`
- [x] 8.2.3 实现 `Engine` 类：
  - `__init__(config_path, world_db_path)`：创建 `_StrategyRegistry()` + `Simulator(config_path, world_db_path, self._registry)`；将 `_registry` 传入 Simulator 构造函数（替代旧的 `set_registry`）
  - 创建四个属性：`self.firm = _Slot(...)`、`self.household = _Slot(...)`、`self.government = _Slot(...)`、`self.allocation = _AllocationSlot(...)`
  - `run(n_ticks: int) -> List[Dict]`：委托 `self._simulator.run(n_ticks)`

### 8.3 新建公共 facade `ese/__init__.py`

- [x] 8.3.1 创建 `ese/__init__.py`
- [x] 8.3.2 `from core.engine import Engine`
- [x] 8.3.3 re-export：`from core.entities import Good, Order, Firm, Household, Government, WorldState`
- [x] 8.3.4 re-export：`from core.market_intelligence import MarketIntelligence`

### 8.4 修改 `core/entities.py`

- [x] 8.4.1 `Firm` dataclass 新增 `strategy_label: str = "default"`
- [x] 8.4.2 `Household` dataclass 新增 `strategy_label: str = "default"`
- [x] 8.4.3 `Government` dataclass 新增 `strategy_label: str = "default"`

### 8.5 修改 `core/simulator.py`

- [x] 8.5.1 删除 `from core.registry import Registry` 导入
- [x] 8.5.2 删除 `self.registry = Registry()` 和 `set_registry()` 方法
- [x] 8.5.3 `Simulator.__init__` 接受 `strategy_registry: _StrategyRegistry` 参数（由 `Engine` 传入），存为 `self._reg`
- [x] 8.5.4 `_execute_strategy(self, mi, state)`：`firm_fn = self._reg.get("firm")`，遍历 `state.firms` 调用 `firm_fn(mi, firm, state.goods)`，`dispatch_agent_result` 处理返回值。household/government 同理
- [x] 8.5.5 `_execute_allocation(self, mi, state)`：`allocate_fn = self._reg.get("allocation")`；`pricing_fn = self._reg.get_pricing()`；调用 `allocate_fn(mi, supply, demand, goods, pricing_fn)`
- [x] 8.5.6 分配函数签名变更：`allocate_fn(mi, supply_pool, demand_pool, goods, pricing=None)` — 引擎注入 pricing 为第 5 个参数

### 8.6 删除旧 `core/registry.py`

- [x] 8.6.1 删除 `core/registry.py`（功能已迁移到 `_registry.py` + `engine.py`）

### 8.7 重写 `examples/town_strategies.py`

- [x] 8.7.1 从 `from core.registry import Registry` → 策略函数改为接收 `mi: MarketIntelligence, entity, goods` 签名（与现有 mi 重构一致）
- [x] 8.7.2 无 `Registry` 实例——策略文件只定义纯函数，注册在 `town.py` 中通过 `@ese.xxx` 完成
- [x] 8.7.3 firm 调度器：`@ese.firm` 定义的函数体用 `ese.firm.use(firm.strategy_label, mi, firm, goods)` 分发
- [x] 8.7.4 标签策略：`@ese.firm.label("farm")` 注册农场逻辑，`@ese.firm.label("workshop")` 注册工坊逻辑
- [x] 8.7.5 allocation 策略：`@ese.allocation` 注册，签名含 `pricing=None` 参数
- [x] 8.7.6 pricing 策略：`@ese.allocation.pricing` 注册，签名 `(supply_order, demand_order, config)`

### 8.8 重写 `examples/town.py`

- [x] 8.8.1 `from ese import Engine`
- [x] 8.8.2 创建 `ese = Engine("config/default.yaml", "town_world.db")`
- [x] 8.8.3 装饰器注册所有策略（`@ese.firm`、`@ese.firm.label(...)`、`@ese.household`、`@ese.government`、`@ese.allocation`、`@ese.allocation.pricing`）
- [x] 8.8.4 `snapshots = ese.run(n_ticks=50)`
- [x] 8.8.5 保存 CSV、绘图逻辑不变

### 8.9 适配测试

- [x] 8.9.1 修改 `core/simulator_test.py`：删除对 `Registry` 的导入和 `set_registry` 调用；用 `_StrategyRegistry` + `Simulator(..., registry)` 替代
- [x] 8.9.2 新增 `core/engine_test.py`：测试 `_Slot.__call__` 注册、`label()` 注册、`use()` 查+调、无标签 warning
- [x] 8.9.3 新增 `core/engine_test.py`：测试 `_AllocationSlot.pricing` 注册 + `get_pricing()` 获取
- [x] 8.9.4 验证：`uv run pytest core/ -v` 全绿

### 8.10 迁移种子数据库

- [x] 8.10.1 修改 `tools/generate_town.py`：firms/households INSERT 增加 `strategy_label TEXT DEFAULT 'default'` 列
- [x] 8.10.2 修改 `core/simulator._load_world`：firms 表读取时增加 `strategy_label` 字段
- [x] 8.10.3 重新生成 `town_world.db` 和 `config/seed_world.db`
- [x] 8.10.4 现有数据 `strategy_label` 统一填充 `"default"`

### 8.11 端到端验证

- [x] 8.11.1 `uv run python examples/town.py` → 正常跑完 50 tick，输出 CSV/图表
- [x] 8.11.2 无注册策略的实体 → 控制台输出 `RuntimeWarning`（而非 crash）
- [x] 8.11.3 `uv run pytest core/ -v` 全绿

---

## 9. 数据层：AgentOrders + 世界生成 API

**产出**：`core/entities.py`（修改）、`core/data_layer.py`（新增）、`ese/__init__.py`（修改）；修改 `core/simulator.py`、`examples/town.py`、`examples/generate_town.py`、`readme.md`；适配所有 `core/*_test.py`

**依据**：本文件 §9（新设计）；docs/update.md §5（数据层三层架构草稿）

**动机**：

- 当前 `Order.order_id` 是必填字段，用户在策略中手拼字符串（如 `f"f{firm.id}_sell_food_{mi.tick}"`），不能保证唯一性，且不应该由用户管理
- 当前策略需手动管理 `return {"new": [...], "cancel": [...], "update": [...]}` 三字段字典，啰嗦
- 世界生成依赖手写 SQL（`examples/generate_town.py` 158 行 CREATE TABLE + INSERT），啰嗦且易错
- 引擎内部缺少统一的订单 ID 生成器和世界定义 API，数据层职责散落在 `Simulator` 各处
- 未来可能将运行时热数据（池、订单）替换为 Redis 等外部缓存，需要清晰的数据边界

**核心设计决策**：

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 用户操作入口 | 新类型 `OrderNew` / 参数式 `orders.new()` / 装饰器隐式 | **`orders.new()` 挂在已有 `orders` 参数上** | 无新 import、无新参数、用户自然地在策略内部直接操作 `orders` |
| 策略返回值 | `return {new, cancel, update}` vs 不 return | **不 return** | `orders.new()` 直接记录意图，引擎策略执行后统一读取 |
| 引擎侧管道 | 改动 vs 不动 | **不动 `_dispatch_agent_result`** | `orders._consume()` 返回的仍是 `{new, cancel, update}` 三字段，原有管道完整保留 |
| 世界生成 | 手写 SQL vs Python API | **`WorldBuilder` 流式 API** | `w.add_firm(...).save()` 替代 158 行 SQL |
| 引擎内部订单 | 用 Orders API vs 直接 `Order(...)` | **直接 `Order(...)`** | `liquidate_firm` 等引擎内部代码是"可信代码"；`foreclosure_*` 等语义化 ID 对调试有价值 |
| 分配策略 | 受影响 vs 不受影响 | **不受影响** | 分配策略签名（返回 tuple）和流程不变 |

**策略签名汇总（与 §8 一致，不变）：**

| 插槽 | 签名 |
|------|------|
| firm | `(mi, firm, goods, orders)` |
| household | `(mi, hh, goods, orders)` |
| government | `(mi, gov, goods, orders)` |
| allocation | `(mi, supply_pool, demand_pool, goods, pricing=None)` |

---

### 9.1 修改 `core/entities.py`：新增 `AgentOrders`

- [x] 9.1.1 新增 `AgentOrders` 类：

```python
class AgentOrders:
     """策略中的 orders 参数。可遍历（读写清单条）且可操作（new/cancel/update）。
    方法调用只记录意图，引擎策略执行后统一处理。
    """
    def __init__(self, orders: list[Order]):
        self._orders = orders          # 当前 OPEN/ALLOCATED 订单列表
        self._new: list[dict] = []     # 收集新建意图
        self._cancel: list[str] = []   # 收集撤销意图
        self._update: list[dict] = [] # 收集替换意图


    # ——— 可遍历（只读当前订单）———

    def __iter__(self): return iter(self._orders)
    def __getitem__(self, i): return self._orders[i]
    def __len__(self): return len(self._orders)


    # ——— 用户操作接口（记录意图，非直接 CRUD）———

    def new(self, *, seller_id: int, buyer_id: int, good_id: int,
            quantity: float, price: float, side: OrderSide = OrderSide.SUPPLY,
            description: str = "") -> None: ...

    def cancel(self, order_id: str) -> None: ...

    def update(self, order_id: str, *, seller_id: int, buyer_id: int,
                good_id: int, quantity: float, price: float,
                side: OrderSide = OrderSide.SUPPLY,
                description: str = "") -> None: ...


    # ——— 引擎内部调用 ————

    def _consume(self) -> dict:
        """取出并清空积攒的意图，返回 {new, cancel, update} 给 _dispatch_agent_result。"""
```

- [x] 9.1.2 `Order.order_id` 保持 `str`（无默认值）——仅引擎内部构造，用户不碰。`Order` 保留在 `ese` facade 中作为只读类型导出（用户遍历 `orders` 时拿到这些 `Order` 对象）

### 9.2 新建 `core/data_layer.py`：Sequence + OrderFactory + WorldLoader + WorldBuilder

- [x] 9.2.1 实现 `Sequence` 类：线程安全的自动递增计数器，`next() -> str` 返回 `f"order_{n}"`

- [x] 9.2.2 实现 `OrderFactory` 类：

```python
class OrderFactory:
    def __init__(self, id_seq: Sequence): ...

    def from_params(self, *, seller_id, buyer_id, good_id, quantity, price,
                    side=OrderSide.SUPPLY, description="") -> Order:
        """从 orders.new() 积攒的参数 dict 构造 Order，注入 order_id。"""

    def from_update(self, update_params: dict) -> Order:
        """从 orders.update() 积攒的参数构造 Order，order_id 沿用旧单的。"""
```

- [x] 9.2.3 实现 `WorldLoader` 类（从 `core/simulator.py` 的 `_load_world` 静态方法迁移，代码逻辑不变）：

```python
class WorldLoader:
    @staticmethod
    def load(db_path: str) -> WorldState:
        """从 SQLite 加载世界，校验 delivery_lag、good_type 枚举、1 政府。"""
```

- [x] 9.2.4 实现 `WorldBuilder` 类（流式 API，替代手写 SQL）：

```python
class WorldBuilder:
    def __init__(self): ...

    def add_good(self, good_id: int, name: str, good_type: str,
                 delivery_lag: int = 1) -> 'WorldBuilder': ...

    def add_firm(self, id: int, cash: float, *,
                 capacity: float = 0, strategy_label: str = "default",
                 inventory: dict[int, float] | None = None,
                 employees: list[int] | None = None) -> 'WorldBuilder': ...

    def add_household(self, id: int, cash: float, *,
                      labor_ask_price: float = 0,
                      is_employed: bool = False,
                      employer_firm_id: int | None = None,
                      inventory: dict[int, float] | None = None,
                      strategy_label: str = "default") -> 'WorldBuilder': ...

    def add_government(self, id: int, cash: float, *,
                       tax_rate: float = 0,
                       unemployment_benefit: float = 0,
                       strategy_label: str = "default") -> 'WorldBuilder': ...

    def build(self) -> WorldState:
        """不写 DB，直接返回 WorldState（用于测试/快速启动）。"""

    def save(self, db_path: str) -> None:
        """持久化到 SQLite。"""
```

`save()` 内部建表：`goods`、`firms`、`firm_inventory`、`firm_employees`、`households`、`household_inventory`、`governments`（7 张表，与当前 `generate_town.py` 的 schema 一致）。覆盖或新建 db 文件。

### 9.3 修改 `core/simulator.py`：集成数据层

- [x] 9.3.1 删除 `_load_world` 静态方法（已迁移到 `WorldLoader`）
- [x] 9.3.2 `Simulator.__init__`：创建 `Sequence()` → `OrderFactory(sequence)`；用 `WorldLoader.load()` 替代 `self._load_world()`
- [x] 9.3.3 修改 `_execute_strategy`：

  - 在调用每个主体策略前，构造 `AgentOrders(my_orders)` 作为 `orders` 参数传入
  - 策略执行完毕后，调用 `orders._consume()` 取出 `{new, cancel, update}` dict
  - 将 dict 传给 `_dispatch_agent_result`（该方法不变，仍收同样的三字段数据结构）

  ```python
  # _execute_strategy 核心逻辑
  for firm in state.firms.values():
      if not firm.is_active:
          continue
      my_orders = firm.outstanding_orders(state.all_orders)
      orders = AgentOrders(my_orders)
      firm_fn(mi, firm, state.goods, orders)
      self._dispatch_agent_result(state, orders._consume())
  ```

- [x] 9.3.4 `_dispatch_agent_result` **不需要改**：仍处理 `{new: [...], cancel: [...], update: [...]}` 三字段。唯一的区别是过去直接收策略返回值，现在收 `orders._consume()` 的输出 — 数据结构一模一样。

- [x] 9.3.5 `_execute_allocation` **不受影响**：分配策略仍返回 `(matched: list[Order], remaining_supply, remaining_demand)`，流程不变

### 9.4 修改 `ese/__init__.py`：新增公开导出

- [x] 9.4.1 新增 `from core.data_layer import WorldBuilder`
- [x] 9.4.2 保持 `Order` 导出（用户遍历 `orders` 时拿到 `Order` 对象）
- [x] 9.4.3 **不需要** 新增 `OrderNew`/`OrderUpdate` 导出（不存在这两个类型）

### 9.5 重写 `examples/generate_town.py`：WorldBuilder API

- [x] 9.5.1 删除所有手写 SQL（`sqlite3.connect`、`CREATE TABLE`、`INSERT`）
- [x] 9.5.2 用 `WorldBuilder` 链式调用定义 town 世界（2 商品、2 企业、10 家庭、1 政府）
- [x] 9.5.3 调用 `builder.save("examples/town_world.db")`

### 9.6 修改 `examples/town.py`：orders.new/cancel/update

- [x] 9.6.1 所有策略删掉 `result = {"new": [], "cancel": [], "update": []}` 和 `return result`
- [x] 9.6.2 原 `result["new"].append(Order(...))` 改为 `orders.new(seller_id=..., ...)`
- [x] 9.6.3 原 `result["cancel"].append("order_5")` 改为 `orders.cancel("order_5")`
- [x] 9.6.4 原 `result["update"].append(Order(...))` 改为 `orders.update("old_id", seller_id=..., ...)`
- [x] 9.6.5 分配策略 `alloc` 中 matched 仍为 `Order(...)`（不受影响），`order_id` 走原有格式
- [x] 9.6.6 import 不变，仍是 `from ese import Engine, OrderSide`

### 9.7 修改 `readme.md`：更新示例代码

- [x] 9.7.1 所有策略示例删除 `result = {...}` 和 `return result`，改用 `orders.new`/`orders.cancel`
- [x] 9.7.2 快速开始 §4.2 世界生成步骤更新为 `WorldBuilder` API 示例

### 9.8 适配测试

- [x] 9.8.1 `core/entities_test.py`：新增 `AgentOrders` 构造 + `__iter__`/`__len__` + `new`/`cancel`/`update` 记录意图 + `_consume` 返回正确三字段结构 测试
- [x] 9.8.2 `core/data_layer_test.py`（新增）：测试 `OrderFactory.from_params`/`from_update` ID 注入；测试 `WorldBuilder.build()` 返回正确的 `WorldState`；测试 `WorldBuilder.save()` + `WorldLoader.load()` 往返
- [x] 9.8.3 `core/simulator_test.py`：测试辅助函数的策略改为 `orders.new(...)` 风格（不 return）；`_dispatch_agent_result` 测试不需要改（输入格式不变）
- [x] 9.8.4 `core/ledger_test.py` / `core/clearing_house_test.py` / `core/reporter_test.py` / `core/engine_test.py`：这些测试不涉及策略返回值格式，检查是否有直接构造 `Order(order_id=...)` 的地方需要适配
- [x] 9.8.5 验证：`uv run pytest core/ -v` 全绿

### 9.9 端到端验证

- [x] 9.9.1 重新生成 town 世界：`uv run python examples/generate_town.py` → 输出 `town_world.db`
- [x] 9.9.2 运行 town 模拟：`uv run python examples/town.py` → 正常跑完 50 tick，输出 CSV/图表
- [x] 9.9.3 `uv run pytest core/ -v` 全绿

---

## 依赖关系

```
1(entities) ─→ 2(ledger+noise) ─→ 3a(clearing part1) ─→ 3b(clearing part2) ─→ 4(reporter) ─→ 5(simulator kernel) ─→ 6(strategies) ─→ 7(obs→MI refactor) ─→ 8(registry→Engine) ─→ 9(data layer)
                                                                                                                                                                                                             │
                                                                                                                                                                                                             └─→ 10(labels) ─→ 11(market) ─→ 12(apply dispatch) ─→ 13(examples+readme)
```

每轮严格按顺序执行，前一轮全部打勾才进入下一轮。

---

## 10. labels 字段迁移：`strategy_label: str` → `labels: List[str]`

**产出**：修改 `core/entities.py`、`core/data_layer.py`、`core/engine.py`、`core/simulator.py`；适配 `core/*_test.py`；修改 `examples/generate_town.py`、`examples/town.py`；重新生成 `town_world.db`、`config/seed_world.db`

**依据**：`docs/strategy-design.md` §labels 字段

**动机**：

- 当前 `strategy_label` 是单字符串，一个实体只能匹配一个 `apply()` 调用
- 新设计改为 `labels: List[str]`，一个企业可以同时属于 `["steel", "tech"]`，两个 label 的 `apply()` 都能命中它
- `apply()` 匹配规则：`label in entity.labels`
- 字段名从 `strategy_label` 改为 `labels`（去掉冗余的 strategy 前缀），更精准

**DB 存储格式**：逗号分隔字符串，如 `"steel,tech"`。加载时 `split(",")` 还原为 list，保存时 `",".join(labels)`。

---

### 10.1 修改 `core/entities.py`

- [x] 10.1.1 `Firm` dataclass 第 45 行：`strategy_label: str = "default"` → `labels: List[str] = field(default_factory=lambda: ["default"])`
- [x] 10.1.2 `Household` dataclass 第 68 行：同上
- [x] 10.1.3 `Government` dataclass 第 89 行：同上

---

### 10.2 修改 `core/data_layer.py` — WorldLoader.load()

修改三处 SQL 查询和对应的加载逻辑（列名 `strategy_label` → `labels`，存为逗号分隔字符串，解析为 list）：

- [x] 10.2.1 行 87：`SELECT id, cash, capacity, collateral, is_active, labels FROM firms`（列名改为 labels）
- [x] 10.2.2 行 100-101：`if "labels" in cols: kwargs["labels"] = row_dict["labels"].split(",")`（读取后 split 为 list）
- [x] 10.2.3 行 118-119：`SELECT ... labels FROM households`
- [x] 10.2.4 行 133-134：`if "labels" in cols: kwargs["labels"] = row_dict["labels"].split(",")`
- [x] 10.2.5 行 145-146：`SELECT ... labels FROM governments`
- [x] 10.2.6 行 159-160：`if "labels" in cols: kwargs["labels"] = row_dict["labels"].split(",")`

---

### 10.3 修改 `core/data_layer.py` — WorldBuilder

- [x] 10.3.1 `add_firm()` 签名行 222：`strategy_label: str = "default"` → `labels: List[str] = None`，方法体内 `if labels is None: labels = ["default"]`
- [x] 10.3.2 `add_firm()` 行 230：`Firm(... strategy_label=strategy_label)` → `Firm(... labels=labels)`
- [x] 10.3.3 `add_household()` 签名行 252：同上
- [x] 10.3.4 `add_household()` 行 260：同上
- [x] 10.3.5 `add_government()` 签名行 276：同上
- [x] 10.3.6 `add_government()` 行 283：同上

---

### 10.4 修改 `core/data_layer.py` — WorldBuilder.save() DDL + INSERT

- [x] 10.4.1 行 326（firms DDL）：`strategy_label TEXT NOT NULL DEFAULT 'default'` → `labels TEXT NOT NULL DEFAULT 'default'`
- [x] 10.4.2 行 349（households DDL）：同上
- [x] 10.4.3 行 365（governments DDL）：同上
- [x] 10.4.4 行 376（firms INSERT）：列名 `strategy_label` → `labels`，值 `f.strategy_label` → `",".join(f.labels)`
- [x] 10.4.5 行 395-396（households INSERT）：列名 `strategy_label` → `labels`，值 `hh.strategy_label` → `",".join(hh.labels)`
- [x] 10.4.6 行 413-414（governments INSERT）：列名 `strategy_label` → `labels`，值 `gov.strategy_label` → `",".join(gov.labels)`

---

### 10.5 修改 `core/engine.py`

- [x] 10.5.1 `_Slot.use()` 方法行 27：签名 `use(self, label: str, mi, entity, goods, orders)` → 保留（仅为兼容过渡，Round 12 会被删除）
- [x] 10.5.2 `_Slot.label()` 装饰器行 19-24：保留（仅为兼容过渡，Round 12 会被删除）
- [x] 10.5.3 注意：`Engine` 类本身不做 labels 相关变更

---

### 10.6 修改 `core/simulator.py`

- [x] 10.6.1 行 140-141：`my_orders = firm.outstanding_orders(state.all_orders)` 不变，无需修改（引擎遍历逻辑 Round 10 不动）
- [x] 10.6.2 无需修改 `_execute_strategy`（当前仍是 per-entity 遍历，只是字段名改了，Round 12 才重写）

---

### 10.7 修改 `core/simulator_test.py`

- [x] 10.7.1 行 47（测试 DB schema）：`strategy_label TEXT` → `labels TEXT`
- [x] 10.7.2 行 67（测试 DB schema）：同上
- [x] 10.7.3 行 81（测试 DB schema）：同上
- [x] 10.7.4 所有构造 `Firm(... strategy_label=...)` 的测试 → `Firm(... labels=["farm"])`
- [x] 10.7.5 所有 `assert firm.strategy_label == "farm"` → `assert "farm" in firm.labels`

---

### 10.8 修改 `core/data_layer_test.py`

- [x] 10.8.1 行 78：`strategy_label="farm"` → `labels=["farm"]`
- [x] 10.8.2 行 89：`strategy_label="default"` → `labels=["default"]`
- [x] 10.8.3 行 103：`assert ws.firms[1].strategy_label == "farm"` → `assert "farm" in ws.firms[1].labels`
- [x] 10.8.4 行 113：同上风格修改
- [x] 10.8.5 行 146, 154：同上
- [x] 10.8.6 行 175, 178：`strategy_label == "farm"` → `"farm" in labels`
- [x] 10.8.7 行 225-236：测试名称和默认值断言改为 `labels == ["default"]`

---

### 10.9 修改 `core/engine_test.py`

- [x] 10.9.1 所有测试中构造的 Firm/Household/Government 实例 `strategy_label="..."` → `labels=["..."]`
- [x] 10.9.2 所有 `assert entity.strategy_label == ...` → `assert "..." in entity.labels`

---

### 10.10 修改 `core/entities_test.py`

- [x] 10.10.1 所有 Firm/Household/Government 构造中 `strategy_label=...` → `labels=[...]`
- [x] 10.10.2 默认值测试改为 `assert firm.labels == ["default"]`

---

### 10.11 修改 `core/reporter_test.py`

- [x] 10.11.1 如果有直接构造实体实例的地方（Household 等），`strategy_label` → `labels`（该文件大概率不涉及——Reporter 不读 strategy_label）

---

### 10.12 修改 `examples/generate_town.py`

- [x] 10.12.1 行 21：`strategy_label="farm"` → `labels=["farm"]`
- [x] 10.12.2 行 29：`strategy_label="workshop"` → `labels=["workshop"]`

---

### 10.13 修改 `examples/town.py`

- [x] 10.13.1 行 33：`ese.firm.use(firm.strategy_label, ...)` → `ese.firm.use(firm.labels[0], ...)`（取第一个 label 作为分发目标，仅过渡；Round 13 会重写整个文件）

---

### 10.14 重新生成数据库

- [x] 10.14.1 运行 `uv run python examples/generate_town.py` 重新生成 `examples/town_world.db`
- [x] 10.14.2 如果有 `config/seed_world.db`，也重新生成

---

### 10.15 验证

- [x] 10.15.1 `uv run pytest core/ -v` 全绿
- [x] 10.15.2 `uv run python examples/town.py` → 正常跑完 50 tick，输出 CSV/图表

---

## 11. market 命名空间迁移：supply_pool/demand_pool/ledger → market.supply/demand/history

**产出**：修改 `core/entities.py`、`core/simulator.py`、`core/clearing_house.py`、`core/market_intelligence.py`、`core/reporter.py`、`core/engine.py`、`core/ledger.py`；适配全部 `core/*_test.py`

**依据**：`docs/strategy-design.md` §market 命名空间

**动机**：

- 三个散落的变量名（`supply_pool`、`demand_pool`、`ledger`）对用户不直观
- 统合在 `market` 对象下，一个入口查完所有市场数据：`market.supply`、`market.demand`、`market.history`
- 语义对称，supply/demand 天然对应卖和买
- `ledger.py` 中的 `Ledger` 类重命名为 `TradeHistory` 并入 `market` 体系

**设计**：
- 新增 `MarketData` 类（或在 `WorldState` 上直接挂 `market` 属性），持有 `supply: List[Order]`、`demand: List[Order]`、`history: TradeHistory`
- `TradeHistory` 是原 `Ledger` 类的重命名，接口不变（`record_trade`、`get_trades_by_agent`、`get_avg_price_by_good`、`get_all_recent_prices`）
- `WorldState` 字段 `supply_pool`、`demand_pool` 删除（移入 `market.supply`、`market.demand`）
- 全局替换所有代码中对 `state.supply_pool`、`state.demand_pool`、`self.ledger` 的引用

---

### 11.1 修改 `core/ledger.py`：Ledger → TradeHistory

- [x] 11.1.1 `class Ledger` → `class TradeHistory`（仅改名，接口完全不变）
- [x] 11.1.2 文件名不重命名（避免 touch 太多 import），`core/ledger.py` 保持原文件名

---

### 11.2 修改 `core/entities.py` — WorldState 字段

- [x] 11.2.1 行 198-199：删除 `supply_pool: List[Order]` 和 `demand_pool: List[Order]` 两个字段
- [x] 11.2.2 在 `WorldState` 上新增 `market` 属性。由于 `WorldState` 是 `@dataclass`，在 `__post_init__` 中初始化：
  ```python
  @dataclass
  class WorldState:
      tick: int
      firms: Dict[int, Firm] = ...
      ...
      # 新增
      market: "MarketData" = field(default=None)  # __post_init__ 中初始化

      def __post_init__(self):
          if self.market is None:
              self.market = MarketData()
  ```
- [x] 11.2.3 在 `entities.py` 底部新增 `MarketData` 类：
  ```python
  @dataclass
  class MarketData:
      supply: List[Order] = field(default_factory=list)
      demand: List[Order] = field(default_factory=list)
      history: "TradeHistory" = field(default_factory=lambda: _get_trade_history())
  ```
  **⚠️ 循环导入处理**：`ledger.py` 已有 `from core.entities import Order`。若 `entities.py` 顶层 `from core.ledger import TradeHistory` 会造成循环导入。解决方案：
  - `MarketData.history` 字段用**字符串标注** `"TradeHistory"` + `field(default_factory=...)` 延迟导入
  - 在 `entities.py` 定义 `_get_trade_history()` 辅助函数，内部局部 `from core.ledger import TradeHistory`
  - 不在 `entities.py` 顶层 import `TradeHistory`，仅用在类型标注的字符串引用和延迟 factory 中
- [x] 11.2.4 `ese/__init__.py` 新增 `from core.entities import MarketData`

---

### 11.3 修改 `core/simulator.py`：全局替换 supply_pool / demand_pool / ledger

**Simulator.__init__：**

- [x] 11.3.1 行 8：`from core.ledger import Ledger` → `from core.ledger import TradeHistory`
- [x] 11.3.2 行 17：`self.ledger = Ledger()` → 删除这行，不再单独持有 ledger
- [x] 11.3.3 **⚠️ 调整初始化顺序**：`self.state` 必须移到 `self.clearing` 之前创建，因为 `ClearingHouse` 构造函数需要 `self.state.market.history`：
  ```python
  # 新顺序（仅列出有改动的行）：
  self.config = self._load_config(config_path)
  self.noise = InformationFriction(...)
  self.reporter = Reporter()
  self._id_seq = Sequence()
  self.order_factory = OrderFactory(self._id_seq)
  self.state = WorldLoader.load(world_db_path)       # ← 移到前面
  self.clearing = ClearingHouse(                     # ← 此时 self.state 已存在
      ledger=self.state.market.history, ...)
  self.order_expire_ticks = ...
  self.mi_builder = MarketIntelligenceBuilder(...)
  self.mi = self.mi_builder.build(self.state, self.state.market.history)
  self._reg = strategy_registry
  ```
  > **若不调整顺序，`ClearingHouse(ledger=self.state.market.history, ...)` 会在 `self.state` 赋值前执行，触发 `AttributeError: 'Simulator' object has no attribute 'state'`。**
- [x] 11.3.4 行 32：`self.mi_builder.build(self.state, self.ledger)` → `self.mi_builder.build(self.state, self.state.market.history)`

**tick() 方法：**

- [x] 11.3.5 行 69：`self.mi_builder.build(state, self.ledger)` → `self.mi_builder.build(state, state.market.history)`

**run() 方法：**

- [x] 11.3.6 行 77：`self.reporter.snapshot(self.state, self.ledger)` → `self.reporter.snapshot(self.state, self.state.market.history)`

**_add_new_order() 方法：**

- [x] 11.3.7 行 201：`state.supply_pool.append(order)` → `state.market.supply.append(order)`
- [x] 11.3.8 行 203：`state.demand_pool.append(order)` → `state.market.demand.append(order)`

**_cancel_order() 方法：**

- [x] 11.3.9 行 212：`self.ledger.record_trade(order)` → `state.market.history.record_trade(order)`
- [x] 11.3.10 行 214-217：`if order in state.supply_pool: state.supply_pool.remove(order)` → `if order in state.market.supply: state.market.supply.remove(order)`
- [x] 11.3.11 行 216-217：`state.demand_pool` → `state.market.demand`

**_execute_allocation() 方法：**

- [x] 11.3.12 行 228-229：`list(state.supply_pool)` → `list(state.market.supply)`，`list(state.demand_pool)` → `list(state.market.demand)`
- [x] 11.3.13 行 234-235：`state.supply_pool = remaining_supply` → `state.market.supply = remaining_supply`，`state.demand_pool = remaining_demand` → `state.market.demand = remaining_demand`
- [x] 11.3.14 行 244：`self.ledger.record_trade(order)` → `state.market.history.record_trade(order)`

**_execute_strategy() 方法：**

- [x] 11.3.15 行 140-143：引擎内部遍历逻辑不变（Round 10 的 per-entity 循环不改）
- [x] 11.3.16 但仍需确保 `firm.outstanding_orders(state.all_orders)` 正确工作——该函数用 `outstanding_order_ids` 在 `all_orders` 中查找，不依赖 pool 命名

---

### 11.4 修改 `core/clearing_house.py`

- [x] 11.4.1 行 5：`from core.ledger import Ledger` → `from core.ledger import TradeHistory`
- [x] 11.4.2 行 11：`ledger: Ledger` → `ledger: TradeHistory`
- [x] 11.4.3 行 15：`self.ledger = ledger` → `self.ledger = ledger`（变量名保持 self.ledger，不变——因为 ClearingHouse 内部可以继续叫 ledger，它不暴露给用户）
- [x] 11.4.4 全文搜索 `state.supply_pool` 和 `state.demand_pool`：
  - `liquidate_firm()` 中如果有池操作 → `state.market.supply` / `state.market.demand`
  - `expire_stale_orders()` 中遍历的池 → `state.market.supply` / `state.market.demand`
- [x] 11.4.5 全文搜索 `self.ledger.record_trade`：不变（清除器内部仍叫 `self.ledger`，只是对象类型变成了 `TradeHistory`）

---

### 11.5 修改 `core/market_intelligence.py`

- [x] 11.5.1 行 6：`from core.ledger import Ledger` → `from core.ledger import TradeHistory`
- [x] 11.5.2 所有方法签名中的 `ledger: Ledger` → `ledger: TradeHistory`
- [x] 11.5.3 行 42-43：`self._aggregate_pool(state.supply_pool, ...)` → `self._aggregate_pool(state.market.supply, ...)`
- [x] 11.5.4 行 43-44：`state.demand_pool` → `state.market.demand`

---

### 11.6 修改 `core/reporter.py`

- [x] 11.6.1 行 35：类型标注 `ledger: "Ledger"` → `ledger: "TradeHistory"`（字符串引用不变因为 ledger.py 不重命名）
- [x] 11.6.2 行 75：`snapshot(state, ledger)` 签名中类型标注同上

---

### 11.7 修改 `core/data_layer.py` — WorldLoader.load() 和 WorldBuilder.build()

- [x] 11.7.1 `WorldLoader.load()` 行 185-186：构造 `WorldState(... supply_pool=[], demand_pool=[], ...)` → **删除 `supply_pool` 和 `demand_pool` 参数**。由于 `WorldState.__post_init__` 会在无 market 时自动创建 `MarketData()`，load 方法不需要手动传入。
  > **⚠️ 如果忘记删除这两个参数，会报 `TypeError: __init__() got an unexpected keyword argument 'supply_pool'`，因为 dataclass 字段已删除。**
- [x] 11.7.2 `WorldBuilder.build()` 行 287-294：同上删除 `supply_pool=[], demand_pool=[]`，同理会触发 TypeError

---

### 11.8 修改 `core/engine.py`

- [x] 11.8.1 全部不变——Engine 不直接引用 supply_pool / demand_pool / ledger

---

### 11.9 修改 `ese/__init__.py`

- [x] 11.9.1 `from core.ledger import Ledger` → 删除（不再公开导出旧的 Ledger 类名）
- [x] 11.9.2 保持现有导出：`Engine`, `Firm`, `Good`, `Government`, `Household`, `Order`, `OrderSide`, `WorldState`, `MarketIntelligence`, `WorldBuilder`, `MarketData`

---

### 11.10 适配所有 `core/*_test.py`

- [x] 11.10.1 `core/ledger_test.py`：所有 `Ledger()` → `TradeHistory()`，所有 `from core.ledger import Ledger` → `from core.ledger import TradeHistory`
- [x] 11.10.2 `core/clearing_house_test.py`：全局替换 `state.supply_pool` → `state.market.supply`，`state.demand_pool` → `state.market.demand`，`Ledger()` → `TradeHistory()`
- [x] 11.10.3 `core/simulator_test.py`：全局同上替换
- [x] 11.10.4 `core/reporter_test.py`：`Ledger()` → `TradeHistory()`
- [x] 11.10.5 `core/market_intelligence_test.py`（如独立文件）或 `simulator_test.py` 中的 MI 测试：同上
- [x] 11.10.6 `core/entities_test.py`：测试 `MarketData` 构造，测试 `WorldState.__post_init__` 自动创建 `market`
- [x] 11.10.7 `core/data_layer_test.py`：`supply_pool` / `demand_pool` 相关测试适配

---

### 11.11 验证

- [x] 11.11.1 `uv run pytest core/ -v` 全绿
- [x] 11.11.2 `uv run python examples/town.py` → 正常跑完 50 tick

---

## 12. apply() + 宏函数调度：引擎改为每 slot 调一次宏函数

**产出**：修改 `core/simulator.py`、`core/engine.py`、`core/_registry.py`；适配 `core/engine_test.py`、`core/simulator_test.py`

**依据**：`docs/strategy-design.md` §apply() 核心语义

**动机**：

- 当前引擎在 `_execute_strategy` 中按 F→H→G 顺序，**逐实体**调用注册的 primary 策略函数（per-entity 遍历）
- 新设计：引擎改为每个 slot 只调一次宏函数，传参 `(mi, goods)`，不在引擎层遍历实体
- 迭代权交给用户，在宏函数内部通过 `apply()` 分发到实体
- `apply(label, leaf_fn, **params)` 内部做：筛选实体（`label in entity.labels`）→ 构造 AgentOrders → 调 leaf_fn → 汇总返回值
- 叶子函数是普通 Python 函数，不注册、不装装饰器，由 `apply()` 直接传入实体实例

**宏函数新签名：**

| 旧签名 | 新签名 |
|--------|--------|
| `firm_fn(mi, entity, goods, orders)` | `firm_macro(mi, goods)` |
| `hh_fn(mi, entity, goods, orders)` | `hh_macro(mi, goods)` |
| `gov_fn(mi, entity, goods, orders)` | `gov_macro(mi, goods)` |

**`apply()` 完整实现（位于 `engine._Slot`）：**

依赖注入说明：`_Slot.__init__` 除 `_get_entities_fn` 外，还需额外接收 `simulator: Simulator` 引用，从而在 `apply()` 内部取到 `state`、`order_factory`、`_dispatch_agent_result` 三个关键依赖。

```python
def apply(self, label: str, leaf_fn, **params):
    state = self._sim.state                     # ← 通过 simulator 引用取 state
    results = []
    for entity in self._get_entities():
        if hasattr(entity, 'is_active') and not entity.is_active:
            continue                            # 跳过已退出实体（Firm）
        if label not in entity.labels:
            continue                            # label 不匹配则跳过
        my_orders = entity.outstanding_orders(state.all_orders)
        orders = AgentOrders(my_orders, self._sim.order_factory)  # ← 通过 simulator 取 order_factory
        result = leaf_fn(entity, orders, **params)
        results.append(result)
        self._sim._dispatch_agent_result(state, orders._consume())  # ← 通过 simulator 调 dispatch
    return results
```

---

### 12.1 修改 `core/_registry.py`：去掉 labeled 字典

- [ ] 12.1.1 `_Slot` 类：
  - 删除 `self.labeled: Dict[str, Callable] = {}`（行 8）
  - 删除 `set_labeled(label, func)` 方法（行 13-14）
  - `get()` 方法简化为 `def get(self) -> Optional[Callable]: return self.primary`（去掉 label 参数）
- [ ] 12.1.2 `_StrategyRegistry` 类：
  - 删除 `set_labeled(slot, label, func)` 方法（行 35-36）
  - `get(slot, label=None)` → `get(slot)`（去掉 label 参数，返回 primary）

---

### 12.2 修改 `core/engine.py`：去掉 label()/.use()，新增 apply()

- [ ] 12.2.1 `_Slot` 类：
  - 删除 `.label(label)` 装饰器方法（行 19-24）
  - 删除 `.use(label, mi, entity, goods, orders)` 分发方法（行 26-35）
  - `__init__` 签名改为 `__init__(self, registry, slot_name, get_entities_fn, simulator)`：
    - `get_entities_fn: Callable` — 闭包，返回该 slot 类型的实体列表（由 Engine 注入 lambda）
    - `simulator: Simulator` — 提供 `state`（WorldState）、`order_factory`（OrderFactory）、`_dispatch_agent_result()` 三个关键依赖
  - 新增 `apply(label, leaf_fn, **params)` 方法，完整实现见上文"动机"节
- [ ] 12.2.2 `Engine.__init__` 创建 `_Slot` 时注入两个依赖：
  ```python
  self.firm = _Slot(self._registry, "firm",
      get_entities_fn=lambda: list(self._simulator.state.firms.values()),
      simulator=self._simulator)

  self.household = _Slot(self._registry, "household",
      get_entities_fn=lambda: list(self._simulator.state.households.values()),
      simulator=self._simulator)

  # government 只有一个实例，直接取（gov 宏函数内手动访问 state.governments.values()）
  self.government = _Slot(self._registry, "government",
      get_entities_fn=lambda: list(self._simulator.state.governments.values()),
      simulator=self._simulator)
  ```
  > **注意**：`get_entities_fn` 用 `list()` 包裹 `dict_values` 视图，确保多次迭代结果一致（虽然 Round 10-12 不会在迭代中增删实体，但 `list()` 是安全惯例）。
- [ ] 12.2.3 `_AllocationSlot` 类：
  - `__init__` 改为 `__init__(self, registry, get_entities_fn, simulator)`，不再固定 `slot_name="allocation"`
  - 其余保持不变（`.pricing` 属性、`super().__init__` 委托）
- [ ] 12.2.4 `Engine.__init__` 创建 `_AllocationSlot` 时注入：
  ```python
  self.allocation = _AllocationSlot(self._registry,
      get_entities_fn=lambda: None,  # allocation slot 不需要实体迭代
      simulator=self._simulator)
  ```

---

### 12.3 修改 `core/simulator.py`：重写 `_execute_strategy`

- [ ] 12.3.1 删除当前逐实体遍历的 `_execute_strategy` 方法（行 134-159）
- [ ] 12.3.2 新 `_execute_strategy(self, mi, state)`：
  ```python
  def _execute_strategy(self, mi, state):
      # Firm 宏函数
      firm_fn = self._reg.get("firm") if self._reg else None
      if firm_fn is not None:
          firm_fn(mi, state.goods)  # 宏函数签名: (mi, goods)

      # Household 宏函数
      hh_fn = self._reg.get("household") if self._reg else None
      if hh_fn is not None:
          hh_fn(mi, state.goods)

      # Government 宏函数
      gov_fn = self._reg.get("government") if self._reg else None
      if gov_fn is not None:
          gov_fn(mi, state.goods)
  ```
  **关键**：引擎不再构造 AgentOrders、不再遍历实体、不再调用 `_dispatch_agent_result`。这些全部由 `apply()` 在宏函数内部完成。
- [ ] 12.3.3 保留 `_dispatch_agent_result` 方法不变（`apply()` 内部调用它）
- [ ] 12.3.4 保留 `_add_new_order` 和 `_cancel_order` 方法不变

---

### 12.4 适配 `core/engine_test.py`

- [ ] 12.4.1 测试 `_Slot.__call__` 注册仍有效（primary 策略注册）
- [ ] 12.4.2 删除所有测试 `.label()` 的测试用例
- [ ] 12.4.3 删除所有测试 `.use()` 的测试用例
- [ ] 12.4.4 新增测试 `_Slot.apply()`：注入假实体列表 → 调 apply("tag", fn) → 验证 fn 被调用、返回值正确汇总
- [ ] 12.4.5 新增测试 `apply()` 在 `label in entity.labels` 不匹配时跳过对应实体

---

### 12.5 适配 `core/simulator_test.py`

- [ ] 12.5.1 所有测试用例中的 `_execute_strategy` 调用预期行为更新：
  - 注册一个宏函数（收 `(mi, goods)` 参数），宏函数内部调 `apply()`
  - 宏函数不再接收 entity 参数
- [ ] 12.5.2 删除所有依赖于逐实体调用策略的旧测试断言
- [ ] 12.5.3 新增测试：分配策略调用不受影响（`_execute_allocation` 逻辑不变）

---

### 12.6 验证

- [ ] 12.6.1 `uv run pytest core/ -v` 全绿
- [ ] 12.6.2 不需要端到端跑 town.py（Round 12 结束时 town.py 还是旧写法 = 会崩溃，属于预期，Round 13 修复）

---

## 13. examples + readme 重写：适配新的 apply() 架构

**产出**：重写 `examples/town.py`；修改 `examples/generate_town.py`（labels 最终确认）；修改 `readme.md`；重新生成数据库

**依据**：`docs/strategy-design.md` §1.市场

**动机**：

- Round 12 改造完成后，引擎只调宏函数，旧的 `ese.firm.use()` / `@ese.firm.label()` 写法全部失效
- `town.py` 必须重写为宏函数 + `apply()` + 普通叶子函数的风格
- `readme.md` 的代码示例和文档说明同步更新
- 端到端验证整个改造链路

---

### 13.1 重写 `examples/town.py`

**新的文件结构：**

- [ ] 13.1.1 初始化：`ese = Engine(...)` 不变
- [ ] 13.1.2 叶子函数（普通 Python 函数，无装饰器）：
  ```python
  def farm_decide(firm, orders):
      # 生产：1 工具 → 5 食物
      if firm.inventory.get(2, 0) >= 1.0:
          firm.inventory[2] -= 1.0
          firm.inventory[1] = firm.inventory.get(1, 0) + 5.0
      # 挂单卖食物
      if firm.inventory.get(1, 0) > 2.0:
          orders.new(seller_id=firm.id, buyer_id=0, good_id=1, ...)
      # 采购工具
      if firm.cash > 50 and firm.inventory.get(2, 0) < 10:
          orders.new(seller_id=0, buyer_id=firm.id, good_id=2, ...)

  def workshop_decide(firm, orders):
      # 类似，2 食物 → 3 工具
      ...

  def household_spend(hh, orders):
      budget = hh.cash * 0.2
      if budget < 0.5:
          return
      orders.new(seller_id=0, buyer_id=hh.id, good_id=1, ...)
      orders.new(seller_id=0, buyer_id=hh.id, good_id=2, ...)
  ```
- [ ] 13.1.3 宏函数（带 `@ese.firm` 等装饰器）：
  ```python
  @ese.firm
  def market(mi, goods):
      ese.firm.apply("farm", farm_decide)
      ese.firm.apply("workshop", workshop_decide)

  @ese.household
  def consumption(mi, goods):
      ese.household.apply("default", household_spend)

  @ese.government
  def minimal_gov(mi, goods):
      gov = list(ese._simulator.state.governments.values())[0]
      # 税率和失业金在种子数据库已设定，不动
  ```
- [ ] 13.1.4 分配和定价策略：保持不变（`@ese.allocation`、`@ese.allocation.pricing` 不变）
- [ ] 13.1.5 删除所有 `@ese.firm.label(...)` 和 `ese.firm.use(...)` 调用
- [ ] 13.1.6 运行和输出：`snapshots = ese.run(n_ticks=50)` + `ese.save(...)` 不变

---

### 13.2 修改 `examples/generate_town.py`

- [ ] 13.2.1 确认 `labels=["farm"]` 和 `labels=["workshop"]` 参数正确
- [ ] 13.2.2 Household 不指定 labels（默认 `["default"]`），`apply("default", fn)` 命中
- [ ] 13.2.3 重新生成 `dir/town_world.db`：`uv run python examples/generate_town.py`

---

### 13.3 重写 `readme.md`

- [ ] 13.3.1 §2.5 "策略的调度机制" 整段重写：
  - 删除 `@ese.firm.label()` 和 `ese.firm.use()` 相关说明
  - 改为宏函数 + `apply()` + 叶子函数的说明
  - 更新代码示例
- [ ] 13.3.2 §4.4 策略编写示例全部重写为宏函数 + apply 风格：
  ```python
  # 叶子：无装饰器的普通函数
  def farm(firm, orders):
      if firm.inventory.get(2, 0) >= 1.0:
          firm.inventory[2] -= 1.0
          firm.inventory[1] = firm.inventory.get(1, 0) + 5.0
      orders.new(seller_id=firm.id, buyer_id=0, good_id=1, ...)

  def workshop(firm, orders):
      ...

  # 宏函数
  @ese.firm
  def market(mi, goods):
      ese.firm.apply("farm", farm)
      ese.firm.apply("workshop", workshop)
  ```
- [ ] 13.3.3 删除所有 `@ese.firm.label("farm")` 和 `@ese.household.label(...)` 示例
- [ ] 13.3.4 §1 "企业（Firm）" 描述：`strategy_label` → `labels`
- [ ] 13.3.5 分配策略和定价策略相关描述保持不变
- [ ] 13.3.6 §4.2 世界生成示例中 `strategy_label="farm"` → `labels=["farm"]`
- [ ] 13.3.7 ALL references to `strategy_label` → `labels`

---

### 13.4 端到端验证

- [ ] 13.4.1 `uv run pytest core/ -v` 全部 170+ 测试通过
- [ ] 13.4.2 `uv run python examples/generate_town.py` → 正常生成 town_world.db
- [ ] 13.4.3 `uv run python examples/town.py` → 正常跑完 50 tick，输出 CSV/图表
- [ ] 13.4.4 检查 `examples/results/town_results.csv` 包含 50 行数据，`town_results.png` 包含 gini、unemployment、engel、active_firms 四个子图