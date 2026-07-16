# ESE (Economic Simulation Engine)

![](headup.png)

别打口水仗了，来 ese 模拟你的完美经济制度。

ESE 是一个类似回合制，按轮次执行的经济沙盒。你定义初始世界、编写主体策略和分配规则，跑 N 轮，得到一个国家的经济演化数据。换个规则再跑一次，制度的优劣直接从 Gini 系数、失业率、恩格尔系数中体现。

---

# 一、快速开始

```bash
uv sync
uv run python examples/generate_town.py
uv run python examples/town.py
```

---

# 二、核心范式

ESE 按照轮次（tick）执行，没有规定天数。你可以认为一轮为一天，也可以认为一轮为一年——取决于你的实验设计。

ESE 有三类主体，你需要编写三种主体在每轮经济循环中的 strategy（策略）与 behavior（行动）。

| 主体 | 大致行为 |
| --- | --- |
| **Firm** 企业 | 生产、订单交易（商品买卖，雇佣是特殊的劳动力交易）、生产 |
| **HouseHold** 家庭 | 消费商品、劳动力交易 |
| **Government** 政府 | 交易（主要为公共项目）、发放福利金 |

ESE 要求你理解三个概念：

| 概念 | 代码 | 职责 |
|------|--------|------|
| **strategy** | `@ese.firm` / `@ese.household` / `@ese.government` 装饰的函数 | 每轮只调一次，决定不同类主体的执行策略 |
| **apply** | `ese.firm.apply(label, leaf_fn)` | 把标签匹配到的实体分发给行为函数 |
| **behavior** | `(entity, orders, mi, market, **params)` | 一个实体每轮具体做什么 |

一个典型的 ESE 程序编写范式如下：
```python
@ese.firm
def 所有企业策略
    # 不同类企业（部门）
    # 按何种顺序
    # 执行哪些动作

@ese.household
def 所有家庭策略
    # 不同类家庭
    # 按何种顺序
    # 执行哪些动作

@ese.government
def 所有政府策略

@ese.allocation
def 分配策略
    # 匹配供应订单-需求订单
@ese.allocation.pricing
def 分配策略的价格策略
    # 供需订单的两个价格，如何达成一致，并对齐交易
```

以下是最简单的企业写法，每类企业按照机械行为进行生产与交易
```python
# 假设商品编号 1 为食物，2 为工具
@ese.firm                                           # strategy：firm，每类企业（部门）按照其 behavior 执行
def firm_strategy(mi, goods, market):
    ese.firm.apply("farm", farm_behavior)           # apply
    ese.firm.apply("workshop", work_behavior)

def farm_behavior(firm, orders, mi, market):        # behavior
    # -1 工具 +5 食物，模拟生产行为
    firm.inventory[2] -= 1.0                        # 读/写实体状态
    firm.inventory[1] += 5.0
    # 挂供应订单，卖出食物
    orders.new(good_id=1, quantity=5, price=2.0, side=OrderSide.SUPPLY)
...
```

## behavior：每个主体（企业/家庭/政府）能知道什么？

每个 behavior 函数可用 4 个对象：

- **`entity（firm、hh、gov）`** — 实体实例
  - 可读写 `cash`、`inventory`、`capacity`、`employees`、`is_active`、`tax_rate` 等字段
- **`orders`** — 订单操作
  - `.new(good_id, quantity, price, side)` / `.cancel(order_id)` / `.update(order_id, ...)`，引擎自动填充买卖方 ID
- **`mi`** — 宏观情报
  - `.gini` / `.unemployment_rate` / `.engel` / `.sector_avg_price[good_id]` 等统计局指标（经噪声处理）
- **`market`** — 市场快照
  - `.supply`（卖单池）、`.demand`（买单池）、`.history`（成交账本）

以企业为例
```python
def steel_firm(firm, orders, mi, market):
    # 企业现金
    firm.cash
    # 企业订单操作
    orders.new(good_id=1, quantity=5, price=2.0, side=OrderSide.SUPPLY)
    orders.cancel(order_id)
    # 宏观经济指标（统计局报表，含噪声）
    mi.unemployment_rate          # 决定是否扩招
    mi.sector_avg_price[1]        # 食物行业均价，指导报价
    # 市场实时信号
    market.supply                 # 同行挂单价
    market.history.get_avg_price_by_good(1, n=10)  # 近期成交均价
```

## strategy：每类主体的宏观策略（`@ese.firm` `@ese.househould` `@ese.government`）能知道什么？

strategy 的第一个参数 `mi` 是 **MarketIntelligence** — 你可以理解为统计局的宏观数据，不含任何企业个体数据，且经噪声处理：

