# ESE 项目更新文档 v2.0

> 基于现有代码结构的重构方案，涵盖策略注册、定价机制、策略架构、数据指标、MarketIntelligence 和数据层六大模块。

---

## 0. 装饰器注册（统一基础设施）

### 0.1 目标

所有策略注册统一使用装饰器语法，提升代码可读性和编写效率。

### 0.2 实现方案

扩展 `core/registry.py`，为所有插槽提供装饰器：

```python
# core/registry.py
from functools import wraps

class Registry:
    def __init__(self):
        self._slots = {
            "firm": None,
            "household": None,
            "government": None,
            "allocation": None,
            "pricing": None,      # 新增
        }
        self._tagged_strategies = {
            "firm": {},
            "household": {},
            "government": {},
        }

    def register(self, slot: str, tag: str = None):
        """统一装饰器：注册策略到指定插槽"""
        def decorator(func):
            if tag is None:
                self._slots[slot] = func
            else:
                if slot not in self._tagged_strategies:
                    self._tagged_strategies[slot] = {}
                self._tagged_strategies[slot][tag] = func
            return func
        return decorator

    def get(self, slot: str, tag: str = None):
        if tag:
            return self._tagged_strategies.get(slot, {}).get(tag)
        return self._slots.get(slot)
```

### 0.3 使用示例

```python
# 注册企业主策略（无标签）
@reg.register("firm")
def firm_strategy(market_intelligence, firm, goods):
    tag_strategy = reg.get("firm", firm.strategy_tag)
    if tag_strategy:
        return tag_strategy(market_intelligence, firm, goods)
    return default_firm_strategy(market_intelligence, firm, goods)

# 注册标签策略
@reg.register("firm", tag="farm")
def farm_strategy(market_intelligence, firm, goods):
    pass

@reg.register("firm", tag="workshop")
def workshop_strategy(market_intelligence, firm, goods):
    pass
```

---

## 1. 定价策略：从分配策略中独立

### 1.1 目标

定价逻辑从 allocation 中剥离，作为独立的 `pricing` 插槽，必须手动注册到分配逻辑中。

### 1.2 实现方案

**Step 1：在 Registry 中新增 pricing 插槽**

```python
reg.register("pricing", my_pricing_rule)
```

**Step 2：定价策略函数签名**

```python
def pricing_rule(supply_order: Order, demand_order: Order, config: dict) -> float:
    """
    根据供需订单和配置，返回成交价。

    内置机制：
    - "ask": 取卖方报价
    - "bid": 取买方报价
    - "mid": 取 (ask + bid) / 2
    - "negotiated": 纳什议价（可扩展）
    """
    mechanism = config.get("pricing_mechanism", "mid")
    if mechanism == "ask":
        return supply_order.price
    elif mechanism == "bid":
        return demand_order.price
    elif mechanism == "mid":
        return (supply_order.price + demand_order.price) / 2.0
    # ... 其他机制
```

**Step 3：分配策略中调用定价策略**

```python
@reg.register("allocation")
def town_allocation(obs, supply_pool, demand_pool, goods, config):
    matched = []
    # ... 匹配逻辑（找出谁和谁成交）...
    for s, d in matched_pairs:
        price = reg.get("pricing")(s, d, config)
        matched.append(create_matched_order(s, d, price))
    return matched, remaining_supply, remaining_demand
```

### 1.3 配置文件支持

在 `config/default.yaml` 中增加：

```yaml
pricing_mechanism: "mid"  # ask | bid | mid | negotiated
```

---

## 2. 策略架构：标签化 + 组合执行

### 2.1 目标

- 对不同标签的主体注册不同的策略函数
- 企业/家庭/政府主策略中，每个主体可分别执行标签对应的策略函数
- 用户可手动编写执行顺序（先执行哪些标签，再执行哪些标签）

### 2.2 实现方案

**Step 1：为主体增加 `strategy_tag` 和 `strategy_order` 字段**

```python
# core/entities.py
class Firm:
    def __init__(self, ...):
        self.strategy_tag = "default"      # 标签
        self.strategy_order = ["default"]  # 执行顺序（用户可配置）
```

**Step 2：主策略支持按标签分发 + 按顺序执行**

```python
@reg.register("firm")
def firm_strategy(market_intelligence, firm, goods):
    result = {"new": [], "cancel": [], "update": []}

    for tag in firm.strategy_order:
        tag_strategy = reg.get("firm", tag)
        if tag_strategy:
            partial = tag_strategy(market_intelligence, firm, goods)
            result = merge_strategy_results(result, partial)

    return result


def merge_strategy_results(base, override):
    """后执行的策略覆盖先执行的同名订单"""
    merged = {"new": [], "cancel": [], "update": []}
    # ... 合并逻辑
    return merged
```

