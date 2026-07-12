# ESE (Economic Simulation Engine)

别打口水仗了，来 ese 模拟你的完美经济制度

![](headup.png)

ESE 是一个回合制经济沙盒。你定义初始世界、编写主体策略和分配规则，跑 N 轮，得到一个国家的经济演化数据。换个规则再跑一次，制度优劣直接从数据中体现。

---

## 1 ESE 基础部件

在理解一回合怎么运转之前，先认识几个基础部件。

**商品（Good）**：经济中每一类可交易的东西，用一个 good_id 标识。每种商品有一个 `good_type`（如 food、raw_material、labor）和一个 `delivery_lag`。`delivery_lag` 表示从订单匹配成功到真正交货需要经过多少轮——没有瞬时交付，模拟生产运输的时间成本。

**企业（Firm）**：持有现金、库存、员工列表。可以**生产**（消耗库存中的原材料，产出新产品）、**定价买卖**、**雇佣和解雇**。每个企业有一个 `strategy_label`，用于匹配你为企业类编写的策略。企业不活跃（`is_active=False`）后不再参与任何经济行为。

**家庭（Household）**：持有现金、库存、就业状态。可以**消费商品**、**求职**。家庭是劳动力的提供者和最终消费品的主要需求方。

**政府（Government）**：全局唯一，内核自动完成收税和发放失业金。你也可以在政府策略中实现额外的财政行为。

**订单（Order）**：一切经济活动的载体。订单分为供需两类（`SUPPLY/DEMAND`）、商品、数量、价格、状态。所有活跃订单分别进入**供给池**和**需求池**。订单不是瞬间执行的——它的生命周期是 ESE 运行的核心。

---

## 2 ESE 每轮周期

每一轮 Tick，ese 按以下顺序执行 9 个步骤。其中第 5、6 步是你编写策略被调用的位置。

### 2.1	结算到期订单

本轮之前已匹配好的订单，如果设定的交割时间到了，则执行实际交付：卖方扣库存、买方加库存，买方付钱、卖方收钱，双方保证金退还。

如果卖方库存不足或买方现金不足，则该方违约。违约方的保证金罚没给对方作为补偿。交付完成后，现金为负的企业立即进入破产清算。

以下是**订单生命周期**：

```
从策略创建 → [OPEN] 进入供需池
          → [ALLOCATED] 分配策略匹配成功，设定 settlement_tick = 当前 tick +   delivery_lag
          → 到期结算：
             交付成功 → [FULFILLED]
             交付失败 → [DEFAULTED]
          → 中途被策略取消 → [CANCELLED]
          → 在池中超过 order_expire_ticks 轮未匹配 → [EXPIRED]
```

**双边保证金**：每个订单创建时，买卖双方各冻结订单金额 x 保证金比例（base_collateral_ratio）的现金作为押金。履约退还，违约罚没。保证金比例是动态的：掉出 base，然后根据该主体的历史履约率上调——经常违约的主体需要押更多钱。

**企业破产清算**：现金归零后，库存折价卖给政府换现金，回收冻结保证金，然后按优先级偿付：先结清拖欠工资，再缴纳欠税，最后归零。所有员工被解雇，所有关联订单取消或违约，企业标记为不活跃。

### 2.2	工资发放

每个活跃企业向自己的员工支付工资（金额 = 员工的 labor_ask_price）。现金不足的企业记录欠薪。

### 2.3	收税

每个活跃企业按税率缴纳所得税，收入进入政府账户。

### 2.4	发失业金

政府对处于失业状态的家庭发放失业金。政府现金不足时按比例削减。

### 2.5	执行主体策略	← 你要写的东西之一

按**企业 → 家庭 → 政府**的顺序，ese 逐一调用你注册的**策略函数**，每个函数接收当前的市场情报（MarketIntelligence，下详）、该主体的数据、商品目录，返回本轮要执行的操作：

```python
{
    "new": [Order, ...],       # 新创建的订单
    "cancel": [order_id, ...], # 要取消的订单（必须是仍在供需池中的 OPEN 订单）
    "update": [Order, ...],    # 替换已有订单（先取消旧单再创建新单，两者原子化）
}
```

`new` 中的订单通过校验后进入供需池，`cancel` 中的订单退还保证金、从池中移除，`update` 先校验新订单，通过后才执行替换。

**策略的调度机制**
以企业为例，家庭与政府同理。

`@ese.firm` 注册的不是一个具体策略，而是一个**调度器**。ese 每轮对每个活跃企业调用这个调度器，调度器根据企业的 `strategy_label` 分发到对应的标签策略：

```python
@ese.firm
def orchestrator(mi, firm, goods):
    return ese.firm.use(firm.strategy_label, mi, firm, goods)
```

然后用 `@ese.firm.label("农场")` 注册每种企业的具体行为。没有匹配到标签的企业，ese 输出警告、返回空操作。

策略的具体内容，就是你写的逻辑：消耗多少原材料、产出多少成品、按什么价格挂单、招不招人——由你决定。ese 只提供库存读写和订单创建校验，不内置任何生产函数。

### 2.6	执行分配策略