| 字段 | 说明 |
|------|------|
| `mi.gini` / `mi.unemployment_rate` / `mi.engel` | 宏观指标 |
| `mi.sector_avg_price` / `mi.sector_total_supply` / `mi.sector_total_demand` | 行业汇总 |
| `mi.tax_rate` / `mi.unemployment_benefit` / `mi.active_firms` | 政策参数 |

---

# 三、分配策略

分配策略`@ese.allocation`决定供需池怎么配对——它是**制度的核心**。同一个世界、同一群企业，换个分配规则，宏观结果完全不同。

分配策略中的定价策略`@ese.allocation.princing`则是分类中的灵魂——需求池和供应池中的订单往往价格不一致，你需要让他们达成同一价格并进行交易。

在现实世界中，这个行为往往是交易所、市商、集合竞价、场内外交易、行政定价来执行……总之这就是被人们批判的最多的“制度之恶”或“结构性压迫”——现在你需要手动编写它。

```python
@ese.allocation
def my_alloc(mi, supply, demand, goods, market, pricing=None):
    # 你的配对逻辑
    return matched, remaining_supply, remaining_demand

@ese.allocation.pricing
def my_price(supply_order, demand_order, config, market):
    return (supply_order.price + demand_order.price) / 2.0  # 简单粗暴的供需平均值定价
```

---

# 四、创建世界

用 `WorldBuilder`，不用手写 SQL：

```python
(WorldBuilder()
    .add_good(1, "food", "food", 1)
    .add_good(2, "tool", "raw_material", 1)
    .add_firm(101, 1000.0, labels=["farm"], capacity=50.0, inventory={1: 20.0, 2: 5.0})
    .add_firm(102, 1000.0, labels=["workshop"], capacity=30.0, inventory={1: 10.0, 2: 15.0})
    .add_household(1, 60.0, reservation_wage=6.0, is_employed=True, employer_firm_id=101)
    .add_government(201, 2000.0, tax_rate=0.1, unemployment_benefit=2.0)
    .save("town_world.db"))
```
交给 AI 来做吧

---

# 五、三种制度

内核（结算器、破产规则、订单生命周期）对三种制度完全一样。区别只在 strategy 怎么写。

## 无政府自由主义市场

`apply()` 只管分发，各企业/家庭自己读 MI，利润最大原则行事（下单）。

```python
@ese.firm
def market(mi, goods, market):
    ese.firm.apply("farm", farm_behavior)
    ese.firm.apply("workshop", workshop_behavior)

def farm_behavior:
    #利润最大的下单方法
```

## 中央计划经济

下面演示列昂惕夫的投入产出模型（1936）与苏联国家计划委员会的物资平衡法。

核心假设是生产技术系数矩阵 A 稳定可估。

但 ESE 不提供上帝视角的 A 矩阵——计划委员会也必须从 `market.history` 的成交记录中自行拟合。

```python
@ese.firm
def plan(mi, goods, market):
    # 1. 摸底 — 各企业上报产能和技术系数
    reports = {}
    for sector in ["farm", "workshop"]:
        reports[sector] = ese.firm.apply(sector, survey)

    # 2. 从历史成交估算 A 矩阵，从上报产能推定生产瓶颈
    A = estimate_tech_matrix(market.history, goods)     # {产出: {投入: 系数}}
    cap = {s: max(r["capacity"] for r in reports.get(s, [{}])) for s in reports}

    # 3. (I−A) 迭代求解 → 各商品生产计划
    targets = solve_io(A, cap, population=len(ese._simulator.state.households))

    # 4. 摊派 — 各企业按指标下单
    for sector in reports:
        ese.firm.apply(sector, execute, plan=targets)


# survey(firm, orders, mi, market) → return {"capacity": ..., "input_per_output": ...}
# execute(firm, orders, mi, market, plan) → 按 plan 调用 orders.new(...)
```

## 混合制

MI 指标过阈值时追加干预。

```python
@ese.firm
def mixed(mi, goods, market):
    if mi.engel > 0.6:
        ese.firm.apply("farm", farm_behavior, price_cap=1.5)
    else:
        ese.firm.apply("farm", farm_behavior)

    if mi.unemployment > 0.3:
        gap = ese.firm.apply("workshop", survey)
        ese.firm.apply("workshop", invest, funding=sum(g["gap"] for g in gap))
```

---

# 六、FAQ

**为什么没有内置投入产出表？**

策略只能从 MI 的统计局汇总报表（已加噪）自行推断经济结构。即使是计划委员会，也必须为估算误差付出代价。

**货币总量为何恒定？**

剔除货币政策干扰，单纯观察资源配置制度。

**为什么没有技术创新？金融系统呢？**

不好做，以后再说。

---

# 七、深入阅读

- `docs/design.md` — 完整架构设计、API 签名、数据模型
- `examples/town.py` — 完整可运行的市场制示例（50 轮，含 CSV + 图表输出）
