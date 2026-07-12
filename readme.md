# ESE (Economic Simulation Engine) 说明

**一句话：ESE 是一个回合制经济沙盒。每一轮（Tick），企业、家庭、政府各自执行你编写的策略，产生买卖订单，订单匹配后进行交付和结算。运行 N 轮后，你得到一个国家的经济演化数据。**

## 这玩意儿到底在跑什么？

想象一个简单的经济循环：

1. **每个 Tick 开始**，引擎先把上一轮匹配好的订单完成交付（一手交钱、一手交货），并把交不起货的标记为违约、该破产的破产。
2. **企业执行策略**：接收 `MarketIntelligence`（下称 MI，统计局报表 + 公开市场情报），结合自身库存、现金、员工情况，决定生产、定价、买卖，生成订单。
3. **家庭执行策略**：接收 MI，根据收入、储蓄、就业状态，决定消费，生成订单。
4. **政府执行策略**：接收 MI，决定是否调整税率、发福利，生成订单。
5. **分配策略匹配订单**：遍历供需池，把能对上的买卖单配对（按价格优先、按配额、按你写的任何规则）。
6. **引擎聚合全局数据并加噪声**（模拟统计局报表的误差），产出下一轮 MI。
7. **记录本轮快照**（基尼系数、失业率等），进入下一个 Tick。

循环往复。你编写的策略就是主体的"大脑"，通过替换策略来对比不同制度的效果。

## 主体

| 主体 | 持有 | 能做什么 |
|---|---|---|
| **Firm（企业）** | 现金、库存、产能、员工列表 | 生产商品、定价、雇佣/解雇、买卖 |
| **Household（家庭）** | 现金、库存、就业状态 | 消费商品、求职 |
| **Government（政府）** | 税收收入 | 征税、发福利、招标公共工程 |

## 交易机制

所有订单进入全局交易池：

- **Supply Pool**：卖方报价簿（企业卖商品、家庭卖劳动力）
- **Demand Pool**：买方询价簿（企业买原材料、家庭买消费品）

分配策略匹配后，进入交付周期（`delivery_lag` 个 Tick 后才真正交割），模拟生产运输的时间成本。

## 核心特性

- 单政府，货币总量恒定，生产技术不变
- 订单状态：`OPEN → ALLOCATED → FULFILLED | DEFAULTED | CANCELLED | EXPIRED`
- 双边保证金制度：订单履约退还保证金，违约扣除违约方保证金
- 企业破产清算流程：拖欠工资 → 欠税 → 归零，清算后取消所有订单
- 订单强制交付周期，不允许瞬时交付

## MarketIntelligence（市场情报）：无上帝视野

策略的第一个参数不再是包含所有对家资产负债表的 `obs` 字典，而是一个**统计局报表级别的聚合对象**——模拟真实世界中企业做决策时能看到的信息：国家统计局公告、央行利率、行业均价，而不是对家的库存和现金。

| 字段 | 类型 | 说明 | 状态 |
|------|------|------|------|
| `tick` | `int` | 当前 Tick | ✅ |
| `gini` | `float` | 基尼系数 | ✅ |
| `unemployment_rate` | `float` | 失业率 | ✅ |
| `engel` | `float` | 恩格尔系数 | ✅ |
| `sector_avg_price` | `Dict[int, float]` | 各商品挂单均价 | ✅ |
| `sector_total_supply` | `Dict[int, float]` | 各商品总供给量 | ✅ |
| `sector_total_demand` | `Dict[int, float]` | 各商品总需求量 | ✅ |
| `tax_rate` | `float` | 税率 | ✅ |
| `unemployment_benefit` | `float` | 失业金标准 | ✅ |
| `active_firms` | `int` | 活跃企业数 | ✅ |
| `gdp` | `float` | GDP | ❌ P2 待实现 |
| `cpi` | `float` | 消费者价格指数 | ❌ P2 待实现 |
| `avg_wage` | `float` | 平均工资 | ❌ P2 待实现 |
| `labor_income_share` | `float` | 劳动收入占比 | ❌ P2 待实现 |
| `sector_cr3` | `Dict[int, float]` | 行业集中度 CR3 | ❌ P2 待实现 |
| `sector_inventory_ratio` | `Dict[int, float]` | 库存/产能比 | ❌ P2 待实现 |
| `central_bank_rate` | `float` | 基准利率 | ❌ 无央行 |
| `government_announcement` | `Optional[str]` | 政府指导价/配额公告 | ❌ 待设计 |

> **设计理念：** 所有 `✅` 字段经 `InformationFriction` 加噪后注入，模拟统计局有偏公告或公开市场情报失真。计划经济和市场经济的唯一区别在于 `noise_type` 配置（计划 = `none`，市场 = `gaussian`）。策略函数不再能遍历 `all_firms` 获取对家电库数据——只能像真实企业一样，从宏观报表和行业均价中推断市场状态。

策略函数签名示例：

