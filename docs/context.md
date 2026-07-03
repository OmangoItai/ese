【经济模拟引擎 ESE】对话上下文完整摘要与交接文档
1. 对话历程概括（我们是怎么走到这里的）
本次对话由一位计算机科学家/软件工程师（你）与一位经济学家（我）展开，核心是探索"如何用工程化手段构建一个可验证的经济制度对比实验平台"。

对话发展的五个关键阶段：

阶段一：文献解剖与祛魅（起点）

从一篇2026年6月的论文（Testing Centralized and Polycentric Computational Planning）切入。

你敏锐地指出该论文最大的工程漏洞：计划委员会被"白送"了精确的全局投入产出矩阵（A矩阵），这在哲学和现实操作上都是"上帝外挂"。

我们一致认定：任何有价值的模拟，算法只能从历史交易数据（Ledger）自行推断世界结构，不得直接读取"物理定律表"。

阶段二：微观粒度的争论与统一（核心转折）

你质疑该论文的"粒度造假"——它只用"行业总量"和"7个需求群体"，却输出"基尼系数"，这根本不算个体。

我们确立双核最小单位：模拟的最小主体必须是 "企业（Firm）+ 家庭（Household）"，生产必须最终流向C端消费才能计算满意度。

为了解决"生产如何到消费"，我们引入了结算器（Clearing House）作为独立于主体的"物理规则执行者"。

阶段三：经济学底层机制的补全（填空）

针对你"总觉得还差点什么"的直觉，我补充了经济模拟中缺席的四根时空支柱：

时间队列（生产延迟与坏单惩罚）；
存量折旧（资本磨损由主体自己决策）；
信息噪音（可插拔的谎报/瞒报噪声器）；
残酷退出（破产清算必须引发家庭失业与资产拍卖的连锁反应）。
我们重点攻克了"退出机制"的设计难点，确立了按"劳动力合约→资本品合约→金融合约"分层处理的会计原则。

阶段四：工程交付与UI设计（收尾）

你拒绝了"假大空"的论文式描述，要求一份"能跑、能写代码进去"的设计文档。

我输出了 《ESE v2.0工程实现设计书》，包含完整的文件目录树、核心类定义、热加载注册机制。

阶段五：架构深化与 10 个遗留问题的解决（本次对话）

本次对话在阶段四的基础上，对设计书进行了系统性审查和架构升级：

1. InformationFriction 模块补全：在 core/noise.py 中定义了可插拔噪声器，支持 gaussian / uniform / upward_bias（瞒报）/ downward_bias（谎报）四种噪声类型，全局 seed 保证实验可复现。

2. 生产函数解耦：ESE 不内置任何生产函数。用户在编写 FirmPolicy 时自行实现"投入→产出"逻辑。ESE 只提供库存读取、订单创建、账本查询等数据接口。

3. 匹配即制度（铁律五）：ClearingHouse 不再包含 match_market / match_plan。撮合算法本身是用户策略（MatchingPolicy），属于可插拔层。结算器只负责不可变的物理规则。

4. 抵押品机制升级：从"单向卖方冻结"升级为"双向冻结 + 动态履约率挂钩"。冻结比例 = base_ratio + (1 - fulfillment_rate) × 0.4。All-or-Nothing 全量结算。设计细节已写入 design.md 第 9 节。

5. 劳动力市场重构（v3→v4 再次简化）：劳动力作为特殊 Good（good_type="labor"），交易走标准 Order 流程，结算时特殊处理（雇佣+扣薪），无需独立的 LaborOrder 实体或 match_labor 方法。

6. 经济指标体系建立：core/reporter.py 内置 calc_gini、calc_engel、calc_unemployment、snapshot。（calc_cpi 暂不实现——缺乏跨期一篮子价格追踪。）

7. 五年尺度不印钞决策：M0 总量在单次实验中恒定，Government 保留 money_supply 占位属性以备未来扩展。五年尺度下流动性风险可控。

8. importlib 方案确认：优先 importlib（错误回溯友好），exec 为备选。

9. 初始世界：由用户在 seed_world.db（SQLite）中完整定义（Firm/Household/Good/Government 的初始属性），Simulator 不随机生成。

10. 商品定义：Good 实体使用 good_type: str（"food"/"labor"/"capital"/"consumer"/"raw_material"），替代布尔 is_food。新增 delivery_lag: int（行业默认交付延迟 Tick 数）。商品种类完全由用户配置。

2. 聚焦的痛点与有价值的正向共识（精华）
痛点1：禁止上帝视角。
投入产出表（A矩阵）只能是通过历史账本拟合出来的"统计估计值"，任何算法（无论计划还是市场）都必须为此付出"估算误差"的成本。这是本项目的灵魂。