**Step 3：用户配置示例**

```python
farm = Firm(
    id=101,
    strategy_tag="farm",
    strategy_order=["production", "pricing", "hiring"]
)

# 或更细粒度
farm.strategy_order = [
    "farm_production",
    "cost_plus_pricing",
    "passive_hiring",
]
```

### 2.3 设计哲学：组合优于继承

不采用类继承体系，而是采用行为组件（Component）组合的方式：

```python
# 给企业打组件标签
farm = Firm(components=["production_food", "pricing_cost_plus", "hiring_passive"])
workshop = Firm(components=["production_tool", "pricing_market_follower", "hiring_active"])

# 策略路由器按组件顺序执行
def firm_strategy(obs, firm):
    result = {}
    for comp in firm.components:
        result.update(STRATEGY_COMPONENTS[comp](obs, firm))
    return result
```

> 优势：新增策略只需写一个新组件函数，贴给任意企业，零继承，零侵入。

---

## 3. 数据指标：硬编码输出列表

### 3.1 目标

在 Simulator 中内置 Reporter，硬编码输出以下三类数据。

### 3.2 指标列表

**宏观指标**

| 指标 | 计算方式 | 输出文件 |
|------|----------|----------|
| GDP | 所有最终品的市场价值总和 | `macro.csv` |
| CPI | 一篮子商品本期均价 / 上期均价 - 1 | `macro.csv` |
| 基尼系数 | 已有实现 | `macro.csv` |
| 失业率 | 已有实现 | `macro.csv` |
| 劳动收入份额 | 所有家庭工资总和 / GDP | `macro.csv` |

**中观指标**

| 指标 | 计算方式 | 输出文件 |
|------|----------|----------|
| 行业集中度 (CR3) | 该行业前3家企业产出 / 该行业总产出 | `meso.csv` |
| 行业平均利润率 | 行业总利润 / 行业总营收 | `meso.csv` |
| 行业库存周转率 | 行业销售成本 / 平均库存 | `meso.csv` |

**微观指标**

| 指标 | 计算方式 | 输出文件 |
|------|----------|----------|
| 净资产轨迹 | 每个主体（现金 + 库存市值）随时间变化 | `micro/` 文件夹 |

### 3.3 输出格式

```text
outputs/
├── macro.csv          # 全局时序指标
├── meso.csv           # 分行业时序指标
├── micro/
│   ├── firms.csv      # 每个企业每 N tick 的状态
│   ├── households.csv # 每个家庭每 N tick 的状态
│   └── government.csv # 政府每 N tick 的状态
└── trades.csv         # 所有成交明细
```

### 3.4 参考标准

施工时参考以下两个行业标准：

- **ODD+D 协议** (Grimm et al., 2013)：用于规范化描述 ABM 模型。重点记录初始条件、主体行为规则、观测指标。
- **STRESS-ABS 指南** (Monks et al., 2018)：20 项检查清单，用于提高 ABM 模拟研究的可重复性。重点：输出数据必须包含随机种子、必须输出原始微观数据而非仅汇总数据。

**核心原则两条：**

1. 记录所有初始条件和随机种子
2. 输出原始微观数据（不只是汇总指标）

---

## 4. MarketIntelligence：命名与接口

### 4.1 命名决策

`obs` → `MarketIntelligence`（市场情报）

**理由：**

- 经济学上精准：真实世界中，企业看 PMI、美联储看 CPI——这些都是"情报"
- 工程上自然：天然包含"不完美"的意味（情报可能有误、延迟、噪声）
- 双向兼容：计划经济（国家统计局情报）和市场经济（公开市场情报）通用

### 4.2 数据结构接口

```python
# core/market_intelligence.py
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class MarketIntelligence:
    """传递给所有策略的市场情报"""

    # === 第1层：宏观统计（从报表汇总，可能存在偏差）===
    tick: int
    gdp: float
    cpi: float                          # 环比
    unemployment_rate: float
    avg_wage: float
    gini: float
    labor_income_share: float           # 劳动收入份额

    # === 第2层：中观市场信号（从订单簿观察）===
    sector_avg_price: Dict[int, float]      # {good_id: 均价}
    sector_total_supply: Dict[int, float]   # {good_id: 总挂单量}
    sector_total_demand: Dict[int, float]   # {good_id: 总询价量}
    sector_inventory_ratio: Dict[int, float]# {good_id: 库存/产能比}
    sector_cr3: Dict[int, float]            # {good_id: 行业集中度}

    # === 第3层：公共信息（政策/公告）===
    tax_rate: float
    central_bank_rate: float                # 基准利率
    government_announcement: Optional[str]  # 政府指导价/配额（计划经济专用）
    unemployment_benefit: float

    # === 第4层：信息摩擦（可配置）===
    data_lag: int = 0                       # 数据延迟（显示的是N期前的数据）
    reporting_bias: float = 1.0             # 上报偏差系数（如企业虚报产出1.2倍）
```

