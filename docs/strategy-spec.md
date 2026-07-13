# ESE 策略编写规范 v2.0

## 概述

ESE 的策略系统采用**三层架构**：宏观决策层 → 组合策略层 → 叶子操作层。

核心原则：
- **计划层**：每 tick 一次，看 MI 做宏观判断
- **策略层**：组合多个叶子操作，串成行业行动计划
- **操作层**：绑定到一类实体，只写 orders 订单

---

## 1. 企业策略（Firm）

### 1.1 三层定义

| 层级 | 注册方式 | 调用频率 | 死参数（引擎注入） | 自定义参数 |
|------|----------|----------|-------------------|-----------|
| 宏观决策 | `@ese.firm` | **每 tick 一次** | `mi, state` | 无 |
| 组合策略 | `@ese.firm.strategy("name")` | 被 `@ese.firm` 或其他 strategy 调用 | `mi, state` | `**kwargs` 任意 |
| 叶子操作 | `@ese.firm.sector("entity_type")` | 引擎按行业遍历每个企业 | `mi, firm, goods, orders` | `**kwargs` 任意 |

### 1.2 `apply()` 的用法

`ese.firm.apply(entity_type, sector_fn, **params)` 的作用：
1. 从 `state` 中找出所有 `entity_type` 匹配的活跃企业
2. 对每个企业，构造 `AgentOrders`，调用 `sector_fn(mi, firm, goods, orders, **params)`
3. 引擎自动收集所有企业的订单意图，统一处理

`apply()` 是策略层唯一的下发方式，不在 `apply()` 内的企业**不执行任何操作**。

### 1.3 完整代码示例

```python
# ============================================================
# 第 3 层：叶子操作（sector）
#   死参数：mi, firm, goods, orders
#   自定义参数：price, quota, mode, markup... 全部由策略层传入
# ============================================================

@ese.firm.sector("agriculture")
def farm(mi, firm, goods, orders, price=2.0, quota=None, mode="free"):
    """农业企业的订单操作"""
    qty = quota if quota else firm.inventory.get(1, 0)
    if mode == "clearance":
        price = price * 0.5
    elif mode == "hoard":
        qty = 0
    orders.new(
        seller_id=firm.id, buyer_id=0, good_id=1,
        quantity=qty, price=price, side=OrderSide.SUPPLY
    )


@ese.firm.sector("energy")
def energy_sector(mi, firm, goods, orders, price_cap=5.0):
    orders.new(
        seller_id=firm.id, buyer_id=0, good_id=2,
        quantity=firm.inventory.get(2, 0),
        price=min(price_cap, 10.0),
        side=OrderSide.SUPPLY
    )


@ese.firm.sector("manufacturing")
def workshop(mi, firm, goods, orders, markup=1.5):
    raw_cost = mi.sector_avg_price.get(1, 2.0)
    orders.new(
        seller_id=firm.id, buyer_id=0, good_id=3,
        quantity=10, price=raw_cost * markup,
        side=OrderSide.SUPPLY
    )


# ============================================================
# 第 2 层：组合策略（strategy）
#   死参数：mi, state
#   自定义参数：全部由上层传入
# ============================================================

@ese.firm.strategy("food_relief")
def food_relief(mi, state):
    """粮食救济：食品降价出清 + 能源限价"""
    market_price = mi.sector_avg_price.get(1, 5.0)
    ese.firm.apply("agriculture", farm,
                    price=market_price / 3, mode="clearance")
    ese.firm.apply("energy", energy_sector,
                    price_cap=2.0)


@ese.firm.strategy("stimulus")
def stimulus(mi, state):
    """经济刺激：全线扩产 + 高价放行"""
    ese.firm.apply("agriculture", farm, price=3.0, quota=50)
    ese.firm.apply("energy", energy_sector, price_cap=8.0)
    ese.firm.apply("manufacturing", workshop, markup=2.0)


@ese.firm.strategy("free_market")
def free_market(mi, state):
    """自由市场：各行业按默认参数执行"""
    ese.firm.apply("agriculture", farm)
    ese.firm.apply("energy", energy_sector)
    ese.firm.apply("manufacturing", workshop)


# ============================================================
# 第 1 层：宏观决策（@ese.firm）
#   死参数：mi, state
#   职责：只看 MI 做判断，选 strategy
# ============================================================

@ese.firm
def firm_decide(mi, state):
    if mi.engel > 0.6:                     # 恩格尔系数高 → 食品危机
        food_relief(mi, state)
    elif mi.unemployment_rate > 0.3:         # 失业率高 → 刺激经济
        stimulus(mi, state)
    else:
        free_market(mi, state)               # 默认：自由市场
```

### 1.4 纯市场经济的写法

