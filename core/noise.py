import random
from typing import Dict


class InformationFriction:
    noise_types = ["gaussian", "uniform", "upward_bias", "downward_bias", "none"]

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def apply_noise(self, true_value: float, noise_type: str, params: Dict) -> float:
        if noise_type == "none":
            return true_value
        elif noise_type == "gaussian":
            sigma = params.get("sigma", 0.1)
            noise = self.rng.gauss(0.0, sigma)
            return true_value + noise
        elif noise_type == "uniform":
            r = params.get("range", 0.1)
            noise = self.rng.uniform(-r, r)
            return true_value + noise
        elif noise_type == "upward_bias":
            factor = params.get("factor", 1.2)
            return true_value * factor
        elif noise_type == "downward_bias":
            factor = params.get("factor", 0.8)
            return true_value * factor
        else:
            raise ValueError(f"Unknown noise_type: {noise_type}")

    def apply_dict(
        self, values: Dict[str, float], noise_type: str, params: Dict
    ) -> Dict[str, float]:
        return {k: self.apply_noise(v, noise_type, params) for k, v in values.items()}
