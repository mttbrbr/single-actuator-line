import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from case_config import (  # noqa: E402
    load_config,
    mean_velocity,
    read_blade,
    tip_speed_ratio,
    turbine_positions,
)
from generate_mann_inflow import grid_spec  # noqa: E402


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()

    def test_layout_is_reproducible_and_separated(self):
        positions = turbine_positions(self.cfg)
        self.assertEqual([item["name"] for item in positions], ["T1", "T2", "T3", "T4"])
        diameter = self.cfg["turbine"]["diameter"]
        for i, first in enumerate(positions):
            for second in positions[i + 1 :]:
                distance_D = math.hypot(second["x"] - first["x"], second["y"] - first["y"]) / diameter
                self.assertGreaterEqual(distance_D, 3.0)

    def test_log_law_matches_hub_velocity(self):
        speed = mean_velocity(self.cfg, self.cfg["turbine"]["hub_height"])
        self.assertAlmostEqual(speed, self.cfg["abl"]["hub_velocity"], places=12)

    def test_tip_speed_ratio_is_derived_consistently(self):
        self.assertAlmostEqual(tip_speed_ratio(self.cfg), self.cfg["turbine"]["tip_speed_ratio"], delta=5e-4)

    def test_blade_is_monotonic_and_reaches_tip(self):
        blade = read_blade()
        self.assertEqual(len(blade), 26)
        self.assertAlmostEqual(blade[0]["radius"], 0.5083)
        self.assertAlmostEqual(blade[-1]["radius"], self.cfg["turbine"]["radius"])
        self.assertTrue(all(b["radius"] > a["radius"] for a, b in zip(blade, blade[1:])))

    def test_mann_grid_covers_requested_duration(self):
        spec = grid_spec(self.cfg)
        self.assertEqual(spec["Nxyz"], (2048, 64, 40))
        self.assertEqual(spec["n_planes"], 1203)
        self.assertGreaterEqual(spec["Nxyz"][0], spec["n_planes"])


if __name__ == "__main__":
    unittest.main()

