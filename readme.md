# ESE (Economic Simulation Engine) 说明

**一句话：ESE 是一个回合制经济沙盒。每一轮（Tick），企业、家庭、政府各自执行你编写的策略，产生买卖订单，订单匹配后进行交付和结算。运行 N 轮后，你得到一个国家的经济演化数据。**

## 这玩意儿到底在跑什么？

想象一个简单的经济循环：

1. **每个 Tick 开始**，引擎先把上一轮匹配好的订单完成交付（一手交钱、一手交货），并把交不起货的标记为违约、该破产的破产。
2. **企业执行策略**：根据当前库存、市价、员工情况，决定生产多少、定什么价、雇多少人，生成买卖订单。
3. **家庭执行策略**：根据收入、储蓄、就业状态，决定买什么、找什么工作，生成订单。
4. **政府执行策略**：根据税收，决定是否发福利、调整税率，生成订单。
5. **分配策略匹配订单**：遍历供需池，把能对上的买卖单配对（按价格优先、按配额、按你写的任何规则）。
6. **引擎再对"他人"的财务数据加噪声**（模拟现实中的信息不全），作为下一轮决策的依据。
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

---

## 快速开始

### 1. 环境准备

```bash
cd ese
uv sync
```

### 2. 生成初始世界

```bash
uv run python config/generate_seed.py
```

### 3. 配置实验参数（`config/default.yaml`）

```yaml
seed: 42
noise_type: "gaussian"       # none / gaussian / upward_bias / downward_bias
base_collateral_ratio: 0.1
order_expire_ticks: 30
```

### 4. 编写策略

在 `policies/` 目录编写以下策略函数并注册到 Registry：

| 策略插槽 | 职责 |
|---|---|
| FirmStrategy | 企业定价、生产、投资 |
| HouseholdStrategy | 家庭消费、劳动力供给 |
| GovernmentStrategy | 征税、发放福利 |
| AllocationPolicy | 匹配买卖订单（**制度灵魂**：按价格优先→市场；按配额→计划） |

### 5. 运行实验

```python
from core.simulator import Simulator
from policies.registry import Registry
import policies.demo_strategies as demo

reg = Registry()
reg.register("firm", demo.firm_strategy)
reg.register("household", demo.household_strategy)
reg.register("allocation", demo.demo_allocation)

sim = Simulator("config/default.yaml", "seed_world.db")
sim.set_registry(reg)
snapshots = sim.run(n_ticks=30)

import pandas as pd
pd.DataFrame(snapshots).to_csv("results.csv", index=False)
```

---

## 输出指标

| 字段 | 含义 |
|---|---|
| `gini` | 基尼系数（贫富差距） |
| `engel` | 恩格尔系数（食品支出占比） |
| `unemployment` | 失业率 |
| `active_firms` | 活跃企业数 |

## FAQ

**Q：为什么没有内置投入产出表？**

A：实验者的策略只能通过 Ledger 历史交易数据，和带噪声的 Observation（obs）观测数据（企业和家庭上报的数据）自行推断，模拟现实中统计局的估计误差。

**Q：货币总量为何恒定？**

A：剔除货币政策的干扰，单纯观察资源配置制度。如需模拟通胀，可在 Government 策略中实现货币增发——当然这是 AI 说的，我不这么认为，还是建议你不要动货币总量。等到有了金融系统再去玩吧。

**Q：为什么没有技术创新？**

A：因为不好做，以后再做。而且一旦做了这个，就有点像上帝开发一样，规定了技术的本质，一定会引来从哲学到经济学、社会学的争议。

**Q：你的金融系统呢？我想玩银行**

A：我们注意到，整个 ESE 某种程度上就是在扮演一种绝对精神。更具体的说，就像钢铁雄心4，扮演一个国家的绝对精神的同时，也大量利用了政府的强制工具—— ESE 也这样，扮演大手发力的同时也会用到大量银行工具。这个有些复杂，虽然比技术创新好做，但也要之后再说。更新的优先级会比技术创新高。