纯市场经济不需要写 `@ese.firm` 和 `@ese.firm.strategy`。**只注册 sector，引擎自动按 entity_type 执行默认参数。**

```python
@ese.firm.sector("agriculture")
def farm(mi, firm, goods, orders):               # 没有自定义参数，全用默认
    orders.new(seller_id=firm.id, buyer_id=0, good_id=1,
               quantity=10, price=2.0, side=OrderSide.SUPPLY)

@ese.firm.sector("energy")
def energy_sector(mi, firm, goods, orders):
    orders.new(seller_id=firm.id, buyer_id=0, good_id=2,
               quantity=20, price=5.0, side=OrderSide.SUPPLY)

@ese.firm.sector("manufacturing")
def workshop(mi, firm, goods, orders):
    orders.new(seller_id=firm.id, buyer_id=0, good_id=3,
               quantity=10, price=3.0, side=OrderSide.SUPPLY)
# 零行调度代码。引擎自动执行。
```

---

## 2. 家庭策略（Household）

### 2.1 三层定义

| 层级 | 注册方式 | 调用频率 | 死参数（引擎注入） | 自定义参数 |
|------|----------|----------|-------------------|-----------|
| 宏观决策 | `@ese.household` | **每 tick 一次** | `mi, state` | 无 |
| 组合策略 | `@ese.household.strategy("name")` | 被 `@ese.household` 或其他 strategy 调用 | `mi, state` | `**kwargs` 任意 |
| 叶子操作 | `@ese.household.stratum("group_label")` | 引擎按群体遍历每个家庭 | `mi, hh, goods, orders` | `**kwargs` 任意 |

### 2.2 `apply()` 的用法

`ese.household.apply(group_label, stratum_fn, **params)` 与企业的 `apply()` 机制相同：
1. 从 `state` 中找出所有 `group_label` 匹配的家庭
2. 对每个家庭调用 `stratum_fn`

家庭的 `group_label` 是使用者自定义的群体分类，如 `"low_income"`, `"middle_income"`, `"unemployed"`, `"employed"` 等。

### 2.3 完整代码示例

```python
# ============================================================
# 第 3 层：叶子操作（stratum）
# ============================================================

@ese.household.stratum("low_income")
def poor_hh(mi, hh, goods, orders, save_ratio=0.8, consume_food=True):
    """低收入家庭：高储蓄、只买食品"""
    budget = hh.cash * (1 - save_ratio)
    if budget < 0.5:
        return
    if consume_food:
        qty = budget / mi.sector_avg_price.get(1, 2.0)
        orders.new(seller_id=0, buyer_id=hh.id, good_id=1,
                   quantity=qty, price=mi.sector_avg_price.get(1, 2.0),
                   side=OrderSide.DEMAND)


@ese.household.stratum("middle_income")
def middle_hh(mi, hh, goods, orders, food_ratio=0.6, tool_ratio=0.2):
    """中等收入家庭：食品、工具、服务都有消费"""
    budget = hh.cash * 0.3
    if budget < 1.0:
        return
    food_price = mi.sector_avg_price.get(1, 2.0)
    tool_price = mi.sector_avg_price.get(3, 3.0)
    orders.new(seller_id=0, buyer_id=hh.id, good_id=1,
               quantity=budget * food_ratio / food_price,
               price=food_price, side=OrderSide.DEMAND)
    orders.new(seller_id=0, buyer_id=hh.id, good_id=3,
               quantity=budget * tool_ratio / tool_price,
               price=tool_price, side=OrderSide.DEMAND)


@ese.household.stratum("unemployed")
def jobless_hh(mi, hh, goods, orders, search_intensity=1.0):
    """失业家庭：只买最低生存食品，找工作的开销"""
    min_food = 0.5 / mi.sector_avg_price.get(1, 2.0)
    orders.new(seller_id=0, buyer_id=hh.id, good_id=1,
               quantity=min_food, price=mi.sector_avg_price.get(1, 2.0),
               side=OrderSide.DEMAND)


# ============================================================
# 第 2 层：组合策略（strategy）
# ============================================================

@ese.household.strategy("austerity")
def austerity_consumption(mi, state):
    """紧缩消费：所有阶层降低消费比例"""
    ese.household.apply("low_income", poor_hh, save_ratio=0.9)
    ese.household.apply("middle_income", middle_hh, food_ratio=0.8, tool_ratio=0.1)
    ese.household.apply("unemployed", jobless_hh, search_intensity=1.5)


@ese.household.strategy("normal_consumption")
def normal_consumption(mi, state):
    """正常消费：各阶层按默认参数"""
    ese.household.apply("low_income", poor_hh)
    ese.household.apply("middle_income", middle_hh)
    ese.household.apply("unemployed", jobless_hh)


# ============================================================
# 第 1 层：宏观决策（@ese.household）
# ============================================================

@ese.household
def household_decide(mi, state):
    if mi.unemployment_rate > 0.3:
        austerity_consumption(mi, state)
    else:
        normal_consumption(mi, state)
```

