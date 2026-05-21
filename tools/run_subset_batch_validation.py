#!/usr/bin/env python3
import argparse
import csv
import subprocess
import time
from pathlib import Path

from validate_luna_annotations import (
    count_candidate_hits,
    parse_mhd,
    read_annotations,
    read_features,
    validate,
)


def annotation_counts(path):
    counts = {}
    with path.open(newline="") as file:
        for row in csv.DictReader(file):
            counts[row["seriesuid"]] = counts.get(row["seriesuid"], 0) + 1
    return counts


def write_validation_outputs(case_dir, rows, annotations, features):
    validation_csv = case_dir / "annotation_validation.csv"
    with validation_csv.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    strict_hits = sum(row["strict_hit_distance_le_radius"] for row in rows)
    relaxed_hits = sum(row["relaxed_hit_distance_le_max_radius_10mm"] for row in rows)
    strict_candidate_hits = count_candidate_hits(annotations, features, relaxed=False)
    relaxed_candidate_hits = count_candidate_hits(annotations, features, relaxed=True)
    lines = [
        f"annotations_for_case: {len(annotations)}",
        f"pipeline_candidates: {len(features)}",
        f"strict_annotation_hits_distance_le_annotation_radius: {strict_hits}/{len(annotations)}",
        f"relaxed_annotation_hits_distance_le_max_radius_10mm: {relaxed_hits}/{len(annotations)}",
        f"strict_candidate_true_positive_ids: {len(strict_candidate_hits)}",
        f"relaxed_candidate_true_positive_ids: {len(relaxed_candidate_hits)}",
        f"strict_false_positive_candidates: {len(features) - len(strict_candidate_hits)}",
        f"relaxed_false_positive_candidates: {len(features) - len(relaxed_candidate_hits)}",
    ]
    for row in rows:
        lines.append("")
        lines.append(
            "annotation "
            f"{row['annotation_index']}: "
            f"diameter={row['ann_diameter_mm']:.2f}mm, "
            f"nearest_candidate={row['nearest_candidate_id']}, "
            f"distance={row['distance_mm']:.2f}mm, "
            f"strict_radius={row['strict_radius_mm']:.2f}mm, "
            f"strict_hit={row['strict_hit_distance_le_radius']}, "
            f"relaxed_hit={row['relaxed_hit_distance_le_max_radius_10mm']}"
        )
    (case_dir / "annotation_validation_summary.txt").write_text("\n".join(lines) + "\n")
    return {
        "strict_hits": strict_hits,
        "relaxed_hits": relaxed_hits,
        "strict_candidate_hits": len(strict_candidate_hits),
        "relaxed_candidate_hits": len(relaxed_candidate_hits),
        "strict_false_positives": len(features) - len(strict_candidate_hits),
        "relaxed_false_positives": len(features) - len(relaxed_candidate_hits),
    }


def count_feature_rows(path):
    if not path.exists():
        return 0
    with path.open(newline="") as file:
        return max(0, sum(1 for _ in file) - 1)


