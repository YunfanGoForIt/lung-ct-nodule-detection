import unittest

from tools.post_filter_analysis import (
    Annotation,
    Candidate,
    Policy,
    evaluate_case,
)


class PostFilterAnalysisTest(unittest.TestCase):
    def test_evaluate_case_counts_hits_and_false_positives_for_selected_candidates(self):
        annotations = [
            Annotation(index=1, world=(0.0, 0.0, 0.0), diameter_mm=6.0),
            Annotation(index=2, world=(20.0, 0.0, 0.0), diameter_mm=4.0),
        ]
        candidates = [
            Candidate(candidate_id=1, world=(1.0, 0.0, 0.0), features={"diameter_mm": 4.0}),
            Candidate(candidate_id=2, world=(30.0, 0.0, 0.0), features={"diameter_mm": 8.0}),
            Candidate(candidate_id=3, world=(20.0, 1.5, 0.0), features={"diameter_mm": 3.0}),
        ]
        policy = Policy(name="keep_small", filters=(lambda c: c.features["diameter_mm"] < 6.0,), limit=None, score=None)

        metrics = evaluate_case(annotations, candidates, policy)

        self.assertEqual(metrics.annotations, 2)
        self.assertEqual(metrics.candidates, 2)
        self.assertEqual(metrics.strict_hits, 2)
        self.assertEqual(metrics.relaxed_hits, 2)
        self.assertEqual(metrics.strict_candidate_hits, 2)
        self.assertEqual(metrics.relaxed_candidate_hits, 2)
        self.assertEqual(metrics.strict_false_positives, 0)
        self.assertEqual(metrics.relaxed_false_positives, 0)


if __name__ == "__main__":
    unittest.main()
