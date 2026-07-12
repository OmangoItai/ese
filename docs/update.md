# ESE 项目更新文档 v2.0

> 基于现有代码结构的重构方案，涵盖策略注册、定价机制、策略架构、数据指标、MarketIntelligence 和数据层六大模块。

---

## 0. 策略注册（Engine 统一入口）

### 0.1 目标

所有策略注册统一走 `Engine` 实例，槽名即装饰器方法名，无需魔术字符串。

### 0.2 实现方案

新建 `ese/__init__.py`（公共 facade）和 `core/engine.py`（`Engine` 类）。内部用私有的 `core/_registry.py`（`_StrategyRegistry`）管理查表，用户不接触。

`Engine` 提供四个装饰器属性：

| 属性 | 注册什么 | 标签装饰器 | 标签调用方法 |
|------|----------|------------|------------|
| `ese.firm` | 企业调度器（每 tick 每企业调用一次） | `ese.firm.label("x")` | `ese.firm.use("x", mi, firm, goods)` |
| `ese.household` | 家庭调度器 | `ese.household.label("x")` | `ese.household.use("x", mi, hh, goods)` |
| `ese.government` | 政府调度器 | `ese.government.label("x")` | `ese.government.use("x", mi, gov, goods)` |
| `ese.allocation` | 分配策略 + 定价子槽 | — | `ese.allocation.pricing`（定价装饰器） |

### 0.3 使用示例

```python
from ese import Engine

ese = Engine("config/default.yaml", "town_world.db")

# ==== 企业：调度器 + 标签策略 ====
@ese.firm
def firm_orchestrator(mi, firm, goods):
    """每 tick 每企业调用一次，负责分发到标签策略"""
    return ese.firm.use(firm.strategy_label, mi, firm, goods)

@ese.firm.label("farm")
def farm_strategy(mi, firm, goods):
    ...

@ese.firm.label("workshop")
def workshop_strategy(mi, firm, goods):
    ...

# ==== 分配 + 定价 ====
@ese.allocation
def town_allocation(mi, supply, demand, goods, pricing=None):
    """pricing 参数由引擎自动注入"""
    price = pricing(s, d, {}) if pricing else (s.price + d.price) / 2
    ...

@ese.allocation.pricing
def mid_pricing(supply, demand, config):
    return (supply.price + demand.price) / 2

# ==== 运行 ====
snapshots = ese.run(n_ticks=50)
```

### 0.4 语义约定

- `@ese.firm`：注册**调度器**（orchestrator）——每 tick 被引擎对每个企业调用一次。调度器自己决定按什么顺序、用什么条件分发到标签策略。
- `@ese.firm.label("x")`：注册**标签策略**（labeled strategy）——被调度器通过 `ese.firm.use("x", ...)` 调用。调度器和标签策略不是并列关系，而是包含关系。
- `ese.firm.use(label, mi, entity, goods)`：调度器内部触发标签策略。找不到对应标签时发出 `RuntimeWarning` 并返回空 result（`{"new": [], "cancel": [], "update": []}`），不抛异常。
- `strategy_label`：Firm/Household/Government 实体上的字段（`str`，默认 `"default"`），定义在种子数据库中。引擎或调度器根据此字段决定哪个标签策略生效。没有被分配到标签策略的实体，调度器应发出运行时警告。

---

## 1. 定价策略：作为 allocation 的子槽

### 1.1 目标

定价逻辑从 allocation 中剥离，挂载为 `ese.allocation.pricing`。引擎在执行 allocation 时自动解析定价函数并注入为参数。

### 1.2 实现方案

**Step 1：注册定价策略**

```python
@ese.allocation.pricing
def mid_pricing(supply_order, demand_order, config) -> float:
    """根据供需订单返回成交价"""
    return (supply_order.price + demand_order.price) / 2
```

**Step 2：分配策略接受 pricing 参数（引擎自动注入）**

```python
@ese.allocation
def town_allocation(mi, supply_pool, demand_pool, goods, pricing=None):
    matched = []
    for s, d in matched_pairs:
        price = pricing(s, d, {}) if pricing else (s.price + d.price) / 2
        matched.append(create_matched_order(s, d, price))
    return matched, remaining_supply, remaining_demand
```

**Step 3：引擎内部注入**

```python
# simulator.py —— _execute_allocation
allocate_fn = self._reg.get("allocation")
pricing_fn = self._reg.get_pricing()
matched, rem_s, rem_d = allocate_fn(mi, supply, demand, goods, pricing_fn)
```

定价函数签名：`(supply_order: Order, demand_order: Order, config: dict) -> float`

### 1.3 配置文件支持