def main():
    parser = argparse.ArgumentParser(
        description="Run lung_pipeline over a LUNA16 subset and validate against annotations.csv."
    )
    parser.add_argument("--subset-dir", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--pipeline", default="./build/lung_pipeline", type=Path)
    parser.add_argument(
        "--pipeline-arg",
        action="append",
        default=[],
        help="Extra argument passed to lung_pipeline. Repeat for each token, e.g. --pipeline-arg --min-circularity --pipeline-arg 0.46.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    mhd_files = sorted(args.subset_dir.glob("*.mhd"))
    if args.limit:
        mhd_files = mhd_files[: args.limit]
    counts = annotation_counts(args.annotations)
    args.output_root.mkdir(parents=True, exist_ok=True)

    aggregate_rows = []
    start_all = time.monotonic()
    for index, mhd in enumerate(mhd_files, 1):
        seriesuid = mhd.stem
        case_dir = args.output_root / seriesuid
        case_dir.mkdir(parents=True, exist_ok=True)
        features_path = case_dir / "features.csv"
        log_path = case_dir / "pipeline.log"

        elapsed = 0.0
        status = "ok"
        if not (args.resume and features_path.exists()):
            command = [
                str(args.pipeline),
                str(mhd),
                str(case_dir),
                "--no-debug-images",
            ]
            command.extend(args.pipeline_arg)
            start = time.monotonic()
            completed = subprocess.run(command, text=True, capture_output=True)
            elapsed = time.monotonic() - start
            log_path.write_text(
                "$ " + " ".join(command) + "\n\n"
                + completed.stdout
                + ("\n[stderr]\n" + completed.stderr if completed.stderr else "")
            )
            if completed.returncode != 0:
                status = "pipeline_failed"
        else:
            status = "resumed"

        candidate_count = count_feature_rows(features_path)
        annotated_count = counts.get(seriesuid, 0)
        row = {
            "seriesuid": seriesuid,
            "status": status,
            "annotations": annotated_count,
            "candidates": candidate_count,
            "strict_hits": "",
            "relaxed_hits": "",
            "strict_candidate_hits": "",
            "relaxed_candidate_hits": "",
            "strict_false_positives": "",
            "relaxed_false_positives": "",
            "elapsed_seconds": f"{elapsed:.2f}",
        }

        if status in {"ok", "resumed"} and annotated_count > 0 and candidate_count > 0:
            spacing, offset, transform = parse_mhd(mhd)
            annotations = read_annotations(args.annotations, seriesuid)
            features = read_features(features_path, spacing, offset, transform)
            validation_rows = validate(annotations, features)
            stats = write_validation_outputs(case_dir, validation_rows, annotations, features)
            row.update(
                {
                    "strict_hits": stats["strict_hits"],
                    "relaxed_hits": stats["relaxed_hits"],
                    "strict_candidate_hits": stats["strict_candidate_hits"],
                    "relaxed_candidate_hits": stats["relaxed_candidate_hits"],
                    "strict_false_positives": stats["strict_false_positives"],
                    "relaxed_false_positives": stats["relaxed_false_positives"],
                }
            )
        elif status in {"ok", "resumed"} and annotated_count == 0:
            (case_dir / "annotation_validation_summary.txt").write_text(
                "annotations_for_case: 0\n"
                f"pipeline_candidates: {candidate_count}\n"
                "note: no LUNA16 positive nodule annotations for this seriesuid\n"
            )

        aggregate_rows.append(row)
        print(
            f"[{index}/{len(mhd_files)}] {seriesuid} "
            f"status={status} annotations={annotated_count} candidates={candidate_count}",
            flush=True,
        )

    aggregate_csv = args.output_root / "subset8_validation_summary.csv"
    with aggregate_csv.open("w", newline="") as file:
        fieldnames = list(aggregate_rows[0]) if aggregate_rows else []
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(aggregate_rows)

    annotated_rows = [row for row in aggregate_rows if row["annotations"]]
    total_annotations = sum(int(row["annotations"]) for row in annotated_rows)
    total_strict_hits = sum(int(row["strict_hits"] or 0) for row in annotated_rows)
    total_relaxed_hits = sum(int(row["relaxed_hits"] or 0) for row in annotated_rows)
    total_candidates = sum(int(row["candidates"]) for row in aggregate_rows)
    total_strict_fp = sum(int(row["strict_false_positives"] or 0) for row in annotated_rows)
    failed = sum(1 for row in aggregate_rows if row["status"] == "pipeline_failed")
    total_time = time.monotonic() - start_all

    report_lines = [
        f"cases_total: {len(aggregate_rows)}",
        f"cases_failed: {failed}",
        f"cases_with_annotations: {len(annotated_rows)}",
        f"annotations_total: {total_annotations}",
        f"pipeline_candidates_total_all_cases: {total_candidates}",
        f"strict_annotation_recall: {total_strict_hits}/{total_annotations}",
        f"relaxed_annotation_recall_max_radius_10mm: {total_relaxed_hits}/{total_annotations}",
        f"strict_false_positives_on_annotated_cases: {total_strict_fp}",
        f"elapsed_seconds: {total_time:.2f}",
    ]
    report = args.output_root / "subset8_validation_report.txt"
    report.write_text("\n".join(report_lines) + "\n")
    print("\n".join(report_lines))
    print(f"\nWrote {aggregate_csv}")
    print(f"Wrote {report}")


if __name__ == "__main__":
    main()
