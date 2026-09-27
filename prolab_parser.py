from __future__ import annotations

from io import BytesIO
import re
from typing import BinaryIO, Iterable

import fitz


AIR_SAMPLE_CODES = {"PRO-15", "PRO15", "P15", "AOC", "BRZ", "BREEZE", "SPORE TRAP", "ST"}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _upper(value: str) -> str:
    return _norm(value).upper()


def _as_bytes(pdf: bytes | bytearray | BinaryIO) -> bytes:
    if isinstance(pdf, (bytes, bytearray)):
        return bytes(pdf)
    pos = None
    try:
        pos = pdf.tell()
    except Exception:
        pass
    data = pdf.read()
    if pos is not None:
        try:
            pdf.seek(pos)
        except Exception:
            pass
    return data


def _extract_metadata(first_page_text: str) -> dict:
    lines = [_norm(x) for x in first_page_text.splitlines() if _norm(x)]

    def after(label: str) -> str:
        target = _upper(label)
        for i, line in enumerate(lines):
            if _upper(line).rstrip(":") == target.rstrip(":"):
                if i + 1 < len(lines):
                    return lines[i + 1]
        return ""

    return {
        "project_name": after("Project Name:"),
        "report_number": after("Report Number:"),
        "received_date": after("Received Date:"),
        "report_date": after("Report Date:"),
        "prepared_for": after("Prepared for:"),
        "test_location": _extract_test_location(lines),
    }


def _extract_test_location(lines: list[str]) -> str:
    for i, line in enumerate(lines):
        if _upper(line).rstrip(":") == "TEST LOCATION":
            parts = []
            for next_line in lines[i + 1 : i + 4]:
                if _upper(next_line).startswith(("REPORT NUMBER", "RECEIVED DATE", "REPORT DATE")):
                    break
                parts.append(next_line)
            return ", ".join(parts)
    return ""


def _words_by_line(words: list[tuple], tolerance: float = 1.4) -> list[dict]:
    usable = [
        {"x0": float(w[0]), "y0": float(w[1]), "x1": float(w[2]), "y1": float(w[3]), "text": str(w[4])}
        for w in words
    ]
    usable.sort(key=lambda w: (w["y0"], w["x0"]))
    lines: list[dict] = []
    for word in usable:
        if not lines or abs(word["y0"] - lines[-1]["y"]) > tolerance:
            lines.append({"y": word["y0"], "words": [word]})
        else:
            lines[-1]["words"].append(word)
            ys = [x["y0"] for x in lines[-1]["words"]]
            lines[-1]["y"] = sum(ys) / len(ys)
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
        line["text"] = _norm(" ".join(w["text"] for w in line["words"]))
    return lines


def _left_text(line: dict, cutoff: float = 130.0) -> str:
    return _norm(" ".join(w["text"] for w in line["words"] if w["x0"] < cutoff))


def _find_row(lines: list[dict], label: str, start_y: float = 0.0) -> dict | None:
    target = _upper(label)
    for line in lines:
        if line["y"] < start_y:
            continue
        if target in _upper(_left_text(line)):
            return line
    return None


def _column_bounds(centers: list[float], data_left: float = 130.0, page_right: float = 590.0) -> list[tuple[float, float]]:
    if not centers:
        return []
    centers = sorted(centers)
    bounds = []
    for i, center in enumerate(centers):
        left = data_left if i == 0 else (centers[i - 1] + center) / 2.0
        right = page_right if i == len(centers) - 1 else (center + centers[i + 1]) / 2.0
        # PRO-LAB result pages reserve up to four table slots. Keep the final
        # populated sample from swallowing text in intentionally-blank slots.
        if len(centers) < 4:
            nominal_width = 110.0
            left = max(left, center - nominal_width / 2.0)
            right = min(right, center + nominal_width / 2.0)
        bounds.append((left, right))
    return bounds


def _words_in_region(words: list[dict], y0: float, y1: float, x0: float, x1: float) -> list[dict]:
    return sorted(
        [w for w in words if y0 <= w["y0"] < y1 and x0 <= (w["x0"] + w["x1"]) / 2.0 < x1],
        key=lambda w: (w["y0"], w["x0"]),
    )


def _region_text(words: list[dict], y0: float, y1: float, x0: float, x1: float) -> str:
    region = _words_in_region(words, y0, y1, x0, x1)
    if not region:
        return ""
    out: list[str] = []
    current_y = None
    current_line: list[str] = []
    for w in region:
        if current_y is None or abs(w["y0"] - current_y) <= 1.4:
            current_line.append(w["text"])
            current_y = w["y0"] if current_y is None else current_y
        else:
            out.append(" ".join(current_line))
            current_line = [w["text"]]
            current_y = w["y0"]
    if current_line:
        out.append(" ".join(current_line))
    return _norm(" ".join(out))