痛点2：连接B端与C端。
生产不能悬空。清算器（Clearing House）必须在输出端将产品划拨到家庭账户，基尼系数和满意度必须基于家庭实际消费篮子计算，而非基于部门总产出。

痛点3：制度的本质是"结算规则"与"退出机制"。
我们的核心洞察是：计划与市场的优劣，不取决于他们怎么算产量，而取决于他们怎么处理错误和时间。破产清算（市场）和行政接管（计划）必须有对称且具体的会计实现。

正向范式一：策略与规则解耦。
实验者（用户）通过编写FirmStrategy、HouseholdStrategy、GovernmentStrategy，而结算器（ClearingHouse）作为不可篡改的内核保持不变。这是"制度数字风洞"的工程化落地。

正向范式二：匹配即制度。
计划经济和市场经济的本质区别不在于"如何算产量"，而在于"Bid/Ask 如何撮合"。因此撮合算法本身必须是用户策略而非内核。这使得实验者可以对比同一组主体在不同匹配规则下的宏观涌现。

3. 当前方案的缺点、缺陷与遗憾（开放性问题）
计算瓶颈未实测验证：
虽然在设计书中估算了规模（50企/500户为最佳体验），但 ClearingHouse 的 All-or-Nothing 全量结算和双向冻结机制在大规模并发下的实际性能表现尚属理论推演，缺乏基准测试代码。

内生技术创新缺失：
当前设计只允许用户通过自定义策略模拟技术进步，尚未设计"研发投入转化为随机技术突破"的内生闭环。这意味着长期（10年以上）模拟会失去"创造性毁灭"的宏观动力。

金融系统过度简化：
目前只涉及实物资产和基础现金，没有中央银行、内生信贷创造和利率传导机制。因此，无法模拟通胀预期或货币政策冲击带来的制度差异。

主体行为仍是"工程师逻辑"而非"心理学"：
虽然提供了让用户自定义策略的接口，但只要用户写的是确定性最优解（利润最大化），模拟就仍是"理性人"范畴。真正的"动物精神"或认知偏差需要靠实验者自己去写复杂的启发式算法，系统未提供默认的"非理性行为库"。

（以下为阶段五已解决的遗留问题，保留供参考）
已解决 — InformationFriction 模块：已在 design.md 中完成接口定义（core/noise.py），支持四种噪声类型、固定种子可复现。待编码实现。
已解决 — 抵押品冻结机制：已从单向升级为双向冻结 + 动态履约率挂钩，详细设计见 design.md 第 9 节。
已解决 — 匹配逻辑架构：已确立铁律五（匹配即制度），ClearingHouse 不再包含撮合算法。

阶段八（本次对话）：供需池架构与术语标准化
已解决 — 供需池重构：WorldState 新增 supply_pool 和 demand_pool（持久订单池），替代"每 Tick 新建→立即撮合→丢弃"的挥手即忘模式。订单现在在池中持续挂存，直到被分配、撤销或过期。
已解决 — Order 状态机：从 PENDING/FULFILLED/DEFAULTED 三态扩展为 OPEN → ALLOCATED → FULFILLED | DEFAULTED，外加 CANCELLED（代理撤单）和 EXPIRED（池中过期）两个终止态。
已解决 — tick() 从 11 步缩为 9 步：merge 旧步骤 5-7（for 循环）→ 步骤 5 Strategy（策略执行），旧步骤 8 → 步骤 6 Allocation（分配），去掉旧步骤 9（validate/freeze 已在 Strategy 内完成），新增加观测数据构建步骤和池过期清理步骤。
已解决 — 术语标准化：bid/ask/book → supply/demand/pool，MatchingPolicy → AllocationPolicy，FirmPolicy/HouseholdPolicy/GovernmentPolicy → FirmStrategy/HouseholdStrategy/GovernmentStrategy，步骤 5-7 统称 Strategy，步骤 8 改称 Allocation。
已解决 — 策略返回值结构化：个体策略从 List[Order] 改为 {"new": [...], "cancel": [...], "update": [...]} 三字段字典，代理可同时新建、撤单、修改池订单。
已解决 — 池过期核化：ClearingHouse 新增 expire_stale_orders(state, expire_ticks)，expire_ticks 为用户可配全局参数（default.yaml 新增 order_expire_ticks）。
已解决 — obs 新增池字段：my_supply_orders 和 my_demand_orders，代理可在策略中看到自己当前池订单以决定修改/撤单。
已解决 — 策略调用顺序：内核按 F→H→G 固定顺序依次调用 FirmStrategy/HouseholdStrategy/GovernmentStrategy，obs 一次性构建，策略只读不写 state。
已解决 — tick() 重写：从混乱的双重 _process_new_orders 重构为紧凑 9 步流水线（4 步内核 + 2 步用户策略 + 3 步内核），结算在前策略在后。
已解决 — 策略槽精简：从 5 个（FirmPolicy/HouseholdPolicy/GovernmentPolicy/MatchingPolicy/ProductionFn）减为 4 个，删除 ProductionFn（生产逻辑内化于 FirmPolicy），删除 match_labor（劳动力通过 good_type="labor" 走标准 Order 流程）。
已解决 — Good 类型化：is_food: bool → good_type: str，新增 delivery_lag: int。LaborOrder 实体完全删除。
已解决 — Observation/Ledger 定义：obs 字典结构明确定义（全员公开 + 噪声注入），Ledger 类和 TradeRecord 定义补全。
已解决 — 政府行为补全：tick() 中新增征税、失业金发放步骤，Government 新增 unemployment_benefit 字段。
已解决 — 破产触发位置：从独立 handle_bankruptcies 改为 settle_order 内部 cash<0 时立即触发 liquidate_firm。
已解决 — 市场价格追踪：ClearingHouse 新增 price_history 和 get_market_price_range，用于破产库存折现定价。
已解决 — 信息可见性决策：全员公开统一结构，仅经 InformationFriction 加噪区分制度（计划 noise=none，市场 noise=gaussian）。不设 visibility_rules。

