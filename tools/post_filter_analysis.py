#!/usr/bin/env python3
import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

try:
    from validate_luna_annotations import parse_mhd, voxel_to_world
except ModuleNotFoundError:
    from tools.validate_luna_annotations import parse_mhd, voxel_to_world


FEATURE_DEFAULTS = {
    "diameter_mm": 0.0,
    "circularity": 0.0,
    "mean_hu": 0.0,
    "std_hu": 0.0,
    "glcm_contrast": 0.0,
    "glcm_energy": 0.0,
    "glcm_homogeneity": 0.0,
    "slice_count": 0.0,
    "min_boundary_distance_mm": 0.0,
    "max_aspect_ratio": 1.0,
}


@dataclass(frozen=True)
class Annotation:
    index: int
    world: tuple[float, float, float]
    diameter_mm: float


@dataclass(frozen=True)
class Candidate:
    candidate_id: int
    world: tuple[float, float, float]
    features: dict[str, float]


@dataclass(frozen=True)
class Policy:
    name: str
    filters: tuple[Callable[[Candidate], bool], ...]
    limit: int | None = None
    score: Callable[[Candidate], float] | None = None


@dataclass
class Metrics:
    cases: int = 0
    annotated_cases: int = 0
    annotations: int = 0
    candidates: int = 0
    strict_hits: int = 0
    relaxed_hits: int = 0
    strict_candidate_hits: int = 0
    relaxed_candidate_hits: int = 0
    strict_false_positives: int = 0
    relaxed_false_positives: int = 0
    unannotated_candidates: int = 0

    def add(self, other: "Metrics") -> None:
        self.cases += other.cases
        self.annotated_cases += other.annotated_cases
        self.annotations += other.annotations
        self.candidates += other.candidates
        self.strict_hits += other.strict_hits
        self.relaxed_hits += other.relaxed_hits
        self.strict_candidate_hits += other.strict_candidate_hits
        self.relaxed_candidate_hits += other.relaxed_candidate_hits
        self.strict_false_positives += other.strict_false_positives
        self.relaxed_false_positives += other.relaxed_false_positives
        self.unannotated_candidates += other.unannotated_candidates


def feature(candidate: Candidate, key: str) -> float:
    return candidate.features.get(key, FEATURE_DEFAULTS[key])


def cpp_current_score(candidate: Candidate) -> float:
    return (
        2.0 * feature(candidate, "diameter_mm")
        + 3.0 * feature(candidate, "glcm_homogeneity")
        - 0.02 * feature(candidate, "std_hu")
        - 0.2 * feature(candidate, "glcm_contrast")
    )


def cap_diameter_score(cap_mm: float, slice_penalty: float = 0.0) -> Callable[[Candidate], float]:
    def score(candidate: Candidate) -> float:
        single_slice_penalty = slice_penalty if feature(candidate, "slice_count") <= 1.0 else 0.0
        return (
            2.0 * min(feature(candidate, "diameter_mm"), cap_mm)
            + 3.0 * feature(candidate, "glcm_homogeneity")
            - 0.02 * feature(candidate, "std_hu")
            - 0.2 * feature(candidate, "glcm_contrast")
            - single_slice_penalty
        )

    return score


def balanced_score(candidate: Candidate) -> float:
    return (
        0.9 * min(feature(candidate, "diameter_mm"), 10.0)
        + 8.0 * feature(candidate, "glcm_homogeneity")
        + 0.7 * min(feature(candidate, "slice_count"), 6.0)
        + 2.0 * feature(candidate, "circularity")
        - 0.025 * feature(candidate, "std_hu")
        - 0.35 * feature(candidate, "glcm_contrast")
    )


def soft_diameter_score(candidate: Candidate) -> float:
    return (
        5.0 * math.log1p(max(0.0, feature(candidate, "diameter_mm")))
        + 7.0 * feature(candidate, "glcm_homogeneity")
        + 0.5 * min(feature(candidate, "slice_count"), 5.0)
        - 0.02 * feature(candidate, "std_hu")
        - 0.3 * feature(candidate, "glcm_contrast")
    )


def tiny_nodule_score(candidate: Candidate) -> float:
    return (
        1.0 * min(feature(candidate, "diameter_mm"), 8.0)
        + 10.0 * feature(candidate, "glcm_homogeneity")
        + 0.9 * min(feature(candidate, "slice_count"), 4.0)
        - 0.015 * feature(candidate, "std_hu")
        - 0.5 * feature(candidate, "glcm_contrast")
    )


