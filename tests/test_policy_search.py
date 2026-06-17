import unittest

from tools.explore_scoring_policies import adaptive_topk, linear_score


class PolicySearchTest(unittest.TestCase):
    def test_adaptive_topk_uses_fraction_and_bounds(self):
        self.assertEqual(adaptive_topk(10, fraction=0.2, min_k=4, max_k=9), 4)
        self.assertEqual(adaptive_topk(40, fraction=0.2, min_k=4, max_k=9), 8)
        self.assertEqual(adaptive_topk(100, fraction=0.2, min_k=4, max_k=9), 9)

    def test_linear_score_rewards_closeness_and_homogeneity(self):
        best = {
            "diameter_mm": 8.0,
            "circularity": 0.9,
            "mean_hu": -420.0,
            "std_hu": 40.0,
            "glcm_contrast": 0.7,
            "glcm_homogeneity": 0.8,
            "slice_count": 5.0,
        }
        worse = {
            "diameter_mm": 8.0,
            "circularity": 0.9,
            "mean_hu": -180.0,
            "std_hu": 40.0,
            "glcm_contrast": 0.7,
            "glcm_homogeneity": 0.5,
            "slice_count": 5.0,
        }
        weights = {
            "diameter": 1.0,
            "circularity": 1.0,
            "mean_closeness": 2.0,
            "std_hu": 0.5,
            "contrast": 0.5,
            "homogeneity": 1.5,
            "slice_count": 0.5,
        }
        self.assertGreater(linear_score(best, weights, mean_target=-420.0), linear_score(worse, weights, mean_target=-420.0))


if __name__ == "__main__":
    unittest.main()
