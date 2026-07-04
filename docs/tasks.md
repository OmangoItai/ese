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
- [x] 1.10 验证：`python -m pytest core/entities_test.py -v` 全绿

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
- [x] 2.11 验证：`python -m pytest core/ledger_test.py core/noise_test.py -v` 全绿

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
- [x] 3a.14 验证：`python -m pytest core/clearing_house_test.py -v` 全绿

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
- [x] 3b.18 验证：`python -m pytest core/clearing_house_test.py -v` 全绿

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
- [x] 4.11 验证：`python -m pytest core/reporter_test.py -v` 全绿

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
- [x] 5.16 验证：`python -m pytest core/simulator_test.py -v` 全绿

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
- [x] 6.18 验证：`python -m pytest core/simulator_test.py -v` 全绿

---

## 依赖关系

```
1(entities) ─→ 2(ledger+noise) ─→ 3a(clearing part1) ─→ 3b(clearing part2) ─→ 4(reporter) ─→ 5(simulator kernel) ─→ 6(strategies)
```

每轮严格按顺序执行，前一轮全部打勾才进入下一轮。
