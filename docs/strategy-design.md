# 策略架构设计（Strategy Architecture）

> **前置说明 — 给新 AI 会话**
>
> 本文档描述的是**尚未实施的架构升级方案**。
>
> **现状**：引擎在 `_execute_strategy` 中遍历每个 Firm/Household/Government，逐实体调用注册的策略函数。传参 `(mi, entity, goods, orders)`。迭代权在引擎。
>
> **目标**：引擎改为每个 slot 只调一次宏函数，传参 `(mi, goods)`。迭代权交给用户，用户在宏函数内部通过 `apply()` 分发到实体。
>
> **`labels` 字段**：
> - Firm、Household、Government 均新增 `labels: List[str]` 字段（默认 `["default"]`），替代旧的 `strategy_label: str`。
> - 一个实体可以有多个标签（如 `["steel", "tech"]`），表示它同时属于多个策略分组。
> - `apply(label, fn)` 匹配规则：`label in entity.labels`。只要实体标签列表中包含该 label 就算命中。
>
> **`market` 命名空间**：
> - 三个市场数据池统合在 `market` 对象下，一个入口查完所有市场数据：
>   - `market.supply` — 当前卖单（替旧 `supply_pool`）
>   - `market.demand` — 当前买单（替旧 `demand_pool`）
>   - `market.history` — 历史成交记录（替旧 `ledger`）
> - `market.history` 由引擎自动维护，每笔成交自动记录，无需任何主体上报。
> - MI 的宏观指标从 `market.history` 聚合生成。
> - A 矩阵拟合从 `market.history` 做部门间流量聚合。
>
> **`apply()` 核心语义**：
> - `ese.firm.apply(label, leaf_fn, **params)` — 找出所有 `label in labels` 的 Firm，为每个构造 `AgentOrders`，调用 `leaf_fn`，汇总返回值后返回一个 list。
> - `ese.household.apply(label, leaf_fn, **params)` — 同上。
> - 叶子函数直接接收**实体实例本身**（Firm 或 Household 对象）作为上下文，可读取真实属性（capacity、inventory 等），自行决定上报多少、下单多少。
> - 叶子函数是普通 Python 函数，无需装饰器，由 `apply()` 直接传入实例。
> - 叶子函数可以调用 `orders.new()` 创建新订单、`return` 数据给宏函数，**两者不互斥**（可以一边报产能一边下单）。
> - `apply()` **不消费 orders**。所有 AgentOrders 被注册到引擎的内部队列，宏函数返回后由引擎统一处理。
>
> **三种经济制度的核心区别**：引擎不变、结算器不变、破产规则不变。区别仅在于宏函数怎么用 `apply()` ——市场只分发不下沉返回值，计划有多轮往返（摸底→修订→执行），混合是基线市场加条件触发计划式干预。

---

## MI 与 market 定位

策略层有两类数据基础设施，职责严格分离：

### market — 市场数据统一入口

- `market.supply`：当前挂存的卖单。叶子函数和 AllocationPolicy 可读，用于报价决策和配对。
- `market.demand`：当前挂存的买单。同上。
- `market.history`：历史成交记录，引擎自动维护，无需主体上报。每笔成交记录（谁卖谁、商品、数量、价格、Tick）。
- 消费者：计划局的 A 矩阵拟合（部门间流量聚合）、MI 的宏观指标计算。
- 叶子函数和宏函数均可查询，但叶子通常不直接使用 `market.history`（宏函数处理全局分析）。

### MarketIntelligence (MI) — 宏观反馈

- 每 Tick 由引擎从 `market.history` 聚合生成，经 InformationFriction 加噪。
- 职责：提供 gini、失业率、恩格尔系数、行业均价等宏观统计指标。
- 消费者：政府财政策略（失业率→调整福利）、家庭消费策略（恩格尔→调整支出结构）、混合制中的触发条件。
- **不做的事**：不提供企业级数据流（那是 `market.history` 的活）、不充当计划局的数据中枢。

