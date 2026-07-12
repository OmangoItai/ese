import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.simulator import Simulator
from core.registry import Registry
import examples.town_strategies as town
import pandas as pd
import matplotlib.pyplot as plt

# 注册策略
reg = Registry()
reg.register("firm", town.firm_strategy)
reg.register("household", town.household_strategy)
reg.register("government", town.government_strategy)
reg.register("allocation", town.town_allocation)

# 启动模拟（使用默认配置，但可指定自定义config）
sim = Simulator("config/default.yaml", "town_world.db")
sim.set_registry(reg)

# 运行50个Tick
snapshots = sim.run(n_ticks=50)

# 转为DataFrame并保存
df = pd.DataFrame(snapshots)
df.to_csv("town_results.csv", index=False)

# 简单绘图
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
axes[0, 0].plot(df["tick"], df["gini"], label="Gini")
axes[0, 0].set_title("Gini Coefficient")
axes[0, 1].plot(df["tick"], df["unemployment"], label="Unemployment", color="r")
axes[0, 1].set_title("Unemployment")
axes[1, 0].plot(df["tick"], df["engel"], label="Engel", color="g")
axes[1, 0].set_title("Engel Coefficient")
axes[1, 1].plot(df["tick"], df["active_firms"], label="Active Firms", color="m")
axes[1, 1].set_title("Active Firms")
for ax in axes.flatten():
    ax.legend()
plt.tight_layout()
plt.savefig("town_results.png")
print("Done. Saved town_results.csv and town_results.png")
