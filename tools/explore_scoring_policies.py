#!/usr/bin/env python3
import argparse
import csv
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path

try:
    from tools.post_filter_analysis import (
        Annotation,
        Candidate,
        Metrics,
        load_split,
        read_cases,
        write_csv,
    )
except ModuleNotFoundError:
    from post_filter_analysis import Annotation, Candidate, Metrics, load_split, read_cases, write_csv


TOP_K_VALUES = (80, 100, 120, 150, 180)
MEAN_TARGETS = (-500.0, -420.0, -350.0, -280.0)
RANK_CACHE: dict[tuple[int, float, tuple[tuple[str, float], ...]], list["LabeledCandidate"]] = {}


@dataclass(frozen=True)
class LabeledCandidate:
    seriesuid: str
    split: str
    candidate: Candidate
    nearest_annotation_index: int | None
    nearest_distance_mm: float | None
    nearest_strict_radius_mm: float | None
    strict_annotation_indexes: tuple[int, ...]
    relaxed_annotation_indexes: tuple[int, ...]


@dataclass(frozen=True)
class SearchPolicy:
    policy_id: str
    family: str
    mode: str
    weights: dict[str, float]
    mean_target: float
    top_k: int | None = None
    fraction: float | None = None
    min_k: int | None = None
    max_k: int | None = None
    quantile: float | None = None


def feature_value(features: dict[str, float], key: str) -> float:
    value = features.get(key, 0.0)
    if value is None or math.isnan(value):
        return 0.0
    return value


def linear_score(features: dict[str, float], weights: dict[str, float], mean_target: float) -> float:
    diameter = min(max(feature_value(features, "diameter_mm"), 0.0), 20.0) / 20.0
    circularity = min(max(feature_value(features, "circularity"), 0.0), 1.0)
    mean_closeness = 1.0 - min(abs(feature_value(features, "mean_hu") - mean_target) / 320.0, 1.0)
    std_hu = min(max(feature_value(features, "std_hu"), 0.0), 260.0) / 260.0
    contrast = min(max(feature_value(features, "glcm_contrast"), 0.0), 8.0) / 8.0
    homogeneity = min(max(feature_value(features, "glcm_homogeneity"), 0.0), 1.0)
    slice_count = min(max(feature_value(features, "slice_count"), 0.0), 8.0) / 8.0

    return (
        weights["diameter"] * diameter
        + weights["circularity"] * circularity
        + weights["mean_closeness"] * mean_closeness
        - weights["std_hu"] * std_hu
        - weights["contrast"] * contrast
        + weights["homogeneity"] * homogeneity
        + weights["slice_count"] * slice_count
    )


def adaptive_topk(candidate_count: int, fraction: float, min_k: int, max_k: int) -> int:
    if candidate_count <= 0:
        return 0
    return min(candidate_count, max(min_k, min(max_k, math.ceil(candidate_count * fraction))))


def generate_weight_grid() -> list[dict[str, float]]:
    keys = (
        "diameter",
        "circularity",
        "mean_closeness",
        "std_hu",
        "contrast",
        "homogeneity",
        "slice_count",
    )
    values = (
        (0.0, 1.0, 2.0),
        (0.0, 1.0),
        (0.0, 1.0, 2.0),
        (0.0, 1.0),
        (0.0, 1.0),
        (0.0, 1.0, 2.0),
        (0.0, 1.0),
    )
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*values)]


def weight_key(weights: dict[str, float]) -> str:
    return (
        f"d{weights['diameter']:.0f}"
        f"c{weights['circularity']:.0f}"
        f"m{weights['mean_closeness']:.0f}"
        f"s{weights['std_hu']:.0f}"
        f"x{weights['contrast']:.0f}"
        f"h{weights['homogeneity']:.0f}"
        f"z{weights['slice_count']:.0f}"
    )