### 4.3 构建器

```python
# core/market_intelligence.py
class MarketIntelligenceBuilder:
    """构建 MarketIntelligence，支持配置信息摩擦"""

    def __init__(self, config: dict):
        self.lag = config.get("data_lag", 0)
        self.bias = config.get("reporting_bias", 1.0)
        self.history = []  # 存储历史数据用于延迟

    def build(self, sim_state: dict) -> MarketIntelligence:
        raw = self._collect_raw(sim_state)
        biased = self._apply_bias(raw)
        delayed = self._apply_lag(biased)
        return MarketIntelligence(**delayed)

    def _collect_raw(self, sim_state: dict) -> dict:
        """从模拟器状态收集原始数据"""
        pass

    def _apply_bias(self, data: dict) -> dict:
        """应用上报偏差"""
        data["gdp"] *= self.bias
        return data

    def _apply_lag(self, data: dict) -> dict:
        """应用数据延迟"""
        self.history.append(data)
        if len(self.history) > self.lag + 1:
            return self.history[-self.lag - 1]
        return data
```

### 4.4 策略中的使用

```python
def firm_strategy(market_intelligence: MarketIntelligence, firm, goods):
    cpi = market_intelligence.cpi
    sector_price = market_intelligence.sector_avg_price.get(good_id, 2.0)
    tax_rate = market_intelligence.tax_rate

    if cpi > 1.05:
        price = sector_price * 1.1   # 通胀高企 → 涨价
    else:
        price = sector_price * 1.0
    # ...
```

---

## 5. 数据层：三层架构

### 5.1 目标

- **底层（存储）**：保留 SQLite，仅作为序列化存储
- **中间层（Repository）**：封装 DataStore 类，提供链式查询，消灭手写 SQL
- **扩展性（API/插件）**：查询结果返回 `pandas.DataFrame`，未来可扩展 RESTful API

### 5.2 架构图

```text
┌─────────────────────────────────────────────────────┐
│                   用户代码层                         │
│  db.firms.insert(...).commit()                     │
│  df = db.firms.where(id=101).to_dataframe()        │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│               Repository 层 (DataStore)             │
│  - 链式查询 API                                     │
│  - 自动翻译为 SQL                                   │
│  - 返回 pandas.DataFrame                           │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│              存储层 (SQLite)                        │
│  - 仅作为序列化存储                                 │
│  - 不手写 SQL                                      │
└─────────────────────────────────────────────────────┘
```

### 5.3 Repository 接口设计

```python
# core/datastore.py
import sqlite3
import pandas as pd
from typing import List, Dict, Any, Optional

class Query:
    """链式查询构建器"""
    def __init__(self, conn, table: str):
        self.conn = conn
        self.table = table
        self._filters = []
        self._limit = None
        self._order_by = None

    def where(self, **kwargs):
        self._filters.append(kwargs)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def order_by(self, col: str, desc: bool = False):
        self._order_by = (col, desc)
        return self

    def to_dataframe(self) -> pd.DataFrame:
        sql = self._build_sql()
        return pd.read_sql_query(sql, self.conn)

    def first(self) -> Optional[Dict]:
        df = self.limit(1).to_dataframe()
        return df.to_dict('records')[0] if not df.empty else None

    def all(self) -> List[Dict]:
        return self.to_dataframe().to_dict('records')

    def _build_sql(self) -> str:
        pass


class Table:
    """表操作入口"""
    def __init__(self, conn, table_name: str):
        self.conn = conn
        self.table_name = table_name

    def insert(self, **kwargs) -> 'Table':
        columns = ', '.join(kwargs.keys())
        placeholders = ', '.join(['?' for _ in kwargs])
        sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        self.conn.execute(sql, list(kwargs.values()))
        return self

    def insert_many(self, records: List[Dict]) -> 'Table':
        if not records:
            return self
        columns = ', '.join(records[0].keys())
        placeholders = ', '.join(['?' for _ in records[0]])
        sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        values = [[r.get(col) for col in records[0].keys()] for r in records]
        self.conn.executemany(sql, values)
        return self

    def query(self) -> Query:
        return Query(self.conn, self.table_name)


class DataStore:
    """数据存储主入口"""
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        self.goods = Table(self.conn, "goods")
        self.firms = Table(self.conn, "firms")
        self.households = Table(self.conn, "households")
        self.governments = Table(self.conn, "governments")
        self.firm_inventory = Table(self.conn, "firm_inventory")
        self.household_inventory = Table(self.conn, "household_inventory")
        self.firm_employees = Table(self.conn, "firm_employees")

        # 新增：结果表
        self.macro = Table(self.conn, "macro_results")
        self.meso = Table(self.conn, "meso_results")
        self.trades = Table(self.conn, "trades")
        self.agent_states = Table(self.conn, "agent_states")

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def to_dataframe(self, sql: str) -> pd.DataFrame:
        """直接执行 SQL 返回 DataFrame（高级用户使用）"""
        return pd.read_sql_query(sql, self.conn)
```

