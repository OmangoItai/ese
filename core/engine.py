import warnings
from typing import Dict, List

from core._registry import _StrategyRegistry
from core.market_intelligence import MarketIntelligence
from core.simulator import Simulator


class _Slot:
    def __init__(self, registry: _StrategyRegistry, slot_name: str):
        self._reg = registry
        self._name = slot_name

    def __call__(self, func):
        self._reg.set_primary(self._name, func)
        return func

    def label(self, label: str):
        def decorator(func):
            self._reg.set_labeled(self._name, label, func)
            return func

        return decorator

    def use(self, label: str, mi, entity, goods):
        strategy = self._reg.get(self._name, label)
        if strategy is None:
            warnings.warn(
                f"No '{label}' strategy registered for '{self._name}' slot. "
                f"Entity {entity.id} will take no action this tick.",
                RuntimeWarning,
            )
            return {"new": [], "cancel": [], "update": []}
        return strategy(mi, entity, goods)


class _AllocationSlot(_Slot):
    def __init__(self, registry: _StrategyRegistry):
        super().__init__(registry, "allocation")

    @property
    def pricing(self):
        def decorator(func):
            self._reg.set_pricing(func)
            return func

        return decorator


class Engine:
    def __init__(self, config_path: str, world_db_path: str):
        self._registry = _StrategyRegistry()
        self._simulator = Simulator(config_path, world_db_path, self._registry)

        self.firm = _Slot(self._registry, "firm")
        self.household = _Slot(self._registry, "household")
        self.government = _Slot(self._registry, "government")
        self.allocation = _AllocationSlot(self._registry)

    def run(self, n_ticks: int) -> List[Dict]:
        return self._simulator.run(n_ticks)