def make_policies() -> list[SearchPolicy]:
    policies = [
        SearchPolicy(
            policy_id="baseline_keep_all",
            family="baseline",
            mode="all",
            weights={},
            mean_target=-420.0,
        )
    ]
    adaptive_specs = [
        ("adaptive_frac55_min60_max150", 0.55, 60, 150),
        ("adaptive_frac65_min70_max150", 0.65, 70, 150),
        ("adaptive_frac75_min80_max160", 0.75, 80, 160),
    ]
    quantiles = (0.20, 0.30, 0.40, 0.50)

    for grid_index, weights in enumerate(generate_weight_grid()):
        if not any(weights.values()):
            continue
        key = weight_key(weights)
        for mean_target in MEAN_TARGETS:
            target_key = f"mt{int(abs(mean_target))}"
            for top_k in TOP_K_VALUES:
                policies.append(
                    SearchPolicy(
                        policy_id=f"grid{grid_index:04d}_{key}_{target_key}_top{top_k}",
                        family="linear_grid",
                        mode="topk",
                        weights=weights,
                        mean_target=mean_target,
                        top_k=top_k,
                    )
                )
            for name, fraction, min_k, max_k in adaptive_specs:
                policies.append(
                    SearchPolicy(
                        policy_id=f"grid{grid_index:04d}_{key}_{target_key}_{name}",
                        family="linear_grid",
                        mode="adaptive_topk",
                        weights=weights,
                        mean_target=mean_target,
                        fraction=fraction,
                        min_k=min_k,
                        max_k=max_k,
                    )
                )
            for quantile in quantiles:
                policies.append(
                    SearchPolicy(
                        policy_id=f"grid{grid_index:04d}_{key}_{target_key}_score_quantile{quantile:.2f}",
                        family="linear_grid",
                        mode="score_quantile",
                        weights=weights,
                        mean_target=mean_target,
                        quantile=quantile,
                    )
                )
    return policies


def label_candidates(
    cases: dict[str, tuple[list[Annotation], list[Candidate]]],
    split_map: dict[str, str],
) -> dict[str, tuple[list[Annotation], list[LabeledCandidate]]]:
    labeled_cases = {}
    for seriesuid, (annotations, candidates) in cases.items():
        split = split_map.get(seriesuid, "")
        labeled = []
        for candidate in candidates:
            nearest_annotation_index = None
            nearest_distance = None
            nearest_strict_radius = None
            strict_indexes = []
            relaxed_indexes = []
            for annotation in annotations:
                distance = math.dist(annotation.world, candidate.world)
                strict_radius = annotation.diameter_mm / 2.0
                relaxed_radius = max(strict_radius, 10.0)
                if nearest_distance is None or distance < nearest_distance:
                    nearest_annotation_index = annotation.index
                    nearest_distance = distance
                    nearest_strict_radius = strict_radius
                if distance <= strict_radius:
                    strict_indexes.append(annotation.index)
                if distance <= relaxed_radius:
                    relaxed_indexes.append(annotation.index)
            labeled.append(
                LabeledCandidate(
                    seriesuid=seriesuid,
                    split=split,
                    candidate=candidate,
                    nearest_annotation_index=nearest_annotation_index,
                    nearest_distance_mm=nearest_distance,
                    nearest_strict_radius_mm=nearest_strict_radius,
                    strict_annotation_indexes=tuple(strict_indexes),
                    relaxed_annotation_indexes=tuple(relaxed_indexes),
                )
            )
        labeled_cases[seriesuid] = (annotations, labeled)
    return labeled_cases


def ranked_candidates(candidates: list[LabeledCandidate], policy: SearchPolicy) -> list[LabeledCandidate]:
    if policy.mode == "all":
        return list(candidates)
    cache_key = (id(candidates), policy.mean_target, tuple(sorted(policy.weights.items())))
    if cache_key not in RANK_CACHE:
        RANK_CACHE[cache_key] = sorted(
            candidates,
            key=lambda labeled: (
                linear_score(labeled.candidate.features, policy.weights, policy.mean_target),
                -labeled.candidate.candidate_id,
            ),
            reverse=True,
        )
    return RANK_CACHE[cache_key]


def select_candidates(candidates: list[LabeledCandidate], policy: SearchPolicy) -> list[LabeledCandidate]:
    ranked = ranked_candidates(candidates, policy)
    if policy.mode == "all":
        return ranked
    if policy.mode == "topk":
        return ranked[: policy.top_k]
    if policy.mode == "adaptive_topk":
        limit = adaptive_topk(
            len(ranked),
            fraction=policy.fraction or 0.0,
            min_k=policy.min_k or 0,
            max_k=policy.max_k or len(ranked),
        )
        return ranked[:limit]
    if policy.mode == "score_quantile":
        if not ranked:
            return []
        scores = sorted(
            linear_score(labeled.candidate.features, policy.weights, policy.mean_target)
            for labeled in ranked
        )
        index = min(len(scores) - 1, max(0, math.floor((len(scores) - 1) * (policy.quantile or 0.0))))
        threshold = scores[index]
        return [
            labeled
            for labeled in ranked
            if linear_score(labeled.candidate.features, policy.weights, policy.mean_target) >= threshold
        ]
    raise ValueError(f"Unknown policy mode: {policy.mode}")