```python
from core.market_intelligence import MarketIntelligence

def firm_strategy(mi: MarketIntelligence, firm: Firm, goods: Dict[int, Good]) -> Dict:
    # 用统计局报表做决策
    if mi.gini > 0.4:
        ...
    sector_price = mi.sector_avg_price.get(good_id, default_price)
    ...
```

---

## 快速开始

### 1. 环境准备

```bash
cd ese
uv sync
```

### 2. 生成初始世界

```bash
uv run python examples/generate_town.py
```

这会在项目根目录生成 `town_world.db`（2 商品、2 企业、10 家庭、1 政府），并同步到 `config/seed_world.db`。

### 3. 配置实验参数（`config/default.yaml`）

```yaml
seed: 42
noise_type: "gaussian"       # none / gaussian / upward_bias / downward_bias
base_collateral_ratio: 0.1
order_expire_ticks: 30
```

### 4. 编写策略

ESE 使用 `Engine` 作为单一入口，槽名即装饰器方法名。参考 `examples/town_strategies.py`：

| 策略槽 | 注册方式 | 签名 | 职责 |
|------|---------|------|------|
| firm | `@ese.firm` | `(mi, firm, goods)` | 企业调度器（每 tick 每企业调用一次，内部按标签分发） |
| firm 标签 | `@ese.firm.label("x")` | `(mi, firm, goods)` | 特定类型企业的策略（被调度器通过 `ese.firm.use("x", ...)` 调用） |
| household | `@ese.household` | `(mi, hh, goods)` | 家庭消费 |
| government | `@ese.government` | `(mi, gov, goods)` | 征税、发放福利 |
| allocation | `@ese.allocation` | `(mi, supply_pool, demand_pool, goods, pricing=None)` | 匹配买卖订单（**制度灵魂**：按价格优先→市场；按配额→计划） |
| allocation.pricing | `@ese.allocation.pricing` | `(supply_order, demand_order, config)` | 定价规则（引擎自动注入到 allocation 中） |

> **调度器与标签策略的关系：** `@ese.firm` 是调度器——每 tick 被引擎对每个企业调用一次。调度器通过 `ese.firm.use(firm.strategy_label, mi, firm, goods)` 将具体企业分发到对应的标签策略。`@ese.firm.label("farm")` 注册一个标签策略实现。不是并列关系，是包含关系。

### 5. 运行实验

```python
from ese import Engine
import examples.town_strategies as town

ese = Engine("config/default.yaml", "town_world.db")

@ese.firm
def firm_orchestrator(mi, firm, goods):
    return town.firm_strategy(mi, firm, goods)

@ese.household
def household_strategy(mi, hh, goods):
    return town.household_strategy(mi, hh, goods)

@ese.government
def government_strategy(mi, gov, goods):
    return town.government_strategy(mi, gov, goods)

@ese.allocation
def town_allocation(mi, supply, demand, goods, pricing=None):
    return town.town_allocation(mi, supply, demand, goods, pricing)

@ese.allocation.pricing
def mid_pricing(supply, demand, config):
    return town.mid_pricing(supply, demand, config)

snapshots = ese.run(n_ticks=50)

import pandas as pd
pd.DataFrame(snapshots).to_csv("results.csv", index=False)
```

---

## 输出指标

**Snapshot（每 Tick 返回，由 `Reporter.snapshot()` 生成）：**

| 字段 | 含义 |
|---|---|
| `tick` | Tick 序号 |
| `gini` | 基尼系数（贫富差距） |
| `engel` | 恩格尔系数（食品支出占比） |
| `unemployment` | 失业率 |
| `active_firms` | 活跃企业数 |

**MarketIntelligence（每 Tick 构建，注入策略，含噪声）：**

见上方 [MarketIntelligence](#marketintelligence-市场情报无上帝视野) 表格。

## FAQ

**Q：为什么没有内置投入产出表？**

A：实验者的策略不能直接访问全局的投入产出矩阵（A 矩阵）——那是上帝视野。策略只能从 MI（MarketIntelligence）提供的**统计局汇总报表**（行业均价、供给总量、基尼系数等，已加噪）来自行推断经济结构。这是本项目与那篇 2026 年论文最根本的差异：计划委员会也必须为估算误差付出代价。

**Q：货币总量为何恒定？**

A：剔除货币政策的干扰，单纯观察资源配置制度。如需模拟通胀，可在 Government 策略中实现货币增发——当然这是 AI 说的，我不这么认为，还是建议你不要动货币总量。等到有了金融系统再去玩吧。

**Q：为什么没有技术创新？**

A：因为不好做，以后再做。而且一旦做了这个，就有点像上帝开发一样，规定了技术的本质，一定会引来从哲学到经济学、社会学的争议。

**Q：你的金融系统呢？我想玩银行**

A：我们注意到，整个 ESE 某种程度上就是在扮演一种绝对精神。更具体的说，就像钢铁雄心4，扮演一个国家的绝对精神的同时，也大量利用了政府的强制工具—— ESE 也这样，扮演大手发力的同时也会用到大量银行工具。这个有些复杂，虽然比技术创新好做，但也要之后再说。更新的优先级会比技术创新高。