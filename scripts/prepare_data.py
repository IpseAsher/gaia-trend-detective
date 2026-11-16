"""Build GAIA's fixed SQLite/manifest from local, validated originals, offline.

Install backend[prepare] first, then run: python scripts/prepare_data.py
No credentials, downloads, runtime preparation or rounded reference values.
"""

import argparse
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory

PROJECT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT))

import h5py
from shapely.geometry import shape

from scripts.gaia_data.imerg import accepted_month, inspect_original, read_region, regional_month, required_months

DATASET_ID = "gaia-regional-precipitation"
DATASET_VERSION = "gaia-imerg-v07b-inegi-mg2024-2001-2024-v1"
SCHEMA_VERSION = 1
REGION_NAMES = {"09": "Ciudad de México", "15": "Estado de México"}
DATABASE_NAME = "gaia.sqlite"
MANIFEST_NAME = "manifest.json"
OBSERVATION_COLUMNS = (
    "region_id", "year", "month", "precipitation_mm", "quality_status", "missing_reason",
    "valid_area_fraction", "valid_cells", "potential_cells", "qi_valid_area_fraction",
    "qi_area_weighted_mean", "qi_below_2_area_fraction_of_region", "qi_below_10_area_fraction_of_region",
    "source_filename", "source_sha256",
)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def load_inputs(directory):
    inputs = json.loads((directory / "inputs.json").read_text(encoding="utf-8"))
    if inputs["preparation_input_version"] != 1 or inputs["spatial_acceptance_fraction"] != .95:
        raise ValueError("Unsupported preparation inputs or spatial acceptance rule")
    source = inputs["precipitation_source"]
    if (source["product"], source["collection_version"], source["processing_version"]) != ("GPM_3IMERGM", "07", "V07B"):
        raise ValueError("The source must be the validated monthly Final V07B product")
    if set(inputs["files"]) != {"regions-inegi-mg2024.geojson", "weights-09.csv", "weights-15.csv", "schema.sql"}:
        raise ValueError("The frozen geometry, weights and schema hashes are required")
    for name, expected in inputs["files"].items():
        if Path(name).name != name or sha256(directory / name) != expected:
            raise ValueError("Preparation input hash mismatch")
    originals = inputs["originals"]
    expected_dates = {f"{year:04d}-{month:02d}" for year, month in required_months()}
    if len(originals) != 289 or {item["month"] for item in originals} != expected_dates:
        raise ValueError("Expected exactly December 2000 through December 2024")
    names = set()
    for item in originals:
        year, month = item["month"].split("-")
        expected_name = f"3B-MO.MS.MRG.3IMERG.{year}{month}01-S000000-E235959.{month}.V07B.HDF5"
        if item["filename"] != expected_name or expected_name in names or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("Invalid or duplicate original in preparation inputs")
        names.add(expected_name)
    if inputs["reference_tolerance_mm"] != 1e-10:
        raise ValueError("The agreed computational tolerance must remain 1e-10 mm")
    expected_references = {(code, month) for code in REGION_NAMES for month in ("2001-01", "2004-02")}
    if len(inputs["references"]) != 4 or {(r["region_id"], r["month"]) for r in inputs["references"]} != expected_references:
        raise ValueError("Missing independent January or leap-February reference")
    by_month = {item["month"]: item for item in originals}
    for reference in inputs["references"]:
        if (reference["source_sha256"] != by_month[reference["month"]]["sha256"]
                or not math.isfinite(reference["expected_mm"]) or reference["expected_mm"] < 0):
            raise ValueError("Independent reference provenance or value is invalid")
    return inputs


