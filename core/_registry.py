from typing import Callable, Dict, Optional


class _Slot:
    def __init__(self, name: str):
        self.name = name
        self.primary: Optional[Callable] = None
        self.labeled: Dict[str, Callable] = {}

    def set_primary(self, func: Callable) -> None:
        self.primary = func

    def set_labeled(self, label: str, func: Callable) -> None:
        self.labeled[label] = func

    def get(self, label: Optional[str] = None) -> Optional[Callable]:
        if label:
            return self.labeled.get(label)
        return self.primary


class _StrategyRegistry:
    def __init__(self):
        self._slots: Dict[str, _Slot] = {
            "firm": _Slot("firm"),
            "household": _Slot("household"),
            "government": _Slot("government"),
            "allocation": _Slot("allocation"),
        }
        self._pricing: Optional[Callable] = None

    def set_primary(self, slot: str, func: Callable) -> None:
        self._slots[slot].set_primary(func)

    def set_labeled(self, slot: str, label: str, func: Callable) -> None:
        self._slots[slot].set_labeled(label, func)

    def set_pricing(self, func: Callable) -> None:
        self._pricing = func

    def get(self, slot: str, label: Optional[str] = None) -> Optional[Callable]:
        return self._slots[slot].get(label)

    def get_pricing(self) -> Optional[Callable]:
        return self._pricing
