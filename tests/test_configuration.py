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

    def test_single_turbine_is_centred(self):
        positions = turbine_positions(self.cfg)
        self.assertEqual(positions, [{"name": "T1", "x": 0.0, "y": 0.0, "z": 12.192}])

    def test_log_law_matches_hub_velocity(self):
        speed = mean_velocity(self.cfg, self.cfg["turbine"]["hub_height"])
        self.assertAlmostEqual(speed, self.cfg["abl"]["hub_velocity"], places=12)

    def test_tip_speed_ratio_is_derived_consistently(self):
        self.assertAlmostEqual(
            tip_speed_ratio(self.cfg),
            self.cfg["turbine"]["tip_speed_ratio"],
            delta=5e-4,
        )

    def test_blade_is_monotonic_and_reaches_tip(self):
        blade = read_blade()
        self.assertEqual(len(blade), 26)
        self.assertAlmostEqual(blade[0]["radius"], 0.5083)
        self.assertAlmostEqual(blade[-1]["radius"], self.cfg["turbine"]["radius"])
        self.assertTrue(
            all(b["radius"] > a["radius"] for a, b in zip(blade, blade[1:]))
        )

    def test_structured_mesh_cell_count_and_core_resolution(self):
        mesh = self.cfg["mesh"]
        totals = [sum(mesh[axis]["cells"]) for axis in ("x", "y", "z")]
        self.assertEqual(math.prod(totals), 6_674_304)
        core_dx_D = (mesh["x"]["breaks_D"][2] - mesh["x"]["breaks_D"][1]) / mesh["x"]["cells"][1]
        core_dy_D = (mesh["y"]["breaks_D"][2] - mesh["y"]["breaks_D"][1]) / mesh["y"]["cells"][1]
        core_dz_D = (mesh["z"]["breaks_D"][1] - mesh["z"]["breaks_D"][0]) / mesh["z"]["cells"][0]
        self.assertAlmostEqual(core_dx_D, 1 / 32)
        self.assertAlmostEqual(core_dy_D, 1 / 32)
        self.assertAlmostEqual(core_dz_D, 1 / 32)

    def test_mann_grid_covers_requested_duration(self):
        spec = grid_spec(self.cfg)
        self.assertEqual(spec["Nxyz"], (1024, 64, 40))
        self.assertEqual(spec["n_planes"], 578)
        self.assertGreaterEqual(spec["Nxyz"][0], spec["n_planes"])


if __name__ == "__main__":
    unittest.main()