def evaluate_labeled_case(annotations: list[Annotation], candidates: list[LabeledCandidate], policy: SearchPolicy) -> Metrics:
    selected = select_candidates(candidates, policy)
    strict_annotations = set()
    relaxed_annotations = set()
    strict_candidate_hits = 0
    relaxed_candidate_hits = 0
    for labeled in selected:
        if labeled.strict_annotation_indexes:
            strict_candidate_hits += 1
            strict_annotations.update(labeled.strict_annotation_indexes)
        if labeled.relaxed_annotation_indexes:
            relaxed_candidate_hits += 1
            relaxed_annotations.update(labeled.relaxed_annotation_indexes)
    return Metrics(
        cases=1,
        annotated_cases=1 if annotations else 0,
        annotations=len(annotations),
        candidates=len(selected),
        strict_hits=len(strict_annotations),
        relaxed_hits=len(relaxed_annotations),
        strict_candidate_hits=strict_candidate_hits,
        relaxed_candidate_hits=relaxed_candidate_hits,
        strict_false_positives=len(selected) - strict_candidate_hits if annotations else 0,
        relaxed_false_positives=len(selected) - relaxed_candidate_hits if annotations else 0,
        unannotated_candidates=len(selected) if not annotations else 0,
    )


def evaluate_policy(
    labeled_cases: dict[str, tuple[list[Annotation], list[LabeledCandidate]]],
    split_map: dict[str, str],
    policy: SearchPolicy,
) -> dict[str, Metrics]:
    split_metrics = {"full": Metrics(), "train": Metrics(), "test": Metrics()}
    for seriesuid, (annotations, candidates) in labeled_cases.items():
        metrics = evaluate_labeled_case(annotations, candidates, policy)
        split_metrics["full"].add(metrics)
        split = split_map.get(seriesuid)
        if split in split_metrics:
            split_metrics[split].add(metrics)
    return split_metrics


def metric_row(policy: SearchPolicy, split: str, metrics: Metrics, baseline: Metrics) -> dict[str, object]:
    strict_fp_all = metrics.strict_false_positives + metrics.unannotated_candidates
    baseline_strict_fp_all = baseline.strict_false_positives + baseline.unannotated_candidates
    return {
        "policy_id": policy.policy_id,
        "family": policy.family,
        "mode": policy.mode,
        "split": split,
        "top_k": policy.top_k if policy.top_k is not None else "",
        "fraction": f"{policy.fraction:.2f}" if policy.fraction is not None else "",
        "min_k": policy.min_k if policy.min_k is not None else "",
        "max_k": policy.max_k if policy.max_k is not None else "",
        "quantile": f"{policy.quantile:.2f}" if policy.quantile is not None else "",
        "mean_target": f"{policy.mean_target:.1f}",
        "weights_json": json.dumps(policy.weights, sort_keys=True),
        "cases": metrics.cases,
        "annotated_cases": metrics.annotated_cases,
        "annotations": metrics.annotations,
        "strict_hits": metrics.strict_hits,
        "strict_recall": f"{metrics.strict_hits / metrics.annotations:.4f}" if metrics.annotations else "0.0000",
        "relaxed_hits": metrics.relaxed_hits,
        "relaxed_recall": f"{metrics.relaxed_hits / metrics.annotations:.4f}" if metrics.annotations else "0.0000",
        "candidates": metrics.candidates,
        "candidate_reduction": f"{1.0 - metrics.candidates / baseline.candidates:.4f}" if baseline.candidates else "0.0000",
        "strict_false_positives": metrics.strict_false_positives,
        "strict_false_positives_all_cases": strict_fp_all,
        "strict_fp_reduction": (
            f"{1.0 - metrics.strict_false_positives / baseline.strict_false_positives:.4f}"
            if baseline.strict_false_positives
            else "0.0000"
        ),
        "strict_fp_all_cases_reduction": (
            f"{1.0 - strict_fp_all / baseline_strict_fp_all:.4f}" if baseline_strict_fp_all else "0.0000"
        ),
        "candidates_per_case": f"{metrics.candidates / metrics.cases:.2f}" if metrics.cases else "0.00",
        "strict_fp_per_annotated_case": (
            f"{metrics.strict_false_positives / metrics.annotated_cases:.2f}" if metrics.annotated_cases else "0.00"
        ),
    }


