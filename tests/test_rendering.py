import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from case_config import load_config  # noqa: E402
from generate_case import (  # noqa: E402
    blade_element_data,
    render_fvoptions,
    render_snappy,
    render_toposet,
)


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()

    def test_four_independent_alm_sources(self):
        rendered = render_fvoptions(self.cfg)
        self.assertEqual(rendered.count("type axialFlowTurbineALSource;"), 4)
        for name in ("T1", "T2", "T3", "T4"):
            self.assertIn(f"cellSet {name};", rendered)
        self.assertIn("meshFactor 1;", rendered)
        self.assertIn("azimuthalOffset 180.0;", rendered)
        self.assertIn("nElements 50;", rendered)

    def test_nrel_feather_twist_is_converted_to_turbinesfoam_sign(self):
        rendered = blade_element_data(self.cfg)
        stations = rendered.splitlines()
        first = stations[0]
        last = stations[-1]
        self.assertIn("-3)", first)
        self.assertIn("-23.04)", stations[6])
        self.assertIn("-1.185)", last)

    def test_production_and_smoke_refinement_caps(self):
        production = render_snappy(self.cfg, "production")
        smoke = render_snappy(self.cfg, "smoke")
        self.assertIn("levels ((1e15 3));", production)
        self.assertNotIn("levels ((1e15 3));", smoke)
        self.assertIn("levels ((1e15 1));", smoke)

    def test_toposet_uses_v2412_cylinder_keys(self):
        rendered = render_toposet(self.cfg)
        self.assertEqual(rendered.count("source cylinderToCell;"), 4)
        self.assertEqual(rendered.count("point1"), 4)
        self.assertNotRegex(rendered, re.compile(r"\n\s+p1\s"))

    def test_polar_covers_complete_angle_domain(self):
        text = (ROOT / "data" / "airfoils" / "S809_Re1M_extended").read_text()
        angles = [float(value) for value in re.findall(r"^\((-?\d+(?:\.\d+)?)", text, re.MULTILINE)]
        self.assertEqual(angles[0], -180.0)
        self.assertEqual(angles[-1], 180.0)
        self.assertTrue(all(b > a for a, b in zip(angles, angles[1:])))


if __name__ == "__main__":
    unittest.main()

