import math
from core.noise import InformationFriction


class TestInformationFriction:
    def test_init_binds_seed(self):
        n1 = InformationFriction(seed=42)
        n2 = InformationFriction(seed=42)
        v1 = n1.apply_noise(100.0, "gaussian", {"sigma": 0.1})
        v2 = n2.apply_noise(100.0, "gaussian", {"sigma": 0.1})
        assert v1 == v2

    def test_different_seeds_diverge(self):
        n1 = InformationFriction(seed=42)
        n2 = InformationFriction(seed=99)
        v1 = n1.apply_noise(100.0, "gaussian", {"sigma": 0.1})
        v2 = n2.apply_noise(100.0, "gaussian", {"sigma": 0.1})
        assert v1 != v2

    def test_none_noise_returns_original(self):
        n = InformationFriction(seed=42)
        assert n.apply_noise(100.0, "none", {}) == 100.0
        assert n.apply_noise(0.0, "none", {}) == 0.0

    def test_gaussian_mean_close_to_zero(self):
        n = InformationFriction(seed=42)
        noises = [
            n.apply_noise(100.0, "gaussian", {"sigma": 0.1}) - 100.0
            for _ in range(1000)
        ]
        mean_noise = sum(noises) / len(noises)
        assert abs(mean_noise) < 0.05

    def test_uniform_range(self):
        n = InformationFriction(seed=42)
        values = [n.apply_noise(100.0, "uniform", {"range": 0.5}) for _ in range(100)]
        for v in values:
            assert 99.5 <= v <= 100.5

    def test_upward_bias_direction(self):
        n = InformationFriction(seed=42)
        result = n.apply_noise(100.0, "upward_bias", {"factor": 1.5})
        assert result == 150.0

    def test_downward_bias_direction(self):
        n = InformationFriction(seed=42)
        result = n.apply_noise(100.0, "downward_bias", {"factor": 0.7})
        assert result == 70.0

    def test_upward_bias_always_larger(self):
        n = InformationFriction(seed=42)
        for v in [10.0, 100.0, -50.0]:
            result = n.apply_noise(v, "upward_bias", {"factor": 2.0})
            assert result > v if v > 0 else result < v

    def test_default_params(self):
        n = InformationFriction(seed=42)
        assert n.apply_noise(100.0, "gaussian", {}) != 100.0
        assert n.apply_noise(100.0, "uniform", {}) != 100.0
        assert n.apply_noise(100.0, "upward_bias", {}) == 120.0
        assert n.apply_noise(100.0, "downward_bias", {}) == 80.0

    def test_unknown_noise_type_raises(self):
        n = InformationFriction(seed=42)
        try:
            n.apply_noise(100.0, "invalid_type", {})
            assert False, "Should have raised"
        except ValueError:
            pass


class TestApplyDict:
    def test_apply_dict_all_keys(self):
        n = InformationFriction(seed=42)
        values = {"a": 100.0, "b": 200.0, "c": 300.0}
        result = n.apply_dict(values, "none", {})
        assert result == values

    def test_apply_dict_gaussian_changes_all(self):
        n = InformationFriction(seed=42)
        values = {"a": 100.0, "b": 200.0, "c": 300.0}
        result = n.apply_dict(values, "gaussian", {"sigma": 0.1})
        assert set(result.keys()) == set(values.keys())
        for k in values:
            assert result[k] != values[k]

    def test_apply_dict_bias_same_factor(self):
        n = InformationFriction(seed=42)
        values = {"x": 10.0, "y": 50.0}
        result = n.apply_dict(values, "upward_bias", {"factor": 1.2})
        assert result["x"] == 12.0
        assert result["y"] == 60.0