def recommendation_row(policy: SearchPolicy, metrics_by_split: dict[str, Metrics], baseline_by_split: dict[str, Metrics]) -> dict[str, object]:
    full = metrics_by_split["full"]
    train = metrics_by_split["train"]
    test = metrics_by_split["test"]
    baseline_full = baseline_by_split["full"]
    baseline_train = baseline_by_split["train"]
    baseline_test = baseline_by_split["test"]
    return {
        "policy_id": policy.policy_id,
        "family": policy.family,
        "mode": policy.mode,
        "top_k": policy.top_k if policy.top_k is not None else "",
        "fraction": f"{policy.fraction:.2f}" if policy.fraction is not None else "",
        "min_k": policy.min_k if policy.min_k is not None else "",
        "max_k": policy.max_k if policy.max_k is not None else "",
        "quantile": f"{policy.quantile:.2f}" if policy.quantile is not None else "",
        "mean_target": f"{policy.mean_target:.1f}",
        "weights_json": json.dumps(policy.weights, sort_keys=True),
        "train_strict": train.strict_hits,
        "train_strict_loss": baseline_train.strict_hits - train.strict_hits,
        "train_relaxed": train.relaxed_hits,
        "train_candidates": train.candidates,
        "train_strict_fp": train.strict_false_positives,
        "test_strict": test.strict_hits,
        "test_strict_loss": baseline_test.strict_hits - test.strict_hits,
        "test_relaxed": test.relaxed_hits,
        "test_candidates": test.candidates,
        "test_strict_fp": test.strict_false_positives,
        "full_strict": full.strict_hits,
        "full_strict_loss": baseline_full.strict_hits - full.strict_hits,
        "full_relaxed": full.relaxed_hits,
        "full_candidates": full.candidates,
        "full_candidate_reduction": f"{1.0 - full.candidates / baseline_full.candidates:.4f}",
        "full_strict_fp": full.strict_false_positives,
        "full_strict_fp_reduction": f"{1.0 - full.strict_false_positives / baseline_full.strict_false_positives:.4f}",
        "eligible_recommendation": (
            baseline_test.strict_hits - test.strict_hits <= 0
            and baseline_full.strict_hits - full.strict_hits <= 2
            and full.candidates < baseline_full.candidates
        ),
    }


def write_candidate_labels(path: Path, labeled_cases: dict[str, tuple[list[Annotation], list[LabeledCandidate]]]) -> None:
    rows = []
    feature_keys = [
        "diameter_mm",
        "circularity",
        "mean_hu",
        "std_hu",
        "glcm_contrast",
        "glcm_energy",
        "glcm_homogeneity",
        "slice_count",
    ]
    for seriesuid, (_, labeled_candidates) in labeled_cases.items():
        for labeled in labeled_candidates:
            row = {
                "seriesuid": seriesuid,
                "split": labeled.split,
                "candidate_id": labeled.candidate.candidate_id,
                "world_x": f"{labeled.candidate.world[0]:.6f}",
                "world_y": f"{labeled.candidate.world[1]:.6f}",
                "world_z": f"{labeled.candidate.world[2]:.6f}",
                "nearest_annotation_index": labeled.nearest_annotation_index or "",
                "nearest_distance_mm": (
                    f"{labeled.nearest_distance_mm:.6f}" if labeled.nearest_distance_mm is not None else ""
                ),
                "nearest_strict_radius_mm": (
                    f"{labeled.nearest_strict_radius_mm:.6f}" if labeled.nearest_strict_radius_mm is not None else ""
                ),
                "strict_tp": bool(labeled.strict_annotation_indexes),
                "relaxed_tp": bool(labeled.relaxed_annotation_indexes),
                "strict_annotation_indexes": ";".join(str(index) for index in labeled.strict_annotation_indexes),
                "relaxed_annotation_indexes": ";".join(str(index) for index in labeled.relaxed_annotation_indexes),
            }
            for key in feature_keys:
                row[key] = labeled.candidate.features.get(key, "")
            rows.append(row)
    write_csv(path, rows)