在 `config/default.yaml` 中增加：

```yaml
pricing_mechanism: "mid"  # ask | bid | mid | negotiated
```

---

## 2. 策略架构：调度器 + 标签策略

### 2.1 目标

- 对不同标签的主体注册不同的策略函数（`@ese.firm.label("x")`）
- 企业/家庭/政府主策略（`@ese.firm`）是调度器，负责按主体标签分发到具体策略
- 调度器自行控制执行顺序（先处理哪些标签的企业，再处理哪些）

### 2.2 实现方案

**Step 1：为主体增加 `strategy_label` 字段**

```python
# core/entities.py
@dataclass
class Firm:
    id: int
    ...
    strategy_label: str = "default"
```

种子数据库中指定每类企业的标签：

```sql
-- firms 表
INSERT INTO firms (id, cash, capacity, strategy_label) VALUES
    (101, 1000.0, 50.0, 'farm'),
    (102, 500.0,  30.0, 'workshop');
```

**Step 2：调度器按标签分发**

```python
@ese.firm
def firm_orchestrator(mi, firm, goods):
    """每 tick 每企业调用一次，查看 firm.strategy_label 并分发"""
    return ese.firm.use(firm.strategy_label, mi, firm, goods)

@ese.firm.label("farm")
def farm_strategy(mi, firm, goods):
    result = {"new": [], "cancel": [], "update": []}
    # 农场逻辑
    return result

@ese.firm.label("workshop")
def workshop_strategy(mi, firm, goods):
    result = {"new": [], "cancel": [], "update": []}
    # 工坊逻辑
    return result
```

调度器可以更复杂——按编排顺序、合并多个标签策略的结果：

```python
@ese.firm
def composed_orchestrator(mi, firm, goods):
    result = {"new": [], "cancel": [], "update": []}
    for label in firm.strategy_order:
        partial = ese.firm.use(label, mi, firm, goods)
        result = merge_strategy_results(result, partial)
    return result
```

**Step 3：`ese.firm.use(label, ...)` 行为约定**

- 找到标签策略 → 调用并返回结果
- 找不到标签策略 → `warnings.warn()` + 返回 `{"new": [], "cancel": [], "update": []}`
- 不抛异常

### 2.3 设计哲学：组合优于继承

不采用类继承体系，而是采用调度器 + 标签策略的组合方式：

- **调度器**（`@ese.firm`）负责编排逻辑（先处理谁、后处理谁、结果如何合并）
- **标签策略**（`@ese.firm.label("x")`）是原子的策略实现，只关心"这类企业该做什么"

新增策略只需写一个新标签函数并用 `@ese.firm.label("x")` 注册，调度器无需改动（只要调度器通配分发）。

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
| **P0** | Engine + 策略注册 (`ese/` `core/engine.py` `core/_registry.py`) | 小 | 无 |
| **P0** | 数据层 (`datastore.py`) | 中 | 无 |
| **P1** | MarketIntelligence 数据结构 | 小 | P0 |
| **P2** | 策略标签化（调度器 + `ese.firm.label`） | 中 | P0 |
| **P2** | 指标计算器 (`metrics.py`) | 中 | P0 |
| **P3** | Reporter 硬编码输出 | 中 | P1, P2 |
| **P3** | 迁移 `generate_town.py` 到新 API | 小 | P0 |

---

## 7. 文件结构变更

```text
ese/                            # 项目根
├── ese/                        # 新增：公共包（对外唯一入口）
│   └── __init__.py             # from core.engine import Engine; re-export 实体类
├── core/
│   ├── _registry.py            # 新增：_StrategyRegistry（内部查表，用户不碰）
│   ├── engine.py               # 新增：Engine + _Slot + _AllocationSlot（用户入口）
│   ├── registry.py             # 删除：功能迁移到 _registry.py + engine.py
│   ├── datastore.py            # 新增：Repository 层
│   ├── market_intelligence.py  # 新增：MarketIntelligence 数据结构 + 构建器
│   ├── metrics.py              # 新增：指标计算器
│   ├── simulator.py            # 修改：接受 _StrategyRegistry，use _reg.get() 分发，注入 pricing
│   ├── reporter.py             # 修改：硬编码输出
│   └── entities.py             # 修改：Firm/Household/Government 增加 strategy_label: str
├── config/
│   └── default.yaml            # 修改：增加 pricing_mechanism, data_lag, reporting_bias
├── examples/
│   └── town_strategies.py      # 重构：@ese.firm / @ese.firm.label 装饰器风格
└── tools/
    └── generate_town.py        # 重构：firms/households 表增加 strategy_label 列
```
