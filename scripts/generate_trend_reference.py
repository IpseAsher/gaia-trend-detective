"""Freeze independent inference references using optional backend[reference].

This tool never imports GAIA. It reads SQLite in mode=ro and uses independent
SQL aggregation, SciPy's Sen estimator/CI and pyMannKendall's original test.
Existing expected files are never overwritten. Use --output for a new review.
"""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sqlite3

import pymannkendall
from scipy.stats import theilslopes

ROOT = Path(__file__).resolve().parents[1]


def reference(case_id, years, values, **metadata):
    sen = theilslopes(values, years, alpha=.95)
    mk = pymannkendall.original_test(values, alpha=.05)
    return {"case_id": case_id, "years": years, "values_mm": values, **metadata, "expected": {
        "slope_mm_per_decade": float(sen.slope * 10),
        "confidence_interval_95_mm_per_decade": [float(sen.low_slope * 10), float(sen.high_slope * 10)],
        "p_value": float(mk.p), "mann_kendall_s": int(mk.s), "variance_s": float(mk.var_s),
        "z_score": float(mk.z), "status": "significant" if mk.p < .05 else "inconclusive"}}


def generate(database):
    assert version("scipy") == "1.17.1" and version("pymannkendall") == "1.4.3"
    years = list(range(2001, 2025))
    gaps = [year for year in years if year not in (2003, 2008, 2014, 2019)]
    synthetic = [
        reference("constant_zero", years, [0.] * 24),
        reference("increasing_linear", years, [float(3 * (year - 2001) + 7) for year in years]),
        reference("decreasing_linear", years, [float(100 - 2 * (year - 2001)) for year in years]),
        reference("ties_with_trend", years, [2, 2, 3, 1, 4, 4, 3, 6, 4, 7, 7, 5, 8, 6, 9, 9, 7, 10, 8, 11, 11, 10, 12, 9]),
        reference("inconclusive_ties", years, [3, 1, 4, 2] * 5 + [4, 2, 3, 1]),
        reference("irregular_year_gaps", gaps, [17, 15, 18, 20, 16, 21, 18, 24, 22, 23, 21, 27, 25, 26, 24, 28, 26, 31, 29, 30]),
    ]
    real = []
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        for code in ("09", "15"):
            for aggregation in ("season:DJF", "annual"):
                if aggregation == "annual":
                    rows = connection.execute("""
                        SELECT year, SUM(precipitation_mm) FROM monthly_observations
                        WHERE region_id=? AND year BETWEEN 2001 AND 2024
                        GROUP BY year HAVING COUNT(*)=12 AND COUNT(precipitation_mm)=12
                        AND MIN(quality_status='observed')=1 ORDER BY year
                    """, (code,)).fetchall()
                else:
                    rows = connection.execute("""
                        WITH winter AS (
                            SELECT CASE WHEN month=12 THEN year+1 ELSE year END AS label,
                                   precipitation_mm, quality_status FROM monthly_observations
                            WHERE region_id=? AND month IN (12,1,2)
                        ) SELECT label, SUM(precipitation_mm) FROM winter WHERE label BETWEEN 2001 AND 2024
                        GROUP BY label HAVING COUNT(*)=3 AND COUNT(precipitation_mm)=3
                        AND MIN(quality_status='observed')=1 ORDER BY label
                    """, (code,)).fetchall()
                assert len(rows) == 24
                real.append(reference(f"{code}:{aggregation}", [row[0] for row in rows], [row[1] for row in rows],
                                      region_id=code, aggregation=aggregation, requested_years=24))
    return {"reference_version": 1, "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "software": {name: version(name) for name in ("scipy", "pymannkendall", "numpy")},
        "independence": "No GAIA imports; direct read-only SQL complete-month SUM; SciPy Sen slope/CI with actual years; pyMannKendall original MK with ties/continuity correction. pyMannKendall's position-based slope is not used.",
        "dataset_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "domain_files_at_freeze": [path.name for path in (ROOT / "backend/src/gaia/domain").glob("*.py")],
        "tolerances": {"relative": 0., "slope_and_ci_mm_per_decade": 1e-9, "p_and_z": 1e-12,
                       "variance_s": 1e-9, "aggregated_mm": 1e-9},
        "method_sources": ["https://github.com/scipy/scipy/blob/v1.17.1/scipy/stats/_stats_mstats_common.py",
                           "https://github.com/mmhs013/pyMannKendall/blob/v1.4.3/pymannkendall/pymannkendall.py"],
        "synthetic_cases": synthetic, "real_cases": real}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/gaia.sqlite")
    parser.add_argument("--output", type=Path, default=ROOT / "backend/tests/fixtures/trend_reference.json")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Expected values are frozen; specify a new --output path for review")
    report = generate(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "real_expected": [{"case_id": case["case_id"], **case["expected"]} for case in report["real_cases"]]}, indent=2))


if __name__ == "__main__":
    main()