### 2.4 纯市场经济的写法

只注册 stratum，不写 `@ese.household`。引擎自动按 `group_label` 执行默认参数。

```python
@ese.household.stratum("low_income")
def poor_hh(mi, hh, goods, orders): ...

@ese.household.stratum("middle_income")
def middle_hh(mi, hh, goods, orders): ...

@ese.household.stratum("unemployed")
def jobless_hh(mi, hh, goods, orders): ...
# 零行调度代码
```

---

## 3. 政府策略（Government）

当前版本为**单政府**设计，`state.governments` 中只有一条 Government 记录。

### 3.1 单层定义

| 层级 | 注册方式 | 调用频率 | 死参数（引擎注入） | 自定义参数 |
|------|----------|----------|-------------------|-----------|
| 宏观决策 | `@ese.government` | **每 tick 一次** | `mi, state, gov` | 无 |

政府没有 strategy 和 sector/stratum，因为只有一个实体，无需按类型分发。

### 3.2 政府可做的事

- 调整税率：`gov.tax_rate = new_rate`（下一 tick 生效）
- 调整失业金：`gov.unemployment_benefit = new_amount`
- 发放补贴/救济：`orders.new(...)` 直接下单（如政府收购过剩粮食）
- 不做操作：函数体 `pass`

### 3.3 代码示例

```python
@ese.government
def gov_decide(mi, state, gov):
    if mi.unemployment_rate > 0.3:
        gov.unemployment_benefit = min(gov.cash * 0.05, 5.0)    # 提高失业金
        gov.tax_rate = 0.05                                      # 降低税率

    if mi.engel > 0.6:
        # 政府收购粮食，稳定市场
        food_price = mi.sector_avg_price.get(1, 2.0)
        orders.new(seller_id=0, buyer_id=gov.id, good_id=1,
                   quantity=50, price=food_price * 1.2,
                   side=OrderSide.DEMAND)

    if mi.gini > 0.5:
        gov.tax_rate = 0.15                                      # 对富人加税
```

---

## 4. `apply()` 的完整行为规范

### 调用方式

```python
ese.firm.apply("agriculture", farm, price=2.0, mode="free")
ese.household.apply("low_income", poor_hh, save_ratio=0.9)
```

### 内部行为

1. 从 `state` 获取所有 `entity_type` / `group_label` 匹配的活跃实体
2. 对每个匹配实体，执行：
   - 构造 `AgentOrders(orders, self.order_factory)`
   - 调用 `fn(mi, entity, goods, orders, **params)`
   - 调用 `orders._consume()` 取出意图
   - 调用 `_dispatch_agent_result` 处理订单
3. `apply()` 内未提及的实体类型本 tick 不执行任何操作

### 不 apply 的实体

如果一个 entity_type 没有被任何 `apply()` 调用覆盖，该类型的所有实体本 tick **不产出生任何订单**（也不报错）。这是设计选择：计划经济下，未被列入计划的行业就应该停产，而非自由活动。

---

## 5. 三种制度对比

| | 纯市场 | 混合经济 | 纯计划 |
|---|---|---|---|
| `@ese.firm` | **不写** | 写 | 写 |
| `@ese.firm.strategy` | 不需要 | 要害行业写 | 全覆盖写 |
| `@ese.firm.sector` | 每种 entity_type 注册一个 | 同左 | 同左 |
| `apply()` 覆盖范围 | 引擎自动全覆盖 | 要害行业走 strategy 的 apply，其余在 `@ese.firm` 里手动 apply | strategy 的 apply 覆盖全部行业 |
| 调度方式 | 引擎自动 | `@ese.firm` 按 MI 选择 strategy + 手动 apply 兜底 | `@ese.firm` 选 strategy 全覆盖 |

---

## 6. 参数速查

| 层级 | 死的（引擎注入，不能改） | 活的（使用者自定义） |
|------|------------------------|---------------------|
| `@ese.firm(mi, state)` | `mi`, `state` | 无 |
| `@ese.firm.strategy(mi, state)` | `mi`, `state` | `**kwargs` |
| `@ese.firm.sector(mi, firm, goods, orders)` | `mi`, `firm`, `goods`, `orders` | `**kwargs` |
| `@ese.household(mi, state)` | `mi`, `state` | 无 |
| `@ese.household.strategy(mi, state)` | `mi`, `state` | `**kwargs` |
| `@ese.household.stratum(mi, hh, goods, orders)` | `mi`, `hh`, `goods`, `orders` | `**kwargs` |
| `@ese.government(mi, state, gov)` | `mi`, `state`, `gov` | 无 |
