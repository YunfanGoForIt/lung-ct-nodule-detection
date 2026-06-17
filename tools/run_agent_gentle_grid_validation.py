#!/usr/bin/env python3
import argparse
import csv
import subprocess
import time
from pathlib import Path

from run_subset_batch_validation import (
    annotation_counts,
    count_feature_rows,
    write_validation_outputs,
)
from validate_luna_annotations import parse_mhd, read_annotations, read_features, validate


BASE_ARGS = [
    "--min-circularity", "0.46",
    "--final-min-mean-hu", "-410",
    "--final-max-mean-hu", "60",
    "--final-min-std-hu", "25",
    "--final-max-std-hu", "210",
    "--final-max-glcm-contrast", "3.3",
    "--final-min-glcm-homogeneity", "0.45",
    "--final-max-slice-count", "18",
    "--max-final-candidates", "180",
]


SAMPLE_SERIES = [
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.239358021703233250639913775427",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.168833925301530155818375859047",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.299806338046301317870803017534",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.202283133206014258077705539227",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.288701997968615460794642979503",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.131939324905446238286154504249",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.153732973534937692357111055819",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.177086402277715068525592995222",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.188059920088313909273628445208",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.108193664222196923321844991231",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.161821150841552408667852639317",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.246178337114401749164850220976",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.283878926524838648426928238498",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.236698827306171960683086245994",
    "1.3.6.1.4.1.14519.5.2.1.6279.6001.203425588524695836343069893813",
]


GRIDS = {
    "pct86_cap150_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "86",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct86_cap120_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "86",
        "--max-final-candidates", "120",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct86_cap150_seed220_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "86",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "220",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct87_cap150_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "87",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct87_cap120_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "87",
        "--max-final-candidates", "120",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct87_cap150_seed220_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "87",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "220",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct88_cap150_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "88",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct88_cap120_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "88",
        "--max-final-candidates", "120",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct88_cap150_seed220_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "88",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "220",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct89_cap150_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "89",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct89_cap120_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "89",
        "--max-final-candidates", "120",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct89_cap150_seed220_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "89",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "220",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct87_cap100_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "87",
        "--max-final-candidates", "100",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct88_cap100_seed250_bd0p5_pen0p2": [
        "--candidate-bandpass-percentile", "88",
        "--max-final-candidates", "100",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct86_cap150_seed250_bd1p0_pen0p2": [
        "--candidate-bandpass-percentile", "86",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "1.0",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct87_cap150_seed250_bd1p0_pen0p2": [
        "--candidate-bandpass-percentile", "87",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "1.0",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct88_cap150_seed250_bd1p0_pen0p2": [
        "--candidate-bandpass-percentile", "88",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "1.0",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct87_cap150_seed250_bd1p5_pen0p2": [
        "--candidate-bandpass-percentile", "87",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "1.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct88_cap150_seed250_bd1p5_pen0p2": [
        "--candidate-bandpass-percentile", "88",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "1.5",
        "--rank-slice-count-penalty", "0.2",
    ],
    "pct87_cap150_seed250_bd0p5_pen0p4": [
        "--candidate-bandpass-percentile", "87",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.4",
    ],
    "pct88_cap150_seed250_bd0p5_pen0p4": [
        "--candidate-bandpass-percentile", "88",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.4",
    ],
    "pct87_cap150_seed250_bd0p5_pen0p6": [
        "--candidate-bandpass-percentile", "87",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.6",
    ],
    "pct88_cap150_seed250_bd0p5_pen0p6": [
        "--candidate-bandpass-percentile", "88",
        "--max-final-candidates", "150",
        "--candidate-max-seed-hu", "250",
        "--final-min-boundary-distance-mm", "0.5",
        "--rank-slice-count-penalty", "0.6",
    ],
}


def run_one(name, extra_args, args, counts):
    out_root = args.output_root / name
    out_root.mkdir(parents=True, exist_ok=True)
    rows = []
    start_all = time.monotonic()
    for seriesuid in SAMPLE_SERIES:
        mhd = args.subset_dir / f"{seriesuid}.mhd"
        case_dir = out_root / seriesuid
        case_dir.mkdir(parents=True, exist_ok=True)
        command = [str(args.pipeline), str(mhd), str(case_dir), "--no-debug-images"]
        command.extend(BASE_ARGS)
        command.extend(extra_args)
        start = time.monotonic()
        completed = subprocess.run(command, text=True, capture_output=True)
        elapsed = time.monotonic() - start
        (case_dir / "pipeline.log").write_text(
            "$ " + " ".join(command) + "\n\n" + completed.stdout
            + ("\n[stderr]\n" + completed.stderr if completed.stderr else "")
        )
        status = "ok" if completed.returncode == 0 else "pipeline_failed"
        features_path = case_dir / "features.csv"
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
        if status == "ok" and annotated_count > 0 and candidate_count > 0:
            spacing, offset, transform = parse_mhd(mhd)
            annotations = read_annotations(args.annotations, seriesuid)
            features = read_features(features_path, spacing, offset, transform)
            validation_rows = validate(annotations, features)
            stats = write_validation_outputs(case_dir, validation_rows, annotations, features)
            row.update({key: stats[key] for key in stats})
        rows.append(row)

    summary_path = out_root / "sample_validation_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    annotated = [row for row in rows if row["annotations"]]
    total_ann = sum(int(row["annotations"]) for row in annotated)
    strict = sum(int(row["strict_hits"] or 0) for row in annotated)
    relaxed = sum(int(row["relaxed_hits"] or 0) for row in annotated)
    candidates = sum(int(row["candidates"]) for row in rows)
    strict_fp = sum(int(row["strict_false_positives"] or 0) for row in annotated)
    failed = sum(1 for row in rows if row["status"] != "ok")
    return {
        "name": name,
        "cases": len(rows),
        "failed": failed,
        "annotations": total_ann,
        "strict_hits": strict,
        "relaxed_hits": relaxed,
        "candidates": candidates,
        "strict_fp": strict_fp,
        "elapsed_seconds": f"{time.monotonic() - start_all:.2f}",
        "args": " ".join(extra_args),
    }


def write_markdown(path, rows):
    ordered = sorted(
        rows,
        key=lambda row: (
            -int(row["strict_hits"]),
            -int(row["relaxed_hits"]),
            int(row["candidates"]),
            int(row["strict_fp"]),
        ),
    )
    lines = [
        "| rank | config | strict | relaxed | candidates | strict FP | args |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for index, row in enumerate(ordered, 1):
        lines.append(
            f"| {index} | {row['name']} | {row['strict_hits']}/{row['annotations']} | "
            f"{row['relaxed_hits']}/{row['annotations']} | {row['candidates']} | "
            f"{row['strict_fp']} | `{row['args']}` |"
        )
    path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset-dir", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--pipeline", default=Path("./build/lung_pipeline"), type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    counts = annotation_counts(args.annotations)
    summaries = []
    for name, extra_args in GRIDS.items():
        print(f"== {name} ==", flush=True)
        summary = run_one(name, extra_args, args, counts)
        summaries.append(summary)
        print(summary, flush=True)
    out = args.output_root / "agent_gentle_grid_summary.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    write_markdown(args.output_root / "agent_gentle_grid_summary.md", summaries)
    print(f"Wrote {out}")
    print(f"Wrote {args.output_root / 'agent_gentle_grid_summary.md'}")


if __name__ == "__main__":
    main()