### 实体实例 — 产能/库存的 ground truth

- Firm、Household、Government 均持有 `labels: List[str]` 字段（默认 `["default"]`），用于 `apply()` 选中。
- `apply()` 将真实的 Firm / Household 实例传入叶子函数，不经 MI 中转。
- 叶子直接读取 `entity.capacity`、`entity.inventory`、`entity.cash`，自行决定产出决策和上报数据。
- 企业注水或瞒报是策略行为，不是噪声模块的责任。

### 关键规则

- **A 矩阵拟合**走 `market.history`，不走 MI。
- **调查反馈**只返回 {capacity, inventory}，不含交易数据（国家自己从 `market.history` 查）。
- **MI 不存储任何企业个体数据**，没有 `firm_reports` / `household_reports` 字段。

---

## apply() 设计精髓

`apply()` 是调度中枢。参数透传 + 返回值设计，让计划和市场的差异完全落在 `apply()` 的使用方式上：

- **叶子函数不限制行为组合**：可以同时 `orders.new()` 下单和 `return` 数据。某些制度用法上会区分"摸底为主"或"执行为主"，但这是用户的策略选择，不是 API 约束。
- **市场**：`apply()` 只管分发，叶子自己读 MI、自己下单。不关心返回值。
- **计划**：`apply()` 跑多轮。第一轮叶子 `return` 产能/库存上报，宏函数在中间做全局修订，最后一轮叶子才下单。
- **混合**：基线是市场，MI 指标触发后临时切到计划式用法。

---

## 1. 市场

```python
@ese.firm
def market(mi, goods):
    ese.firm.apply("farm", farm_decide)
    ese.firm.apply("factory", factory_decide)

@ese.household
def consumption(mi, goods):
    ese.household.apply("worker", worker_spend)
    ese.household.apply("unemployed", jobless_spend)

@ese.government
def minimal_gov(mi, goods):
    gov = 唯一的政府实例
    gov.tax_rate = 0.05
```

- `apply()` 按行业/群体分发。叶子函数自己读 MI（均价、恩格尔等）、自己下单。
- 宏函数不关心叶子返回值。
- MI 指标触发后可以追加干预（混合制的萌芽）。

---

## 2. 计划

```python
@ese.firm
def planning_bureau(mi, goods):
    # ——— 阶段 1：拟合矩阵，算平衡表 ———
    # 计划局直接从 market.history 做部门间流量聚合，拟合 A 矩阵
    # 不经过 mi
    A = estimate_leontief_matrix(market.history)
    final_demand = estimate_final_demand(market.history, mi)
    gross_targets = solve_balance(A, final_demand)
    sector_targets = derive_sector_allocation(gross_targets, A)

    # ——— 阶段 2：摸底 ———
    # 叶子函数接收实体实例，读取真实产能/库存，自行决定上报多少
    feedback = {}
    for sector in ["steel", "machine", "food"]:
        feedback[sector] = ese.firm.apply(sector, survey,
                                          targets=sector_targets[sector])
        # survey 叶子 return {capacity: 上报产能, inventory: 上报库存}
        # 不包含交易数据（国家自己从 market.history 查）

    # ——— 阶段 3：迭代修订 ———
    while not converged:
        total_capacity = aggregate_reported_capacity(feedback)
        A_revised = revise_matrix(A, total_capacity, sector_targets)
        gross_targets = solve_balance(A_revised, final_demand)
        sector_targets = derive_sector_allocation(gross_targets, A_revised)

        for sector in sectors:
            feedback[sector] = ese.firm.apply(sector, survey,
                                              targets=sector_targets[sector])
        converged = check_convergence(sector_targets, prev_targets)

    # ——— 阶段 4：分配配额到企业 ———
    firm_quotas = allocate_to_firms(feedback, sector_targets)

    # ——— 阶段 5：执行 ———
    for sector in sectors:
        ese.firm.apply(sector, execute, quota=firm_quotas[sector])
        # execute 叶子接收配额，调用 orders.new() 下单

@ese.household
def planned_distribution(mi, goods):
    ese.household.apply("all", ration)

@ese.government
def planning_state(mi, goods):
    gov = 唯一的政府实例
    gov.unemployment_benefit = 0
```

