import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from case_config import load_config  # noqa: E402
from generate_case import (  # noqa: E402
    blade_element_data,
    outputs,
    render_block_mesh,
    render_functions,
    render_fvoptions,
    render_toposet,
)


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()

    def test_one_alm_source(self):
        rendered = render_fvoptions(self.cfg)
        self.assertEqual(rendered.count("type axialFlowTurbineALSource;"), 1)
        self.assertIn("cellSet T1;", rendered)
        self.assertNotRegex(rendered, re.compile(r"\bT[234]\b"))
        self.assertIn("origin (0 0 12.192);", rendered)
        self.assertIn("meshFactor 1;", rendered)
        self.assertIn("azimuthalOffset 180.0;", rendered)
        self.assertIn("nElements 50;", rendered)

    def test_nrel_feather_twist_is_converted_to_turbinesfoam_sign(self):
        rendered = blade_element_data(self.cfg)
        stations = rendered.splitlines()
        self.assertIn("-3)", stations[0])
        self.assertIn("-23.04)", stations[6])
        self.assertIn("-1.185)", stations[-1])

    def test_block_mesh_has_eighteen_structured_blocks(self):
        production = render_block_mesh(self.cfg, "production")
        smoke = render_block_mesh(self.cfg, "smoke")
        self.assertEqual(production.count("    hex ("), 18)
        self.assertEqual(smoke.count("    hex ("), 18)
        self.assertIn("(50 36 64)", production)
        self.assertIn("(10 8 16)", smoke)
        self.assertNotIn("snappy", production.lower())

    def test_toposet_covers_complete_turbine(self):
        rendered = render_toposet(self.cfg)
        self.assertEqual(rendered.count("name T1;"), 1)
        self.assertIn("source boxToCell;", rendered)
        self.assertIn("(-5.029 -10.058 0)", rendered)
        self.assertNotIn("cylinderToCell", rendered)

    def test_outputs_do_not_generate_snappy_dictionary(self):
        paths = [path.name for path in outputs(self.cfg, "production")]
        self.assertNotIn("snappyHexMeshDict", paths)

    def test_q_criterion_is_written_at_each_output_time(self):
        rendered = render_functions(self.cfg)
        self.assertIn("QCriterion\n{", rendered)
        self.assertIn("type Q;", rendered)
        self.assertIn("field U;", rendered)
        self.assertIn("executeControl writeTime;", rendered)
        self.assertIn("writeControl writeTime;", rendered)

    def test_iddes_fields_and_orthogonal_numerics(self):
        turbulence = (ROOT / "case/constant/turbulenceProperties").read_text()
        solution = (ROOT / "case/system/fvSolution").read_text()
        schemes = (ROOT / "case/system/fvSchemes").read_text()
        self.assertIn("LESModel        kOmegaSSTIDDES;", turbulence)
        self.assertIn("delta           IDDESDelta;", turbulence)
        self.assertIn("nNonOrthogonalCorrectors   0;", solution)
        self.assertIn("div(phi,k)", schemes)
        self.assertIn("div(phi,omega)", schemes)
        self.assertIn("Gauss linear orthogonal;", schemes)

    def test_k_omega_boundary_conditions_exist_in_both_profiles(self):
        for profile in ("0.mann", "0.uniform"):
            k = (ROOT / f"case/{profile}/k").read_text()
            omega = (ROOT / f"case/{profile}/omega").read_text()
            self.assertIn("kqRWallFunction", k)
            self.assertIn("omegaWallFunction", omega)
        self.assertIn(
            "atmBoundaryLayerInletK",
            (ROOT / "case/0.mann/k").read_text(),
        )
        self.assertIn(
            "atmBoundaryLayerInletOmega",
            (ROOT / "case/0.mann/omega").read_text(),
        )

    def test_polar_covers_complete_angle_domain(self):
        text = (ROOT / "data/airfoils/S809_Re1M_extended").read_text()
        angles = [
            float(value)
            for value in re.findall(r"^\((-?\d+(?:\.\d+)?)", text, re.MULTILINE)
        ]
        self.assertEqual(angles[0], -180.0)
        self.assertEqual(angles[-1], 180.0)
        self.assertTrue(all(b > a for a, b in zip(angles, angles[1:])))


if __name__ == "__main__":
    unittest.main()