ese 将**供给池**和**需求池**交给你注册的分配函数，你决定哪些买卖单配对成交：

```python
@ese.allocation
def my_allocation(mi, supply_pool, demand_pool, goods, pricing=None):
    # 返回 (matched_orders, remaining_supply, remaining_demand)
    ...
```

分配策略是**制度的核心**。按价格优先、按配额、按随机、按任何你设计的规则——都写在这里。同一个世界、同一群企业、同一个起始状态，换一种分配规则，宏观结果可能截然不同。

匹配成功的订单进入 ALLOCATED 状态，设定交割轮次（当前 tick + 商品的 delivery_lag），移入待结算队列。

**定价规则**是分配策略的子策略，ese 自动注入到分配函数中：

```python
@ese.allocation.pricing
def my_pricing(supply_order, demand_order, config):
    # 返回成交价
    ...
```

### 2.7	清理过期订单

扫描供需池，创建时间超过 `order_expire_ticks` 轮的订单标记为 EXPIRED，退还保证金，移出供/需池。

### 2.8	回合收尾

所有失业家庭的失业轮次 +1。

### 2.9	生成市场情报

ese 汇总本轮宏观数据（基尼系数、失业率、恩格尔系数、各商品均价和供需总量等），经噪声函数处理后产出下一轮的市场情报（MarketIntelligence）。

---

## 3 市场情报 MarketIntelligence

还在对计划经济实验中的上帝视角耿耿于怀吗？ese 拒绝全世界布满摄像头的**全量数据监控**的虚假社会，取而代之的是更现实的市场情报（MarketIntelligence）。在模拟社会主义国家时，你可以认为 mi 是国家统计局；在模拟资本主义国家时，你可以认为 mi 是经济分析据/美联储/劳工统计局。

策略函数的第一个参数 `mi` 是一个 MarketIntelligence 对象。它**不包含**任何企业或家庭的资产负债表——你无法遍历全服查看对家的库存和现金。你的策略只能从一个"统计局报表"的视角做决策。

目前已有字段：

- `tick` — 当前轮次
- `gini` — 基尼系数
- `unemployment_rate` — 失业率
- `engel` — 恩格尔系数
- `sector_avg_price` — 各商品挂单均价
- `sector_total_supply` — 各商品总供给量
- `sector_total_demand` — 各商品总需求量
- `tax_rate` — 税率
- `unemployment_benefit` — 失业金标准
- `active_firms` — 活跃企业数

所有统计类字段会经过噪声函数（在 `config/default.yaml` 中配置 `noise_type`）处理后才注入策略。噪声类型包括高斯、均匀、上行偏差、下行偏差，也可以关闭噪声。无论哪种经济体制，核心都是一样的：看不到别家的库存和现金，只能从报表和均价里推断市场状态。

---

## 4 快速开始

