from typing import Any, Callable, Dict, Optional

VALID_SLOTS = {"firm", "household", "government", "allocation"}


class Registry:
    def __init__(self):
        self._slots: Dict[str, Optional[Callable]] = {
            "firm": None,
            "household": None,
            "government": None,
            "allocation": None,
        }

    def register(self, slot: str, strategy: Callable) -> None:
        if slot not in self._slots:
            raise ValueError(
                f"Unknown slot '{slot}'. Valid slots: {sorted(VALID_SLOTS)}"
            )
        self._slots[slot] = strategy

    def get(self, slot: str) -> Optional[Callable]:
        if slot not in self._slots:
            raise ValueError(
                f"Unknown slot '{slot}'. Valid slots: {sorted(VALID_SLOTS)}"
            )
        return self._slots[slot]
