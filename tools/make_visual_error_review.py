#!/usr/bin/env python3
import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ANNOTATIONS = ROOT / "data/luna16_zenodo/csv/annotations.csv"


CASES = [
    ("all_miss_202283", "1.3.6.1.4.1.14519.5.2.1.6279.6001.202283133206014258077705539227", ROOT / "data/visual_review_202283_tuned"),
    ("mixed_239358", "1.3.6.1.4.1.14519.5.2.1.6279.6001.239358021703233250639913775427", ROOT / "data/visual_review_239358_tuned"),
    ("all_hit_204287", "1.3.6.1.4.1.14519.5.2.1.6279.6001.204287915902811325371247860532", ROOT / "data/visual_review_204287_tuned"),
    ("single_mixed_100225", "1.3.6.1.4.1.14519.5.2.1.6279.6001.100225287222365663678666836860", ROOT / "data/real_gui_100225_tuned"),
]


def parse_mhd(path):
    meta = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        meta[key] = value
    spacing = [float(x) for x in meta["ElementSpacing"].split()]
    offset = [float(x) for x in meta["Offset"].split()]
    transform = [float(x) for x in meta.get("TransformMatrix", "1 0 0 0 1 0 0 0 1").split()]
    dims = [int(x) for x in meta["DimSize"].split()]
    return spacing, offset, transform, dims


def inverse3(m):
    a, b, c, d, e, f, g, h, i = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-8:
        raise ValueError("singular transform")
    return [
        (e * i - f * h) / det,
        (c * h - b * i) / det,
        (b * f - c * e) / det,
        (f * g - d * i) / det,
        (a * i - c * g) / det,
        (c * d - a * f) / det,
        (d * h - e * g) / det,
        (b * g - a * h) / det,
        (a * e - b * d) / det,
    ]


def world_to_voxel(world, spacing, offset, transform):
    inv = inverse3(transform)
    delta = [world[k] - offset[k] for k in range(3)]
    scaled = [
        inv[0] * delta[0] + inv[1] * delta[1] + inv[2] * delta[2],
        inv[3] * delta[0] + inv[4] * delta[1] + inv[5] * delta[2],
        inv[6] * delta[0] + inv[7] * delta[1] + inv[8] * delta[2],
    ]
    return [scaled[k] / spacing[k] for k in range(3)]


def read_annotations(seriesuid):
    rows = []
    with ANNOTATIONS.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["seriesuid"] == seriesuid:
                rows.append({
                    "coordX": float(row["coordX"]),
                    "coordY": float(row["coordY"]),
                    "coordZ": float(row["coordZ"]),
                    "diameter_mm": float(row["diameter_mm"]),
                })
    return rows


def read_validation(case_dir):
    path = case_dir / "annotation_validation.csv"
    if not path.exists():
        return {}
    out = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            out[int(row["annotation_index"])] = row
    return out