推荐使用 uv (https://docs.astral.sh/uv/) 管理 Python 环境和依赖，而非 conda / Anaconda。

uv 是纯 Python 包管理器，不捆绑预编译的科学计算库，不创建庞大的 base 环境。

最重要的是，uv 解析依赖比 conda 快一个数量级，是业界主流趋势。如果你没有，可以按照如下命令安装：

Windows (PowerShell)
```sh
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
macOS / Linux
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 4.1 环境

```bash
cd ese
uv sync
```

### 4.2 生成初始世界

```bash
uv run python examples/generate_town.py
```

生成 `town_world.db`：2 种商品（food、tool）、2 家企业（农场、工坊）、10 个家庭、1 个政府。会同步到 `config/seed_world.db`。

### 4.3 配置参数（`config/default.yaml`）

```yaml
seed: 42
noise_type: "gaussian"
base_collateral_ratio: 0.1
order_expire_ticks: 30
```

### 4.4 策略编写与运行

完整的参考实现见 `examples/town.py`。下面是一个自包含的最简示例（2 种商品、一家做食物的农场和一家做工具的工坊）：

```python
from ese import Engine
from core.entities import Order, OrderSide
from core.market_intelligence import MarketIntelligence

ese = Engine("config/default.yaml", "town_world.db", output_dir="./results/town")

# --- 企业调度器：按 strategy_label 分发 ---
@ese.firm
def orchestrator(mi, firm, goods, orders):
    return ese.firm.use(firm.strategy_label, mi, firm, goods, orders)

# --- 农场：1 工具 → 5 食物，挂单卖食物、买工具 ---
@ese.firm.label("farm")
def farm(mi, firm, goods, orders):
    result = {"new": [], "cancel": [], "update": []}
    if firm.inventory.get(2, 0) >= 1.0:
        firm.inventory[2] -= 1.0
        firm.inventory[1] = firm.inventory.get(1, 0) + 5.0
    if firm.inventory.get(1, 0) > 2.0:
        result["new"].append(Order(
            order_id=f"f{firm.id}_sell_food_{mi.tick}",
            seller_id=firm.id, buyer_id=0, good_id=1,
            quantity=min(firm.inventory[1]-2, 10), price=2.0,
            side=OrderSide.SUPPLY))
    if firm.cash > 50 and firm.inventory.get(2, 0) < 10:
        result["new"].append(Order(
            order_id=f"f{firm.id}_buy_tool_{mi.tick}",
            seller_id=0, buyer_id=firm.id, good_id=2,
            quantity=2, price=3.0,
            side=OrderSide.DEMAND))
    return result

# --- 工坊：2 食物 → 3 工具，挂单卖工具、买食物 ---
@ese.firm.label("workshop")
def workshop(mi, firm, goods, orders):
    result = {"new": [], "cancel": [], "update": []}
    if firm.inventory.get(1, 0) >= 2.0:
        firm.inventory[1] -= 2.0
        firm.inventory[2] = firm.inventory.get(2, 0) + 3.0
    if firm.inventory.get(2, 0) > 2.0:
        result["new"].append(Order(
            order_id=f"f{firm.id}_sell_tool_{mi.tick}",
            seller_id=firm.id, buyer_id=0, good_id=2,
            quantity=min(firm.inventory[2]-2, 5), price=3.0,
            side=OrderSide.SUPPLY))
    if firm.cash > 50 and firm.inventory.get(1, 0) < 10:
        result["new"].append(Order(
            order_id=f"f{firm.id}_buy_food_{mi.tick}",
            seller_id=0, buyer_id=firm.id, good_id=1,
            quantity=3, price=2.0,
            side=OrderSide.DEMAND))
    return result

# --- 家庭：每轮拿 20% 现金消费，70% 买食物、30% 买工具 ---
@ese.household
def hh(mi, hh, goods, orders):
    result = {"new": [], "cancel": [], "update": []}
    budget = hh.cash * 0.2
    if budget < 0.5:
        return result
    result["new"].append(Order(
        order_id=f"h{hh.id}_buy_food_{mi.tick}", seller_id=0, buyer_id=hh.id,
        good_id=1, quantity=budget*0.7/2.0, price=2.0,
        side=OrderSide.DEMAND))
    result["new"].append(Order(
        order_id=f"h{hh.id}_buy_tool_{mi.tick}", seller_id=0, buyer_id=hh.id,
        good_id=2, quantity=budget*0.3/3.0, price=3.0,
        side=OrderSide.DEMAND))
    return result

# --- 政府：不做额外操作 ---
@ese.government
def gov(mi, gov, goods, orders):
    return {"new": [], "cancel": [], "update": []}

# --- 分配：价格优先匹配 ---
@ese.allocation
def alloc(mi, supply, demand, goods, pricing=None):
    matched = []
    supply = sorted([o for o in supply if o.quantity > 0], key=lambda x: x.price)
    demand = sorted([o for o in demand if o.quantity > 0], key=lambda x: -x.price)
    for s in supply:
        for d in demand:
            if s.good_id == d.good_id and s.price <= d.price:
                qty = min(s.quantity, d.quantity)
                price = pricing(s, d, {}) if pricing else (s.price+d.price)/2
                matched.append(Order(
                    order_id=f"match_{s.good_id}_{mi.tick}_{len(matched)}",
                    seller_id=s.seller_id, buyer_id=d.buyer_id, good_id=s.good_id,
                    quantity=qty, price=price, side=s.side))
                s.quantity -= qty; d.quantity -= qty
                break
    return matched, [o for o in supply if o.quantity > 0], [o for o in demand if o.quantity > 0]

# --- 定价：买卖报价的中间价 ---
@ese.allocation.pricing
def price(supply, demand, config):
    return (supply.price + demand.price) / 2.0

# --- 运行 ---
snapshots = ese.run(n_ticks=50)
ese.save(snapshots, prefix="town")
```

每轮输出一个快照字典，包含 `tick`、`gini`、`engel`、`unemployment`、`active_firms`。

---

## 5 FAQ

**Q：为什么没有内置投入产出表？**

A：实验者的策略不能直接访问全局的投入产出矩阵（A 矩阵）——那是上帝视野。策略只能从 MI（MarketIntelligence）提供的**统计局汇总报表**（行业均价、供给总量、基尼系数等，已加噪）来自行推断经济结构。这是本项目与那篇 2026 年论文最根本的差异：计划委员会也必须为估算误差付出代价。

**Q：货币总量为何恒定？**

A：剔除货币政策的干扰，单纯观察资源配置制度。如需模拟通胀，可在 Government 策略中实现货币增发——当然这是 AI 说的，我不这么认为，还是建议你不要动货币总量。等到有了金融系统再去玩吧。

**Q：为什么没有技术创新？**

A：因为不好做，以后再做。而且一旦做了这个，就有点像上帝开发一样，规定了技术的本质，一定会引来从哲学到经济学、社会学的争议。

**Q：你的金融系统呢？我想玩银行**

A：我们注意到，整个 ESE 某种程度上就是在扮演一种绝对精神。更具体的说，就像钢铁雄心4，扮演一个国家的绝对精神的同时，也大量利用了政府的强制工具—— ESE 也这样，扮演大手发力的同时也会用到大量银行工具。这个有些复杂，虽然比技术创新好做，但也要之后再说。有些更新的优先级会比技术创新高。