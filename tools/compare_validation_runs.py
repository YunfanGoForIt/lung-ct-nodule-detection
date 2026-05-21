#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path


def read_split(path):
    with path.open(newline="") as file:
        return {row["seriesuid"]: row["split"] for row in csv.DictReader(file)}


def read_summary(root):
    with (root / "subset8_validation_summary.csv").open(newline="") as file:
        return list(csv.DictReader(file))


def metrics(rows, split_map, split_name):
    selected = [row for row in rows if split_map.get(row["seriesuid"]) == split_name]
    annotated = [row for row in selected if int(row["annotations"]) > 0]
    annotations = sum(int(row["annotations"]) for row in annotated)
    strict_hits = sum(int(row["strict_hits"] or 0) for row in annotated)
    relaxed_hits = sum(int(row["relaxed_hits"] or 0) for row in annotated)
    candidates = sum(int(row["candidates"]) for row in selected)
    strict_fp = sum(int(row["strict_false_positives"] or 0) for row in annotated)
    return {
        "cases": len(selected),
        "annotated_cases": len(annotated),
        "annotations": annotations,
        "strict_hits": strict_hits,
        "relaxed_hits": relaxed_hits,
        "strict_recall": strict_hits / annotations if annotations else 0.0,
        "relaxed_recall": relaxed_hits / annotations if annotations else 0.0,
        "candidates": candidates,
        "candidates_per_scan": candidates / len(selected) if selected else 0.0,
        "strict_false_positives_on_annotated_cases": strict_fp,
        "strict_fp_per_scan": strict_fp / len(selected) if selected else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare baseline and tuned validation runs by split.")
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--run", action="append", nargs=2, metavar=("NAME", "ROOT"), required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    split_map = read_split(args.split)
    lines = ["# Subset8 Train/Test Validation Comparison", ""]
    for name, root_text in args.run:
        root = Path(root_text)
        rows = read_summary(root)
        lines.append(f"## {name}")
        lines.append("")
        lines.append("| split | cases | annotated cases | annotations | strict recall | relaxed recall | candidates/scan | strict FP/scan |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for split_name in ("train", "test"):
            item = metrics(rows, split_map, split_name)
            lines.append(
                f"| {split_name} | {item['cases']} | {item['annotated_cases']} | {item['annotations']} | "
                f"{item['strict_hits']}/{item['annotations']} ({item['strict_recall']:.1%}) | "
                f"{item['relaxed_hits']}/{item['annotations']} ({item['relaxed_recall']:.1%}) | "
                f"{item['candidates_per_scan']:.1f} | {item['strict_fp_per_scan']:.1f} |"
            )
        lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
