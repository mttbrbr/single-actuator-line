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

    def test_video_frames_use_original_full_width_layout(self):
        self.assertEqual(postprocess.video_size("hub"), (3840, 1440))
        self.assertEqual(postprocess.video_size("wake_2D"), (3840, 1920))

    def test_vorticity_scale_distinguishes_cross_wake_vortices(self):
        self.assertEqual(postprocess.display_range("hub", "vorticity"), (0.0, 2.0))
        self.assertEqual(postprocess.display_range("wake_2D", "vorticity"), (0.0, 8.0))

    def test_all_presented_outputs_have_one_parent(self):
        self.assertEqual(postprocess.OUTPUT, ROOT / "postprocessing")
        self.assertEqual(postprocess.OUTPUT / "videos", ROOT / "postprocessing/videos")


if __name__ == "__main__":
    unittest.main()
