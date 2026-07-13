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
```

每轮严格按顺序执行，前一轮全部打勾才进入下一轮。