### 5.4 使用示例（替代手写 SQL）

```python
# 旧方式（手写 SQL）—— 废弃
# c.execute("INSERT INTO firms VALUES (?,?,?,?,?)", (101, 1000.0, 50.0, 0.0, 1))

# 新方式（链式 API）
db = DataStore("town_world.db")
db.firms.insert(id=101, cash=1000.0, capacity=50.0, collateral=0.0, is_active=1)
db.firms.insert_many([
    {"id": 102, "cash": 1000.0, "capacity": 30.0, "collateral": 0.0, "is_active": 1},
])

# 查询
df = db.firms.query().where(is_active=1).order_by("cash", desc=True).to_dataframe()
firm = db.firms.query().where(id=101).first()

db.commit()
db.close()
```

### 5.5 指标聚合支持

指标计算在内存中完成（纯 Python），通过 DataStore 写入结果表：

```python
# core/metrics.py
class MetricsCalculator:
    @staticmethod
    def calc_macro(agents: dict, orders: list, tick: int) -> dict:
        """计算宏观指标，返回字典"""
        return {
            "tick": tick,
            "gdp": MetricsCalculator._calc_gdp(agents),
            "cpi": MetricsCalculator._calc_cpi(agents),
            "gini": MetricsCalculator._calc_gini(agents),
            "unemployment": MetricsCalculator._calc_unemployment(agents),
            "labor_income_share": MetricsCalculator._calc_labor_share(agents),
        }

    @staticmethod
    def calc_meso(agents: dict, goods: dict, tick: int) -> pd.DataFrame:
        """计算中观指标，返回 DataFrame"""
        pass
```

Simulator 中调用：

```python
def run(self, n_ticks: int):
    for tick in range(n_ticks):
        self.step()
        macro = MetricsCalculator.calc_macro(self.agents, self.orders, tick)
        meso = MetricsCalculator.calc_meso(self.agents, self.goods, tick)
        self.db.macro.insert(**macro)
        self.db.meso.insert_many(meso.to_dict('records'))
    self.db.commit()
```

---

## 6. 施工优先级

| 优先级 | 模块 | 工作量 | 依赖 |
|--------|------|--------|------|
| **P0** | 装饰器注册 (`registry.py`) | 小 | 无 |
| **P0** | 数据层 (`datastore.py`) | 中 | 无 |
| **P1** | 定价策略独立 (`pricing` 插槽) | 小 | P0 |
| **P1** | MarketIntelligence 数据结构 | 小 | P0 |
| **P2** | 策略标签化 + 组合执行 | 中 | P0 |
| **P2** | 指标计算器 (`metrics.py`) | 中 | P0 |
| **P3** | Reporter 硬编码输出 | 中 | P1, P2 |
| **P3** | 迁移 `generate_town.py` 到新 API | 小 | P0 |

---

## 7. 文件结构变更

```text
ese/
├── core/
│   ├── registry.py             # 修改：装饰器 + 标签支持
│   ├── datastore.py            # 新增：Repository 层
│   ├── market_intelligence.py  # 新增：MarketIntelligence 数据结构 + 构建器
│   ├── metrics.py              # 新增：指标计算器
│   ├── simulator.py            # 修改：集成 DataStore + Metrics
│   ├── reporter.py             # 修改：硬编码输出
│   └── entities.py             # 修改：增加 strategy_tag, strategy_order
├── config/
│   └── default.yaml            # 修改：增加 pricing_mechanism, data_lag, reporting_bias
├── examples/
│   └── town_strategies.py      # 重构：标签化策略
└── tools/
    └── generate_town.py        # 重构：使用 DataStore API
```
