import os
from typing import Callable, Dict, List

from core._registry import _StrategyRegistry
from core.entities import AgentOrders
from core.simulator import Simulator


class _Slot:
    def __init__(
        self,
        registry: _StrategyRegistry,
        slot_name: str,
        get_entities_fn: Callable,
        simulator: Simulator,
    ):
        self._reg = registry
        self._name = slot_name
        self._get_entities = get_entities_fn
        self._sim = simulator

    def __call__(self, func):
        self._reg.set_primary(self._name, func)
        return func

    def apply(self, label: str, leaf_fn, **params):
        state = self._sim.state
        results = []
        for entity in self._get_entities():
            if hasattr(entity, "is_active") and not entity.is_active:
                continue
            if label not in entity.labels:
                continue
            my_orders = entity.outstanding_orders(state.all_orders)
            orders = AgentOrders(my_orders, self._sim.order_factory)
            result = leaf_fn(entity, orders, **params)
            results.append(result)
            self._sim._dispatch_agent_result(state, orders._consume())
        return results


class _AllocationSlot(_Slot):
    def __init__(
        self,
        registry: _StrategyRegistry,
        get_entities_fn: Callable,
        simulator: Simulator,
    ):
        super().__init__(registry, "allocation", get_entities_fn, simulator)

    @property
    def pricing(self):
        def decorator(func):
            self._reg.set_pricing(func)
            return func

        return decorator


class Engine:
    def __init__(
        self, config_path: str, world_db_path: str, output_dir: str = "./output"
    ):
        self._registry = _StrategyRegistry()
        self._simulator = Simulator(config_path, world_db_path, self._registry)
        self.output_dir = output_dir

        self.firm = _Slot(
            self._registry,
            "firm",
            get_entities_fn=lambda: list(self._simulator.state.firms.values()),
            simulator=self._simulator,
        )
        self.household = _Slot(
            self._registry,
            "household",
            get_entities_fn=lambda: list(self._simulator.state.households.values()),
            simulator=self._simulator,
        )
        self.government = _Slot(
            self._registry,
            "government",
            get_entities_fn=lambda: list(self._simulator.state.governments.values()),
            simulator=self._simulator,
        )
        self.allocation = _AllocationSlot(
            self._registry,
            get_entities_fn=lambda: None,
            simulator=self._simulator,
        )

    def run(self, n_ticks: int) -> List[Dict]:
        return self._simulator.run(n_ticks)

    def save(self, snapshots: List[Dict], prefix: str = "ese") -> str:
        os.makedirs(self.output_dir, exist_ok=True)

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd

        df = pd.DataFrame(snapshots)

        csv_path = os.path.join(self.output_dir, f"{prefix}_results.csv")
        df.to_csv(csv_path, index=False)

        plot_fields = [
            ("gini", "Gini"),
            ("unemployment", "Unemployment"),
            ("engel", "Engel"),
            ("active_firms", "Active Firms"),
        ]
        visible = [(col, title) for col, title in plot_fields if col in df.columns]

        if visible:
            n = len(visible)
            cols = min(2, n)
            rows = (n + cols - 1) // cols
            fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 5 * rows))
            if rows * cols == 1:
                axes = [axes]
            else:
                axes = axes.flatten()

            for i, (col, title) in enumerate(visible):
                axes[i].plot(df["tick"], df[col])
                axes[i].set_title(title)

            for j in range(len(visible), len(axes)):
                axes[j].axis("off")

            fig.tight_layout()
            png_path = os.path.join(self.output_dir, f"{prefix}_results.png")
            fig.savefig(png_path)
            plt.close(fig)

        print(f"Saved {csv_path}" + (f" and {png_path}" if visible else ""))
        return self.output_dir