def load_split(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    with path.open(newline="") as file:
        return {row["seriesuid"]: row["split"] for row in csv.DictReader(file)}


def load_annotations(annotation_validation_path: Path) -> list[Annotation]:
    if not annotation_validation_path.exists():
        return []
    annotations = []
    with annotation_validation_path.open(newline="") as file:
        for row in csv.DictReader(file):
            annotations.append(
                Annotation(
                    index=int(row["annotation_index"]),
                    world=(float(row["ann_x"]), float(row["ann_y"]), float(row["ann_z"])),
                    diameter_mm=float(row["ann_diameter_mm"]),
                )
            )
    return annotations


def load_candidates(features_path: Path, mhd_path: Path | None = None) -> list[Candidate]:
    if not features_path.exists():
        return []
    spacing = offset = transform = None
    if mhd_path is not None and mhd_path.exists():
        spacing, offset, transform = parse_mhd(mhd_path)
    candidates = []
    with features_path.open(newline="") as file:
        for row in csv.DictReader(file):
            features = dict(FEATURE_DEFAULTS)
            for key in features:
                if key in row and row[key] != "":
                    features[key] = float(row[key])
            if spacing is not None and offset is not None and transform is not None:
                world = voxel_to_world(
                    float(row["center_x"]),
                    float(row["center_y"]),
                    float(row["center_z"]),
                    spacing,
                    offset,
                    transform,
                )
            else:
                world = (float(row["center_x"]), float(row["center_y"]), float(row["center_z"]))
            candidates.append(Candidate(candidate_id=int(row["id"]), world=world, features=features))
    return candidates


def selected_candidates(candidates: Iterable[Candidate], policy: Policy) -> list[Candidate]:
    selected = [candidate for candidate in candidates if all(check(candidate) for check in policy.filters)]
    if policy.score is not None:
        selected.sort(key=lambda candidate: (policy.score(candidate), -candidate.candidate_id), reverse=True)
    if policy.limit is not None:
        selected = selected[: policy.limit]
    return selected


def annotation_hits(annotations: list[Annotation], candidates: list[Candidate], relaxed: bool) -> int:
    hits = 0
    for annotation in annotations:
        radius = annotation.diameter_mm / 2.0
        if relaxed:
            radius = max(radius, 10.0)
        if any(math.dist(annotation.world, candidate.world) <= radius for candidate in candidates):
            hits += 1
    return hits


def candidate_hit_ids(annotations: list[Annotation], candidates: list[Candidate], relaxed: bool) -> set[int]:
    hit_ids = set()
    for candidate in candidates:
        for annotation in annotations:
            radius = annotation.diameter_mm / 2.0
            if relaxed:
                radius = max(radius, 10.0)
            if math.dist(annotation.world, candidate.world) <= radius:
                hit_ids.add(candidate.candidate_id)
                break
    return hit_ids


def evaluate_case(annotations: list[Annotation], candidates: list[Candidate], policy: Policy) -> Metrics:
    selected = selected_candidates(candidates, policy)
    strict_candidate_hits = candidate_hit_ids(annotations, selected, relaxed=False)
    relaxed_candidate_hits = candidate_hit_ids(annotations, selected, relaxed=True)
    return Metrics(
        cases=1,
        annotated_cases=1 if annotations else 0,
        annotations=len(annotations),
        candidates=len(selected),
        strict_hits=annotation_hits(annotations, selected, relaxed=False),
        relaxed_hits=annotation_hits(annotations, selected, relaxed=True),
        strict_candidate_hits=len(strict_candidate_hits),
        relaxed_candidate_hits=len(relaxed_candidate_hits),
        strict_false_positives=len(selected) - len(strict_candidate_hits) if annotations else 0,
        relaxed_false_positives=len(selected) - len(relaxed_candidate_hits) if annotations else 0,
        unannotated_candidates=len(selected) if not annotations else 0,
    )


def make_policies() -> list[Policy]:
    filters = {
        "mean_-410_60": lambda c: -410.0 <= feature(c, "mean_hu") <= 60.0,
        "std_25_210": lambda c: 25.0 <= feature(c, "std_hu") <= 210.0,
        "hom_045": lambda c: feature(c, "glcm_homogeneity") >= 0.45,
        "contrast_33": lambda c: feature(c, "glcm_contrast") <= 3.3,
        "circ_046": lambda c: feature(c, "circularity") >= 0.46,
        "slice_le_18": lambda c: feature(c, "slice_count") <= 18.0,
        "slice_ge_2_or_dia_ge_8": lambda c: feature(c, "slice_count") >= 2.0 or feature(c, "diameter_mm") >= 8.0,
        "std_40_190": lambda c: 40.0 <= feature(c, "std_hu") <= 190.0,
        "mean_-350_80": lambda c: -350.0 <= feature(c, "mean_hu") <= 80.0,
        "hom_060": lambda c: feature(c, "glcm_homogeneity") >= 0.60,
        "dia_3_20": lambda c: 3.0 <= feature(c, "diameter_mm") <= 20.0,
        "dia_4_16": lambda c: 4.0 <= feature(c, "diameter_mm") <= 16.0,
    }
    score_variants = [
        ("cpp_current", cpp_current_score),
        ("cpp_cap8", cap_diameter_score(8.0)),
        ("cpp_cap10", cap_diameter_score(10.0)),
        ("cpp_cap8_slicepenalty", cap_diameter_score(8.0, slice_penalty=0.5)),
        ("balanced", balanced_score),
        ("soft_diameter", soft_diameter_score),
        ("tiny_nodule", tiny_nodule_score),
    ]
    top_k = [30, 50, 80, 100, 120, 150, 180]
    policies = [Policy(name="keep_all", filters=(), limit=None, score=None)]
    for name, score in score_variants:
        for limit in top_k:
            policies.append(Policy(name=f"top{limit}_{name}", filters=(), limit=limit, score=score))
    threshold_sets = [
        ("baseline_thresholds", ("mean_-410_60", "std_25_210", "hom_045", "contrast_33", "slice_le_18")),
        ("baseline_plus_circ", ("mean_-410_60", "std_25_210", "hom_045", "contrast_33", "circ_046", "slice_le_18")),
        ("slice_gate_large8", ("slice_ge_2_or_dia_ge_8",)),
        ("stricter_texture", ("hom_060", "contrast_33")),
        ("stricter_hu_std", ("mean_-350_80", "std_40_190")),
        ("diameter_3_20", ("dia_3_20",)),
        ("diameter_4_16", ("dia_4_16",)),
        ("balanced_thresholds", ("mean_-410_60", "std_25_210", "hom_045", "contrast_33", "dia_3_20")),
    ]
    for name, keys in threshold_sets:
        checks = tuple(filters[key] for key in keys)
        policies.append(Policy(name=name, filters=checks, limit=None, score=None))
        for limit in (80, 100, 120, 150):
            policies.append(Policy(name=f"{name}_top{limit}_balanced", filters=checks, limit=limit, score=balanced_score))
            policies.append(Policy(name=f"{name}_top{limit}_cpp_cap8", filters=checks, limit=limit, score=cap_diameter_score(8.0)))
    return policies


def summarize_row(policy_name: str, split: str, metrics: Metrics, baseline: Metrics) -> dict[str, object]:
    strict_recall = metrics.strict_hits / metrics.annotations if metrics.annotations else 0.0
    relaxed_recall = metrics.relaxed_hits / metrics.annotations if metrics.annotations else 0.0
    baseline_strict_recall = baseline.strict_hits / baseline.annotations if baseline.annotations else 0.0
    candidate_reduction = 1.0 - metrics.candidates / baseline.candidates if baseline.candidates else 0.0
    strict_fp_reduction = 1.0 - metrics.strict_false_positives / baseline.strict_false_positives if baseline.strict_false_positives else 0.0
    strict_fp_all = metrics.strict_false_positives + metrics.unannotated_candidates
    baseline_strict_fp_all = baseline.strict_false_positives + baseline.unannotated_candidates
    strict_fp_all_reduction = 1.0 - strict_fp_all / baseline_strict_fp_all if baseline_strict_fp_all else 0.0
    return {
        "policy": policy_name,
        "split": split,
        "cases": metrics.cases,
        "annotated_cases": metrics.annotated_cases,
        "annotations": metrics.annotations,
        "strict_hits": metrics.strict_hits,
        "strict_recall": f"{strict_recall:.4f}",
        "strict_recall_delta": f"{strict_recall - baseline_strict_recall:.4f}",
        "relaxed_hits": metrics.relaxed_hits,
        "relaxed_recall": f"{relaxed_recall:.4f}",
        "candidates": metrics.candidates,
        "candidate_reduction": f"{candidate_reduction:.4f}",
        "strict_false_positives": metrics.strict_false_positives,
        "strict_false_positives_all_cases": strict_fp_all,
        "strict_fp_reduction": f"{strict_fp_reduction:.4f}",
        "strict_fp_all_cases_reduction": f"{strict_fp_all_reduction:.4f}",
        "relaxed_false_positives_all_cases": metrics.relaxed_false_positives + metrics.unannotated_candidates,
        "candidates_per_case": f"{metrics.candidates / metrics.cases:.2f}" if metrics.cases else "0.00",
        "strict_fp_per_annotated_case": (
            f"{metrics.strict_false_positives / metrics.annotated_cases:.2f}"
            if metrics.annotated_cases
            else "0.00"
        ),
    }


def read_cases(run_root: Path, subset_dir: Path | None) -> dict[str, tuple[list[Annotation], list[Candidate]]]:
    cases = {}
    for case_dir in sorted(path for path in run_root.iterdir() if path.is_dir()):
        seriesuid = case_dir.name
        mhd_path = subset_dir / f"{seriesuid}.mhd" if subset_dir is not None else None
        annotations = load_annotations(case_dir / "annotation_validation.csv")
        candidates = load_candidates(case_dir / "features.csv", mhd_path)
        cases[seriesuid] = (annotations, candidates)
    return cases


def aggregate_by_policy(
    cases: dict[str, tuple[list[Annotation], list[Candidate]]],
    split_map: dict[str, str],
    policies: list[Policy],
) -> dict[str, dict[str, Metrics]]:
    aggregate = {}
    for policy in policies:
        split_metrics = {"full": Metrics(), "train": Metrics(), "test": Metrics()}
        for seriesuid, (annotations, candidates) in cases.items():
            case_metrics = evaluate_case(annotations, candidates, policy)
            split_metrics["full"].add(case_metrics)
            split = split_map.get(seriesuid)
            if split in split_metrics:
                split_metrics[split].add(case_metrics)
        aggregate[policy.name] = split_metrics
    return aggregate


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate offline post-filter and re-ranking policies on existing Lung CT candidates."
    )
    parser.add_argument("--run-root", type=Path, default=Path("data/subset8_batch_validation_tuned_rerun"))
    parser.add_argument("--subset-dir", type=Path, default=Path("data/luna16_subset8_download/subset8"))
    parser.add_argument("--split", type=Path, default=Path("data/subset8_split_train_test.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/subset8_batch_validation_tuned_rerun/post_filter_policy_metrics.csv"))
    args = parser.parse_args()

    subset_dir = args.subset_dir if args.subset_dir.exists() else None
    split_map = load_split(args.split)
    cases = read_cases(args.run_root, subset_dir)
    policies = make_policies()
    aggregate = aggregate_by_policy(cases, split_map, policies)
    baseline = aggregate["keep_all"]
    rows = []
    for policy in policies:
        for split in ("full", "train", "test"):
            if split != "full" and not split_map:
                continue
            rows.append(summarize_row(policy.name, split, aggregate[policy.name][split], baseline[split]))
    write_csv(args.out, rows)

    full_rows = [row for row in rows if row["split"] == "full"]
    full_rows.sort(
        key=lambda row: (
            int(row["strict_hits"]),
            int(row["relaxed_hits"]),
            float(row["strict_fp_reduction"]),
            float(row["candidate_reduction"]),
        ),
        reverse=True,
    )
    print(f"cases={baseline['full'].cases} annotations={baseline['full'].annotations}")
    print(f"wrote {args.out}")
    print("top full-set policies by strict hits, relaxed hits, FP reduction:")
    for row in full_rows[:12]:
        print(
            f"{row['policy']}: strict={row['strict_hits']}/{row['annotations']} "
            f"relaxed={row['relaxed_hits']}/{row['annotations']} "
            f"candidates={row['candidates']} "
            f"strict_fp={row['strict_false_positives']} "
            f"fp_reduction={float(row['strict_fp_reduction']):.1%}"
        )


if __name__ == "__main__":
    main()