def read_features(case_dir):
    rows = []
    with (case_dir / "features.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            for key in ["center_x", "center_y", "center_z", "diameter_mm", "mean_hu", "std_hu", "glcm_contrast", "glcm_homogeneity"]:
                row[key] = float(row[key])
            row["id"] = int(row["id"])
            rows.append(row)
    return rows


def draw_ring(draw, x, y, r, color, width=3):
    for k in range(width):
        draw.ellipse((x - r - k, y - r - k, x + r + k, y + r + k), outline=color)


def crop_with_bounds(image, cx, cy, size=176):
    half = size // 2
    left = max(0, min(image.width - size, int(round(cx)) - half))
    top = max(0, min(image.height - size, int(round(cy)) - half))
    return image.crop((left, top, left + size, top + size)), left, top


def label(draw, text, xy, fill=(255, 255, 255)):
    draw.rectangle((xy[0] - 2, xy[1] - 2, xy[0] + 360, xy[1] + 16), fill=(0, 0, 0))
    draw.text(xy, text, fill=fill, font=ImageFont.load_default())


def make_annotation_montage(case_name, seriesuid, case_dir, out_dir):
    mhd = ROOT / "data/luna16_subset8_download/subset8" / f"{seriesuid}.mhd"
    spacing, offset, transform, dims = parse_mhd(mhd)
    annotations = read_annotations(seriesuid)
    validation = read_validation(case_dir)
    tiles = []
    for index, ann in enumerate(annotations, 1):
        vx, vy, vz = world_to_voxel((ann["coordX"], ann["coordY"], ann["coordZ"]), spacing, offset, transform)
        z = max(0, min(dims[2] - 1, int(round(vz))))
        overlay_path = case_dir / f"slice_{z:03d}_overlay.ppm"
        window_path = case_dir / f"slice_{z:03d}_window.pgm"
        if not overlay_path.exists():
            continue
        overlay = Image.open(overlay_path).convert("RGB")
        window = Image.open(window_path).convert("RGB")
        radius_px = max(5, int(round((ann["diameter_mm"] * 0.5) / max(0.001, (spacing[0] + spacing[1]) * 0.5))))
        for img in [overlay, window]:
            draw = ImageDraw.Draw(img)
            draw_ring(draw, vx, vy, radius_px, (0, 220, 255), 3)
        crop_overlay, left, top = crop_with_bounds(overlay, vx, vy)
        crop_window, _, _ = crop_with_bounds(window, vx, vy)
        tile = Image.new("RGB", (352, 210), (25, 25, 25))
        tile.paste(crop_window, (0, 34))
        tile.paste(crop_overlay, (176, 34))
        draw = ImageDraw.Draw(tile)
        val = validation.get(index, {})
        hit = val.get("strict_hit_distance_le_radius", "n/a")
        dist = val.get("distance_mm", "")
        cand = val.get("nearest_candidate_id", "?")
        title = f"{case_name} ann{index} z={z} dia={ann['diameter_mm']:.1f} hit={hit}"
        label(draw, title[:52], (4, 4), (0, 220, 255) if hit == "True" else (255, 210, 80))
        if dist:
            detail = f"nearest={cand} dist={float(dist):.1f}mm"
        else:
            detail = f"nearest={cand}"
        label(draw, detail, (4, 20), (255, 255, 255))
        tiles.append(tile)
    if not tiles:
        return None
    cols = 2
    rows = math.ceil(len(tiles) / cols)
    montage = Image.new("RGB", (cols * 352, rows * 210), (15, 15, 15))
    for i, tile in enumerate(tiles):
        montage.paste(tile, ((i % cols) * 352, (i // cols) * 210))
    out = out_dir / f"{case_name}_annotations.png"
    montage.save(out)
    return out


def make_false_positive_montage(case_name, case_dir, out_dir, max_tiles=12):
    features = read_features(case_dir)[:max_tiles]
    tiles = []
    for row in features:
        z = int(round(row["center_z"]))
        overlay_path = case_dir / f"slice_{z:03d}_overlay.ppm"
        if not overlay_path.exists():
            continue
        overlay = Image.open(overlay_path).convert("RGB")
        draw = ImageDraw.Draw(overlay)
        draw_ring(draw, row["center_x"], row["center_y"], max(6, int(row["diameter_mm"])), (255, 255, 0), 2)
        crop, _, _ = crop_with_bounds(overlay, row["center_x"], row["center_y"], 150)
        tile = Image.new("RGB", (150, 184), (25, 25, 25))
        tile.paste(crop, (0, 34))
        draw = ImageDraw.Draw(tile)
        label(draw, f"id{row['id']} z={z} d={row['diameter_mm']:.1f}", (3, 3), (255, 255, 0))
        label(draw, f"HU={row['mean_hu']:.0f} hom={row['glcm_homogeneity']:.2f}", (3, 18), (255, 255, 255))
        tiles.append(tile)
    cols = 4
    rows = math.ceil(len(tiles) / cols)
    montage = Image.new("RGB", (cols * 150, rows * 184), (15, 15, 15))
    for i, tile in enumerate(tiles):
        montage.paste(tile, ((i % cols) * 150, (i // cols) * 184))
    out = out_dir / f"{case_name}_top_candidates.png"
    montage.save(out)
    return out


def main():
    out_dir = ROOT / "data/visual_error_review"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for case_name, seriesuid, case_dir in CASES:
        outputs.append(make_annotation_montage(case_name, seriesuid, case_dir, out_dir))
        outputs.append(make_false_positive_montage(case_name, case_dir, out_dir))
    for out in outputs:
        if out:
            print(out)


if __name__ == "__main__":
    main()
