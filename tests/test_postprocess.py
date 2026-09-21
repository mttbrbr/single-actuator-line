import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sal_postprocess", ROOT / "scripts/postprocess.py")
postprocess = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = postprocess
SPEC.loader.exec_module(postprocess)


class PostprocessTests(unittest.TestCase):
    def test_purge_disabled_for_future_runs(self):
        self.assertEqual(postprocess.config()["run"]["purge_write"], 0)

    def test_headless_sampling_has_all_views_and_fields(self):
        dictionary = postprocess.sampling_dictionary(postprocess.config())
        self.assertEqual(dictionary.count("type cuttingPlane;"), 8)
        self.assertIn("fields (U vorticity Cp Q);", dictionary)
        self.assertNotIn("runTimePostProcessing", dictionary)
        self.assertEqual(set(postprocess.views_spec(postprocess.config())), set(postprocess.VIEWS))


if __name__ == "__main__":
    unittest.main()