def write_markdown_summary(
    path: Path,
    baseline: dict[str, Metrics],
    recommendations: list[dict[str, object]],
) -> None:
    lines = [
        "# Offline Scoring Policy Search",
        "",
        "Baseline uses all tuned-rerun candidates from `data/subset8_batch_validation_tuned_rerun`.",
        "",
        "| split | strict | relaxed | candidates | strict FP |",
        "|---|---:|---:|---:|---:|",
    ]
    for split in ("train", "test", "full"):
        metrics = baseline[split]
        lines.append(
            f"| {split} | {metrics.strict_hits}/{metrics.annotations} | "
            f"{metrics.relaxed_hits}/{metrics.annotations} | {metrics.candidates} | "
            f"{metrics.strict_false_positives} |"
        )
    lines.extend(
        [
            "",
            "Recommendation filter: test strict recall must not drop, full strict recall may drop by at most 2, and candidates must decrease.",
            "",
            "| rank | policy | mode | train strict | test strict | full strict | full relaxed | candidates | strict FP | candidate reduction | FP reduction |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for index, row in enumerate(recommendations[:20], 1):
        lines.append(
            f"| {index} | `{row['policy_id']}` | {row['mode']} | "
            f"{row['train_strict']} | {row['test_strict']} | {row['full_strict']} | "
            f"{row['full_relaxed']} | {row['full_candidates']} | {row['full_strict_fp']} | "
            f"{float(row['full_candidate_reduction']):.1%} | {float(row['full_strict_fp_reduction']):.1%} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grid-search simple offline ranking policies for Lung CT nodule candidates."
    )
    parser.add_argument("--run-root", type=Path, default=Path("data/subset8_batch_validation_tuned_rerun"))
    parser.add_argument("--subset-dir", type=Path, default=Path("data/luna16_subset8_download/subset8"))
    parser.add_argument("--split", type=Path, default=Path("data/subset8_split_train_test.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/subset8_batch_validation_tuned_rerun/scoring_policy_search"))
    args = parser.parse_args()

    subset_dir = args.subset_dir if args.subset_dir.exists() else None
    split_map = load_split(args.split)
    cases = read_cases(args.run_root, subset_dir)
    labeled_cases = label_candidates(cases, split_map)
    policies = make_policies()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    labels_path = args.out_dir / "candidate_strict_relaxed_labels.csv"
    metrics_path = args.out_dir / "policy_metrics.csv"
    recommendations_path = args.out_dir / "recommended_policies.csv"
    summary_path = args.out_dir / "summary.md"

    write_candidate_labels(labels_path, labeled_cases)

    baseline_policy = policies[0]
    baseline = evaluate_policy(labeled_cases, split_map, baseline_policy)
    metric_rows = []
    recommendation_rows = []
    for index, policy in enumerate(policies, 1):
        metrics_by_split = evaluate_policy(labeled_cases, split_map, policy)
        for split in ("full", "train", "test"):
            metric_rows.append(metric_row(policy, split, metrics_by_split[split], baseline[split]))
        if policy is not baseline_policy:
            recommendation_rows.append(recommendation_row(policy, metrics_by_split, baseline))
        if index % 2500 == 0:
            print(f"evaluated {index}/{len(policies)} policies")

    recommendation_rows.sort(
        key=lambda row: (
            not row["eligible_recommendation"],
            int(row["full_candidates"]),
            int(row["full_strict_loss"]),
            -int(row["test_strict"]),
            -int(row["full_relaxed"]),
        )
    )
    write_csv(metrics_path, metric_rows)
    write_csv(recommendations_path, recommendation_rows)
    eligible = [row for row in recommendation_rows if row["eligible_recommendation"]]
    write_markdown_summary(summary_path, baseline, eligible)

    print(
        "baseline full: "
        f"strict={baseline['full'].strict_hits}/{baseline['full'].annotations} "
        f"relaxed={baseline['full'].relaxed_hits}/{baseline['full'].annotations} "
        f"candidates={baseline['full'].candidates} "
        f"strict_fp={baseline['full'].strict_false_positives}"
    )
    print(f"policies={len(policies)} eligible_recommendations={len(eligible)}")
    print(f"wrote {labels_path}")
    print(f"wrote {metrics_path}")
    print(f"wrote {recommendations_path}")
    print(f"wrote {summary_path}")
    for row in eligible[:8]:
        print(
            f"{row['policy_id']}: train_strict={row['train_strict']} "
            f"test_strict={row['test_strict']} full_strict={row['full_strict']} "
            f"relaxed={row['full_relaxed']} candidates={row['full_candidates']} "
            f"strict_fp={row['full_strict_fp']} "
            f"cand_reduction={float(row['full_candidate_reduction']):.1%}"
        )


if __name__ == "__main__":
    main()