def load_regions(directory):
    collection = json.loads((directory / "regions-inegi-mg2024.geojson").read_text(encoding="utf-8"))
    if collection["type"] != "FeatureCollection" or len(collection["features"]) != 2:
        raise ValueError("Exactly two official region features are required")
    regions, weights = {}, {}
    for feature in collection["features"]:
        properties = feature["properties"]
        code = properties["CVEGEO"]
        geometry = shape(feature["geometry"])
        if (code not in REGION_NAMES or code in regions or properties["CVE_ENT"] != code
                or properties["boundary_edition"] != "2024" or geometry.is_empty or not geometry.is_valid
                or geometry.geom_type not in ("Polygon", "MultiPolygon")):
            raise ValueError("Invalid region identity, edition or geometry")
        west, south, east, north = geometry.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("Expected longitude/latitude GeoJSON geometry")
        with (directory / f"weights-{code}.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        indices = {(int(row["lon_index"]), int(row["lat_index"])) for row in rows}
        if len(indices) != len(rows) or len(rows) != {"09": 25, "15": 245}[code]:
            raise ValueError("Regional cell weights do not match the validated set")
        numeric = [{key: float(value) if key != "region_id" else value for key, value in row.items()} for row in rows]
        total = math.fsum(row["intersection_m2"] for row in numeric)
        for row in numeric:
            if (row["region_id"] != code or not math.isfinite(row["intersection_m2"]) or row["intersection_m2"] <= 0
                    or not math.isclose(row["weight"], row["intersection_m2"] / total, rel_tol=0, abs_tol=1e-12)):
                raise ValueError("Invalid polygon-cell area weight")
        if not math.isclose(math.fsum(row["weight"] for row in numeric), 1, rel_tol=0, abs_tol=1e-12):
            raise ValueError("Weights must cover the whole polygon")
        regions[code] = feature
        weights[code] = numeric
    return regions, weights


def find_originals(directory, inputs):
    expected = {item["filename"] for item in inputs["originals"]}
    available = {}
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.upper() == ".HDF5":
            if path.name not in expected or path.name in available:
                raise ValueError("Unexpected or duplicate original HDF5")
            available[path.name] = path
    if set(available) != expected:
        raise ValueError("All 289 expected original HDF5 files must be present")
    return available


def build_observations(inputs, available, weights):
    observations = []
    for index, item in enumerate(sorted(inputs["originals"], key=lambda row: row["month"]), 1):
        path = available[item["filename"]]
        inspection = inspect_original(path)
        if inspection["sha256"] != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError("An original changed since regional validation")
        year, month = map(int, item["month"].split("-"))
        with h5py.File(path, "r") as hdf:
            for code in REGION_NAMES:
                rates, qi, qi_fill = read_region(hdf, weights[code])
                result = regional_month(rates, [row["intersection_m2"] for row in weights[code]], year, month, qi=qi, qi_fill=qi_fill)
                observed = accepted_month({"status": "observed", **result}, inputs["spatial_acceptance_fraction"])
                reason = None if observed else "source_missing" if result["valid_cells"] == 0 else "insufficient_spatial_coverage"
                observations.append({"region_id": code, "year": year, "month": month,
                    "precipitation_mm": result["mean_mm_over_valid_area"] if observed else None,
                    "quality_status": "observed" if observed else "missing", "missing_reason": reason,
                    **{key: result[key] for key in OBSERVATION_COLUMNS[6:13]},
                    "source_filename": item["filename"], "source_sha256": item["sha256"]})
        if index % 25 == 0 or index == 289:
            print(f"Prepared {index}/289 originals", file=sys.stderr, flush=True)
    return observations


def verify_database(path, references, tolerance):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign_key_check failed")
        regions = {row[0] for row in connection.execute("SELECT region_id FROM regions")}
        keys = list(connection.execute("SELECT region_id, year, month FROM monthly_observations"))
        expected = {(code, year, month) for code in REGION_NAMES for year, month in required_months()}
        if regions != set(REGION_NAMES) or len(keys) != 578 or set(keys) != expected:
            raise ValueError("Expected two regions and 578 unique, complete monthly observations")
        checks = []
        for reference in references:
            year, month = map(int, reference["month"].split("-"))
            row = connection.execute(
                "SELECT precipitation_mm, source_sha256, quality_status FROM monthly_observations WHERE region_id=? AND year=? AND month=?",
                (reference["region_id"], year, month)).fetchone()
            if (row is None or row[2] != "observed" or row[1] != reference["source_sha256"] or row[0] is None
                    or not math.isclose(row[0], reference["expected_mm"], rel_tol=0, abs_tol=tolerance)):
                raise ValueError("An unrounded independent scientific reference does not match")
            checks.append({**reference, "stored_mm": row[0], "absolute_error_mm": abs(row[0] - reference["expected_mm"])})
        try:
            connection.execute("UPDATE dataset_metadata SET dataset_version=dataset_version")
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode != sqlite3.SQLITE_READONLY:
                raise
        else:
            raise ValueError("The read-only verification connection allowed a write")
    return {"integrity_check": "ok", "foreign_key_violations": 0, "regions": 2,
            "monthly_observations": 578, "unique_monthly_keys": 578,
            "read_only_write_rejected": True, "reference_tolerance_mm": tolerance, "references": checks}


def prepare(source_dir, inputs_dir, output_dir, dataset_version=DATASET_VERSION, prepared_at=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,119}", dataset_version):
        raise ValueError("Invalid dataset version identifier")
    inputs = load_inputs(inputs_dir)
    regions, weights = load_regions(inputs_dir)
    available = find_originals(source_dir, inputs)
    observations = build_observations(inputs, available, weights)
    prepared_at = prepared_at or datetime.now(timezone.utc).isoformat()
    code_paths = {"prepare_data.py": Path(__file__), "imerg.py": PROJECT / "scripts/gaia_data/imerg.py",
                  "schema.sql": inputs_dir / "schema.sql"}
    provenance = {"precipitation": inputs["precipitation_source"], "boundaries": inputs["boundary_source"],
                  "originals": inputs["originals"], "preparation_inputs_sha256": sha256(inputs_dir / "inputs.json"),
                  "input_files_sha256": inputs["files"], "preparation_code_sha256": {name: sha256(path) for name, path in code_paths.items()},
                  "area_method": inputs["area_method"], "spatial_acceptance_fraction": .95,
                  "quality_index_policy": inputs["quality_index_policy"],
                  "conversion": "mask native fill/nonfinite/invalid rates, then mm/hr * 24 * calendar days",
                  "missing_policy": "null with explicit reason; zero retained; no imputation",
                  "original_crs": "EPSG:6372", "geometry_crs": "OGC:CRS84",
                  "boundary_transformation": "Mexico ITRF2008 to WGS 84 (1); reported accuracy 1 m; no explicit coordinate epoch",
                  "shared_source_cells": 15}
    coverage = {"observation_start": "2000-12", "observation_end": "2024-12",
                "analysis_start_year": 2001, "analysis_end_year": 2024, "extra_month_for_djf": "2000-12"}
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".gaia-prepare-", dir=output_dir) as temporary:
        stage = Path(temporary)
        database = stage / DATABASE_NAME
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript((inputs_dir / "schema.sql").read_text(encoding="utf-8"))
            with connection:
                connection.execute("INSERT INTO dataset_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (1, DATASET_ID, dataset_version, SCHEMA_VERSION, prepared_at, "precipitation", "mm",
                     coverage["observation_start"], coverage["observation_end"], 2001, 2024, json_text(provenance)))
                for code, feature in sorted(regions.items()):
                    boundary = {"provider": "INEGI", "product": "Marco Geoestadístico", "edition": "2024",
                                "layer": "00ent", "region_identity": f"inegi-mg2024-agee-{code}",
                                "catalog": inputs["boundary_source"]["catalog"], **feature["properties"]}
                    connection.execute("INSERT INTO regions VALUES (?, ?, ?, ?)",
                        (code, REGION_NAMES[code], json_text(feature["geometry"]), json_text(boundary)))
                placeholders = ",".join("?" for _ in OBSERVATION_COLUMNS)
                connection.executemany(f"INSERT INTO monthly_observations ({','.join(OBSERVATION_COLUMNS)}) VALUES ({placeholders})",
                    [tuple(row[key] for key in OBSERVATION_COLUMNS) for row in observations])
        checks = verify_database(database, inputs["references"], inputs["reference_tolerance_mm"])
        manifest = {"manifest_version": 1, "dataset_id": DATASET_ID, "dataset_version": dataset_version,
                    "schema_version": SCHEMA_VERSION, "prepared_at": prepared_at, "sqlite_file": DATABASE_NAME,
                    "sqlite_sha256": sha256(database), "sqlite_bytes": database.stat().st_size,
                    "variable": "precipitation", "unit": "mm", "coverage": coverage,
                    "region_count": 2, "monthly_observation_count": 578, "checks": checks,
                    "precipitation_source": inputs["precipitation_source"], "boundary_source": inputs["boundary_source"],
                    "preparation_inputs_sha256": provenance["preparation_inputs_sha256"],
                    "preparation_code_sha256": provenance["preparation_code_sha256"]}
        (stage / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        # Connections are closed before publication. Readers fail closed during a
        # two-file replacement window; an unverified staged file is never used.
        final_database = output_dir / DATABASE_NAME
        previous_database = stage / "previous.sqlite"
        if final_database.exists():
            shutil.copyfile(final_database, previous_database)
        os.replace(database, final_database)
        try:
            os.replace(stage / MANIFEST_NAME, output_dir / MANIFEST_NAME)
        except OSError:
            if previous_database.exists():
                os.replace(previous_database, final_database)
            else:
                final_database.unlink()
            raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=PROJECT / "data/sources")
    parser.add_argument("--inputs-dir", type=Path, default=PROJECT / "data/preparation")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "data")
    parser.add_argument("--dataset-version", default=DATASET_VERSION)
    args = parser.parse_args()
    try:
        result = prepare(args.source_dir, args.inputs_dir, args.output_dir, args.dataset_version)
    except (ValueError, OSError, KeyError, sqlite3.DatabaseError) as exc:
        print(f"Preparation failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"sqlite": str(args.output_dir / DATABASE_NAME), "manifest": str(args.output_dir / MANIFEST_NAME),
                      "dataset_version": result["dataset_version"], "schema_version": result["schema_version"],
                      "sha256": result["sqlite_sha256"], "checks": result["checks"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