def _numeric_nearest(words: list[dict], y: float, center: float, tolerance_y: float = 2.0, max_dx: float = 50.0):
    candidates = []
    for w in words:
        if abs(w["y0"] - y) > tolerance_y:
            continue
        txt = w["text"].replace(",", "")
        if not re.fullmatch(r"\d+(?:\.\d+)?", txt):
            continue
        cx = (w["x0"] + w["x1"]) / 2.0
        dx = abs(cx - center)
        if dx <= max_dx:
            candidates.append((dx, txt))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    txt = candidates[0][1]
    return int(float(txt)) if float(txt).is_integer() else float(txt)


def _sample_key(sample: dict, page_number: int, index: int) -> str:
    return sample.get("coc_line") or sample.get("serial_number") or f"page{page_number}_sample{index + 1}"


def _parse_result_page(page: fitz.Page, page_number: int) -> tuple[list[dict], list[str]]:
    text = page.get_text("text")
    if "COC / LINE #" not in text or "DETERMINATION" not in text:
        return [], []

    words_raw = page.get_text("words")
    all_words = [
        {"x0": float(w[0]), "y0": float(w[1]), "x1": float(w[2]), "y1": float(w[3]), "text": str(w[4])}
        for w in words_raw
    ]
    lines = _words_by_line(words_raw)
    warnings: list[str] = []

    coc_row = _find_row(lines, "COC")
    sample_type_row = _find_row(lines, "SAMPLE TYPE")
    determination_row = _find_row(lines, "DETERMINATION")
    identification_row = _find_row(lines, "IDENTIFICATION")
    total_row = _find_row(lines, "TOTAL SPORES")

    if not coc_row or not sample_type_row or not determination_row:
        return [], [f"Page {page_number}: result table headings were found, but key rows could not be located."]

    report_number_words = [
        w for w in coc_row["words"]
        if w["x0"] >= 130 and re.fullmatch(r"\d{5,}", w["text"].replace(",", ""))
    ]
    centers = sorted((w["x0"] + w["x1"]) / 2.0 for w in report_number_words)
    if not centers:
        return [], [f"Page {page_number}: could not determine populated sample columns."]

    bounds = _column_bounds(centers, page_right=float(page.rect.width) - 20)
    location_row = _find_row(lines, "LOCATION")
    volume_row = _find_row(lines, "VOLUME")
    serial_row = _find_row(lines, "SERIAL NUMBER")
    collection_row = _find_row(lines, "COLLECTION DATE")
    analysis_date_row = _find_row(lines, "ANALYSIS DATE")

    row_order = [
        r
        for r in [
            location_row,
            coc_row,
            sample_type_row,
            volume_row,
            serial_row,
            collection_row,
            analysis_date_row,
            determination_row,
            identification_row,
        ]
        if r
    ]

    def next_y(row: dict, fallback: float | None = None) -> float:
        later = sorted(r["y"] for r in row_order if r["y"] > row["y"] + 0.5)
        if later:
            return later[0]
        return fallback if fallback is not None else row["y"] + 13.0

    samples: list[dict] = []
    for idx, (center, (left, right)) in enumerate(zip(centers, bounds)):
        coc_text = _region_text(all_words, coc_row["y"] - 1, next_y(coc_row), left, right)
        coc_match = re.search(r"(\d+)\s*-\s*(\d+)", coc_text)
        coc_line = f"{coc_match.group(1)}-{coc_match.group(2)}" if coc_match else _norm(coc_text)

        location = ""
        if location_row:
            location = _region_text(all_words, location_row["y"] - 6, coc_row["y"] - 0.2, left, right)

        sample_type = _region_text(all_words, sample_type_row["y"] - 1, next_y(sample_type_row), left, right)
        volume = _region_text(all_words, volume_row["y"] - 1, next_y(volume_row), left, right) if volume_row else ""
        serial = _region_text(all_words, serial_row["y"] - 1, next_y(serial_row), left, right) if serial_row else ""
        collection_date = (
            _region_text(all_words, collection_row["y"] - 1, next_y(collection_row), left, right)
            if collection_row
            else ""
        )
        analysis_date = (
            _region_text(all_words, analysis_date_row["y"] - 1, next_y(analysis_date_row), left, right)
            if analysis_date_row
            else ""
        )
        determination = _region_text(
            all_words,
            determination_row["y"] - 1,
            determination_row["y"] + 9.5,
            left,
            right,
        )

        sample = {
            "key": "",
            "page": page_number,
            "location": location,
            "coc_line": coc_line,
            "sample_type": sample_type,
            "volume": volume,
            "serial_number": serial,
            "collection_date": collection_date,
            "analysis_date": analysis_date,
            "determination": _upper(determination),
            "total_spores": None,
            "fungi": {},
            "is_air": _upper(sample_type) in AIR_SAMPLE_CODES or bool(volume),
        }
        sample["key"] = _sample_key(sample, page_number, idx)
        samples.append(sample)

    # Read only the actual result-table band. Narrative definitions and mold
    # reference pages never become findings.
    if identification_row and total_row and any(s["is_air"] for s in samples):
        species_lines = [
            line
            for line in lines
            if identification_row["y"] + 5 < line["y"] < total_row["y"] - 1 and _left_text(line)
        ]
        for line in species_lines:
            species = _norm(_left_text(line))
            if not species or _upper(species) in {"RAW COUNT", "SPORES PER M³", "PERCENT OF TOTAL"}:
                continue
            for sample, center in zip(samples, centers):
                value = _numeric_nearest(all_words, line["y"], center)
                if value is not None:
                    sample["fungi"][species] = int(value)

        for sample, center in zip(samples, centers):
            sample["total_spores"] = _numeric_nearest(all_words, total_row["y"], center)

    return samples, warnings