- `apply()` 跑多轮：先 survey（return 数据），修订迭代收敛后，再 execute（下单）。
- A 矩阵拟合数据源是 `market.history`，不是 MI。
- 叶子调查只返回 {capacity, inventory}，交易数据国家自己从 `market.history` 查。
- 叶子函数接收实体实例，产能/库存是企业视角的真实值，上报多少由企业策略决定（可注水）。

---

## 3. 混合

```python
@ese.firm
def mixed(mi, goods):
    if mi.engel > 阈值:
        ese.firm.apply("farm", farm_decide, ceiling=上限)
    else:
        ese.firm.apply("farm", farm_decide)
    ese.firm.apply("factory", factory_decide)

    # 失业率过高 → 摸底工业产能 → 国家投资扩产
    if mi.unemployment > 阈值:
        gap = ese.firm.apply("factory", survey)
        ese.firm.apply("factory", invest)

@ese.household
def mixed_consumption(mi, goods):
    ese.household.apply("worker", worker_spend)
    if mi.gini > 阈值:
        ese.household.apply("low_income", subsidy_spend)

@ese.government
def interventionist_gov(mi, goods):
    gov = 唯一的政府实例
    if mi.unemployment > 阈值:
        gov.tax_rate *= 0.5
        gov.unemployment_benefit *= 1.5
```

- 基线是市场。MI 触发后临时切到计划式写法。
- 同一个 `@ese.firm` 内 `apply()` 在"不返回值"和"返回值"之间无缝切换。

---

## 叶子函数签名

### Firm 叶子

```python
# 叶子函数是普通 Python 函数，无装饰器，由 apply() 直接传入实例
def steel_survey(firm, orders, targets):
    return {
        "capacity": firm.capacity,     # 或 firm.capacity * 1.2（注水）
        "inventory": firm.inventory,
    }

def steel_execute(firm, orders, quota):
    for good_id, qty in calc_inputs(quota).items():
        orders.new(good_id=good_id, quantity=qty, price=..., side=DEMAND)
    orders.new(good_id=STEEL_ID, quantity=quota["output"], price=..., side=SUPPLY)
```

- 叶子函数可直接访问 Firm 实例的真实属性。
- survey 和 execute 是用户命名的两个叶子函数，不是 API 模式。他们在行为上没有限制，可以同时 return 数据和 `orders.new()`。计划流程中习惯让 survey 侧重 return、execute 侧重下单，但这只是使用惯例。
- 交易数据（历史成交量、均价等）由宏函数从 `market.history` 直接查询，不出现在 survey 的 return 中。

### Household 叶子

```python
def worker_spend(hh, orders):
    budget = hh.cash * 0.3
    orders.new(good_id=FOOD_ID, quantity=budget / food_price, price=..., side=DEMAND)
```

### Government 宏函数

```python
@ese.government
def fiscal_policy(mi, goods):
    gov = 唯一的政府实例
    if mi.unemployment > 0.1:
        gov.unemployment_benefit *= 1.2
    if mi.gini > 0.5:
        gov.tax_rate += 0.02
```

- Government 只有一个实例，无需 `apply()`，宏函数直接操作。但 Government 同样持有 `labels` 字段以备未来扩展。

---

## 10. 数据层 DataStore（待定）

> 初步方向：封装 DataStore 类提供链式查询 API 替代手写 SQL，底层保留 SQLite 作为序列化存储，查询结果返回 `pandas.DataFrame`。
>
> 具体设计和 API 尚未确定，留待后续讨论。