4. 给下一次AI（或你自己）开启对话的起始指示词
起始指示（复制此段发给新AI）：

"我们需要继续推进一个名为ESE（Economic Simulation Engine）的经济模拟器项目。此前已完成详细设计书（design.md v4.0），架构已稳定。

当前最高优先级任务：根据 design.md 继续推进内核实现。重点实现：

core/clearing_house.py 中的清算逻辑：
  - calc_dynamic_collateral_ratio：基于履约率的动态冻结比例
  - validate_order / freeze_collateral / release_collateral / forfeit_collateral：双向冻结机制
  - settle_order：All-or-Nothing 全量结算（含 good_type="labor" 的特殊处理）
  - liquidate_firm：破产清算（员工补偿金优先于股东）
  - price_history + get_market_price_range：市场价格追踪

core/noise.py 中的 InformationFriction 类（四种噪声类型、固定种子）。

core/reporter.py 中的 calc_gini、calc_engel、calc_unemployment、snapshot。

core/ledger.py 中的 TradeRecord 和 Ledger（追加、按主体查询、按商品查均价）。

core/simulator.py 中的 9 步 tick() 循环和 run(n_ticks) 批量运行方法。

必须遵守的约束：

严禁在任何模块中导入全局精确的 A 矩阵。

匹配逻辑（AllocationPolicy）不属于内核，结算器只负责物理规则。

所有随机性必须通过 InformationFriction 模块注入，以保证实验可复现。

无 ProductionFn 独立槽位（生产逻辑内化于 FirmStrategy），无 LaborOrder 实体（劳动力为 good_type='labor' 的 Good），无 match_labor 方法（由统一 match 撮合）。

用户希望优先看到一个能跑通'1个Tick'的最小原型（Minimal Viable Prototype），展示：企业报价→ClearingHouse结算→抵押品冻结/释放→家庭收货→reporter计算满意度 的完整闭环。使用硬编码策略先跑通数据流。"

5. 关键设计决策速查（给 AI 代理的快速参考）
项                      | 决策
————————————————————————|————————————————————————
冻结机制                | 双向冻结，动态比例 0.1~0.5，All-or-Nothing
匹配/分配              | 不在内核中，由用户编写 AllocationPolicy（单一 allocate 方法）；旧称 MatchingPolicy
决策编排                | tick() 步骤 5-7 由内核按 F→H→G 固定顺序调用个体策略，无 DecisionOrchestrator
生产函数                | 不在内核中，生产逻辑内化于 FirmStrategy（无 ProductionFn 独立槽位）
劳动力市场              | 劳动力为 good_type='labor' 的 Good，交易走标准 Order，结算时特殊处理
噪声注入                | core/noise.py，必须经此模块读取账本数据
信息可见性              | 全员公开统一 obs 结构，仅经噪声区分制度（计划=none，市场=gaussian）
初始世界                | 用户通过 SQLite（seed_world.db）完整定义，Simulator 不随机生成
Good 定义               | good_type: str（food/labor/capital/consumer/raw_material），delivery_lag: int
订单池                  | supply_pool / demand_pool 持久挂存订单，AllocationPolicy 从池中分配
订单状态机              | OPEN → ALLOCATED → FULFILLED | DEFAULTED | CANCELLED | EXPIRED
池过期                  | expire_stale_orders(state, expire_ticks)，expire_ticks 用户可配（默认 30）
Tick 步数               | 9 步（旧 11 步）