def parse_prolab_pdf(pdf: bytes | bytearray | BinaryIO) -> dict:
    """Parse structured PRO-LAB result tables without scanning narrative pages.

    Mold detections and lab determinations are read only from the result table.
    Text such as "ELEVATED means..." and species reference pages is ignored.
    """
    pdf_bytes = _as_bytes(pdf)
    result = {
        "metadata": {},
        "samples": [],
        "warnings": [],
        "page_count": 0,
    }
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        result["warnings"].append(f"Could not open PDF: {exc}")
        return result

    try:
        result["page_count"] = len(doc)
        if len(doc):
            result["metadata"] = _extract_metadata(doc[0].get_text("text"))
        for page_index in range(len(doc)):
            samples, warnings = _parse_result_page(doc[page_index], page_index + 1)
            result["samples"].extend(samples)
            result["warnings"].extend(warnings)
    finally:
        doc.close()

    if not result["samples"]:
        result["warnings"].append("No structured PRO-LAB sample result table was found.")
    return result


def suggested_mapping(parsed: dict, job: dict) -> dict[str, str]:
    """Suggest lab-sample -> job-sample mappings without mutating the job."""
    mappings: dict[str, str] = {}
    parsed_samples = parsed.get("samples", [])
    job_samples = job.get("samples", [])

    outdoor_jobs = [s for s in job_samples if s.get("outdoor_control")]
    indoor_air_jobs = [s for s in job_samples if s.get("type") == "Air Sample" and not s.get("outdoor_control")]
    swab_jobs = [s for s in job_samples if s.get("type") == "Swab"]

    used: set[str] = set()
    for lab in parsed_samples:
        loc = _upper(lab.get("location", ""))
        det = _upper(lab.get("determination", ""))
        is_control = "OUTDOOR" in loc or det == "CONTROL"
        candidates = outdoor_jobs if is_control else (indoor_air_jobs if lab.get("is_air") else swab_jobs)
        target = next((s for s in candidates if s["id"] not in used), None)
        if target:
            mappings[lab["key"]] = target["id"]
            used.add(target["id"])
    return mappings


def apply_prolab_results(
    job: dict,
    parsed: dict,
    mapping: dict[str, str],
    supported_molds: Iterable[str],
) -> dict:
    """Apply reviewed parsed results to V2 without deciding report outcome."""
    supported = set(supported_molds)
    sample_map = {s["id"]: s for s in job.get("samples", [])}
    air_rows: list[dict] = []
    surface_rows: list[dict] = []
    detected_molds: list[str] = []

    from models import new_air_lab_row, new_surface_lab_row

    for lab in parsed.get("samples", []):
        job_sample_id = mapping.get(lab.get("key", ""))
        if not job_sample_id or job_sample_id not in sample_map:
            continue

        job_sample = sample_map[job_sample_id]
        job_sample["lab_coc_line"] = lab.get("coc_line", "")
        job_sample["lab_serial_number"] = lab.get("serial_number", "")
        job_sample["lab_sample_type"] = lab.get("sample_type", "")
        job_sample["lab_volume"] = lab.get("volume", "")
        job_sample["lab_determination"] = lab.get("determination", "")
        job_sample["lab_collection_date"] = lab.get("collection_date", "")
        job_sample["lab_analysis_date"] = lab.get("analysis_date", "")

        if lab.get("is_air"):
            interpretation = (
                "Baseline (Reference)"
                if job_sample.get("outdoor_control")
                else ("ELEVATED" if lab.get("determination") == "ELEVATED" else "Not Elevated")
            )
            for fungus, count in lab.get("fungi", {}).items():
                row = new_air_lab_row(job_sample_id)
                row["fungal_type"] = fungus
                row["spore_count"] = int(count or 0)
                row["interpretation"] = interpretation
                air_rows.append(row)
                if fungus in supported and int(count or 0) > 0 and fungus not in detected_molds:
                    detected_molds.append(fungus)
        else:
            row = new_surface_lab_row(job_sample_id)
            determination = _upper(lab.get("determination", ""))
            row["result"] = "UNUSUAL / Mold Present" if "UNUSUAL" in determination else "Normal"
            surface_rows.append(row)
            for fungus in lab.get("fungi", {}):
                if fungus in supported and fungus not in detected_molds:
                    detected_molds.append(fungus)

    if air_rows:
        job["air_lab_rows"] = air_rows
    if surface_rows or any(s.get("type") == "Swab" for s in job.get("samples", [])):
        job["surface_lab_rows"] = surface_rows
    if detected_molds:
        job["mold_types"] = detected_molds

    job["lab_metadata"] = dict(parsed.get("metadata", {}))
    return job
