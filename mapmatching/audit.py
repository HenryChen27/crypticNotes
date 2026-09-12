"""Read-only source inventory; no imports from the retired matching system."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np


@dataclass(frozen=True)
class ImageRecord:
    path: str
    role: str
    difficulty: str | None
    mode: str | None
    width: int
    height: int
    channels: int
    format: str
    sha256: str
    pixel_sha256: str
    rgb_mean: list[float]
    gray_percentiles: list[float]
    dark_fraction: float
    bright_fraction: float
    saturated_fraction: float


def read_image(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Cannot decode {path}")
    return image


def classify(path: Path) -> tuple[str, str | None, str | None]:
    parts = path.parts
    # 难度和人数现在直接读 `maps/<难度>/[<人数>/]` 的路径，不再靠中文文件夹名前缀猜。
    if parts[0] == "maps":
        if len(parts) > 1 and parts[1] in ("hard", "nightmare"):
            return ("reference", parts[1],
                    parts[2] if parts[1] == "nightmare" and len(parts) > 2 else None)
        # `maps/_overview/`：一图流总览大图，从来不进索引，也不该被录入
        if len(parts) > 1 and parts[1] == "_overview":
            return "reference_overview", None, None
        # `maps/_unindexed/`：躺在库里但没登记的图，不参与匹配
        return "reference_unregistered", None, None
    if parts[0] == "examples":
        return "example_unclassified", None, None
    return "unverified_raw_candidate" if len(parts) == 1 else "legacy_artifact", None, None


def contact_sheet(root: Path, records: list[dict], output: Path, columns: int = 3) -> None:
    tile_w, tile_h = 480, 310
    canvas = np.full(((len(records) + columns - 1) // columns * tile_h, columns * tile_w, 3), 240, np.uint8)
    for i, record in enumerate(records):
        img = read_image(root / record["path"])
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        img = img[:, :, :3]
        ratio = min((tile_w - 10) / img.shape[1], (tile_h - 35) / img.shape[0])
        img = cv2.resize(img, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA)
        x, y = i % columns * tile_w, i // columns * tile_h
        canvas[y + 30:y + 30 + img.shape[0], x:x + img.shape[1]] = img
        cv2.putText(canvas, f"{i}: {record['width']}x{record['height']}", (x + 5, y + 22), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 0), 1)
    cv2.imencode(".jpg", canvas)[1].tofile(output)
    output.with_suffix(".json").write_text(json.dumps([r["path"] for r in records], ensure_ascii=False, indent=2), encoding="utf-8")


def run(root: Path) -> dict:
    start = time.perf_counter()
    output = root / "out/mapmatching"
    output.mkdir(parents=True, exist_ok=True)
    # 排除：`.git`、包目录本身、以及 `maps/evidence` —— 最后一个是逐张图的特征
    # 派生物（几十 MB 的 npz），不是待审计的图。
    excluded = (".git", "mapmatching")
    files = sorted(p for p in root.rglob("*")
                   if p.is_file() and not any(v in p.parts for v in excluded)
                   and p.parts[:2] != ("maps", "evidence"))
    inventory, records, failures = [], [], []
    for path in files:
        relative = path.relative_to(root)
        inventory.append({"path": relative.as_posix(), "bytes": path.stat().st_size})
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            continue
        try:
            image = read_image(path)
            bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image[:, :, :3]
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            role, difficulty, mode = classify(relative)
            raw = path.read_bytes()
            fmt = "PNG" if raw.startswith(b"\x89PNG") else "JPEG" if raw.startswith(b"\xff\xd8") else path.suffix[1:].upper()
            record = ImageRecord(relative.as_posix(), role, difficulty, mode, image.shape[1], image.shape[0], 1 if image.ndim == 2 else image.shape[2], fmt, hashlib.sha256(raw).hexdigest(), hashlib.sha256(str(image.shape).encode() + image.tobytes()).hexdigest(), np.round(bgr.mean(axis=(0, 1))[::-1], 3).tolist(), np.percentile(gray, [0, 10, 25, 50, 75, 90, 100]).tolist(), float(np.mean(gray < 40)), float(np.mean(gray > 220)), float(np.mean(hsv[:, :, 1] > 80)))
            records.append(asdict(record))
        except (ValueError, cv2.error) as error:
            failures.append({"path": relative.as_posix(), "error": str(error)})
    reference_hashes = defaultdict(list)
    all_hashes = defaultdict(list)
    for r in records:
        all_hashes[r["pixel_sha256"]].append(r["path"])
        if r["role"] == "reference":
            reference_hashes[r["pixel_sha256"]].append(r["path"])
    for r in records:
        if r["role"] == "example_unclassified":
            matches = reference_hashes.get(r["pixel_sha256"], [])
            r["role"] = "example_reference" if matches else "example_screenshot_candidate"
            r["exact_reference_matches"] = matches
    refs = [r for r in records if r["role"] == "reference"]
    examples = [r for r in records if r["path"].startswith("examples/")]
    report = {"schema_version": 1, "root": str(root), "method": "OpenCV full-resolution decoding; exact file/pixel hashes; RGB mean; gray percentiles [0,10,25,50,75,90,100]; intensity fractions are NOT fog labels", "inventory": inventory, "images": records, "decode_failures": failures, "duplicate_pixel_groups": [v for v in all_hashes.values() if len(v) > 1], "counts": {"files": len(files), "images": len(records), "roles": dict(Counter(r["role"] for r in records)), "reference_groups": dict(Counter(f"{r['difficulty']}/{r['mode']}" for r in refs))}, "legacy_python": [v["path"] for v in inventory if v["path"].endswith(".py")], "legacy_benchmarks": [v["path"] for v in inventory if v["path"].endswith(".py") and "bench" in v["path"]], "audit_runtime_seconds": time.perf_counter() - start}
    (output / "data_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    contact_sheet(root, examples, output / "examples_contact.jpg")
    for offset in range(0, len(refs), 18):
        contact_sheet(root, refs[offset:offset + 18], output / f"references_{offset:02d}.jpg")
    print(json.dumps(report["counts"], ensure_ascii=True))
    print("Audit seconds:", report["audit_runtime_seconds"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    run(parser.parse_args().root.resolve())
