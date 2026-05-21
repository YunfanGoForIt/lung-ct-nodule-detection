#!/usr/bin/env python3
import argparse
import csv
import math
from pathlib import Path


def parse_mhd(path):
    meta = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        meta[key] = value
    spacing = [float(x) for x in meta["ElementSpacing"].split()]
    offset = [float(x) for x in meta["Offset"].split()]
    transform = [
        float(x)
        for x in meta.get("TransformMatrix", "1 0 0 0 1 0 0 0 1").split()
    ]
    return spacing, offset, transform


def voxel_to_world(x, y, z, spacing, offset, transform):
    scaled = [x * spacing[0], y * spacing[1], z * spacing[2]]
    return (
        offset[0]
        + transform[0] * scaled[0]
        + transform[1] * scaled[1]
        + transform[2] * scaled[2],
        offset[1]
        + transform[3] * scaled[0]
        + transform[4] * scaled[1]
        + transform[5] * scaled[2],
        offset[2]
        + transform[6] * scaled[0]
        + transform[7] * scaled[1]
        + transform[8] * scaled[2],
    )


def read_annotations(path, seriesuid):
    annotations = []
    with path.open(newline="") as file:
        for row in csv.DictReader(file):
            if row["seriesuid"] != seriesuid:
                continue
            annotations.append(
                {
                    "coordX": float(row["coordX"]),
                    "coordY": float(row["coordY"]),
                    "coordZ": float(row["coordZ"]),
                    "diameter_mm": float(row["diameter_mm"]),
                }
            )
    return annotations


def read_features(path, spacing, offset, transform):
    features = []
    with path.open(newline="") as file:
        for row in csv.DictReader(file):
            world = voxel_to_world(
                float(row["center_x"]),
                float(row["center_y"]),
                float(row["center_z"]),
                spacing,
                offset,
                transform,
            )
            converted = dict(row)
            converted["world_x"], converted["world_y"], converted["world_z"] = world
            features.append(converted)
    return features


def validate(annotations, features):
    rows = []
    for index, annotation in enumerate(annotations, 1):
        nearest_distance, nearest = min(
            (
                (
                    math.dist(
                        (
                            annotation["coordX"],
                            annotation["coordY"],
                            annotation["coordZ"],
                        ),
                        (
                            feature["world_x"],
                            feature["world_y"],
                            feature["world_z"],
                        ),
                    ),
                    feature,
                )
                for feature in features
            ),
            key=lambda item: item[0],
        )
        strict_radius = annotation["diameter_mm"] / 2.0
        relaxed_radius = max(strict_radius, 10.0)
        rows.append(
            {
                "annotation_index": index,
                "ann_x": annotation["coordX"],
                "ann_y": annotation["coordY"],
                "ann_z": annotation["coordZ"],
                "ann_diameter_mm": annotation["diameter_mm"],
                "nearest_candidate_id": nearest["id"],
                "candidate_voxel_x": nearest["center_x"],
                "candidate_voxel_y": nearest["center_y"],
                "candidate_slice_z": nearest["center_z"],
                "candidate_world_x": nearest["world_x"],
                "candidate_world_y": nearest["world_y"],
                "candidate_world_z": nearest["world_z"],
                "candidate_diameter_mm": nearest["diameter_mm"],
                "distance_mm": nearest_distance,
                "strict_radius_mm": strict_radius,
                "strict_hit_distance_le_radius": nearest_distance <= strict_radius,
                "relaxed_hit_distance_le_max_radius_10mm": nearest_distance
                <= relaxed_radius,
            }
        )
    return rows


def count_candidate_hits(annotations, features, relaxed=False):
    hit_ids = set()
    for feature in features:
        for annotation in annotations:
            radius = annotation["diameter_mm"] / 2.0
            if relaxed:
                radius = max(radius, 10.0)
            distance = math.dist(
                (annotation["coordX"], annotation["coordY"], annotation["coordZ"]),
                (feature["world_x"], feature["world_y"], feature["world_z"]),
            )
            if distance <= radius:
                hit_ids.add(feature["id"])
    return hit_ids


def main():
    parser = argparse.ArgumentParser(
        description="Validate pipeline candidates against LUNA16 annotations.csv."
    )
    parser.add_argument("--mhd", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    seriesuid = args.mhd.stem
    spacing, offset, transform = parse_mhd(args.mhd)
    annotations = read_annotations(args.annotations, seriesuid)
    features = read_features(args.features, spacing, offset, transform)

    if not annotations:
        raise SystemExit(f"No annotations found for seriesuid: {seriesuid}")
    if not features:
        raise SystemExit(f"No candidate features found: {args.features}")

    rows = validate(annotations, features)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    strict_hits = sum(row["strict_hit_distance_le_radius"] for row in rows)
    relaxed_hits = sum(row["relaxed_hit_distance_le_max_radius_10mm"] for row in rows)
    strict_candidate_hits = count_candidate_hits(annotations, features, relaxed=False)
    relaxed_candidate_hits = count_candidate_hits(annotations, features, relaxed=True)
    summary = args.out.with_name(args.out.stem + "_summary.txt")
    lines = [
        f"seriesuid: {seriesuid}",
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
    summary.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWrote {args.out}")
    print(f"Wrote {summary}")


if __name__ == "__main__":
    main()
