"""Verify preparation against the shipped geometry and independent observations."""

from contextlib import closing
import json
import math
from pathlib import Path
import shutil
import sqlite3

import pytest

pytest.importorskip("h5py")
pytest.importorskip("shapely")

from scripts import prepare_data as preparation

INPUTS = preparation.PROJECT / "data/preparation"


@pytest.fixture
def real_database():
    path = preparation.PROJECT / "data/gaia.sqlite"
    if not path.is_file():
        pytest.skip("Generate the real-source artifact first")
    return path


def test_independent_january_and_leap_february_values_are_not_rounded(real_database):
    inputs = preparation.load_inputs(INPUTS)
    result = preparation.verify_database(real_database, inputs["references"], 1e-10)
    assert result["monthly_observations"] == result["unique_monthly_keys"] == 578
    assert len(result["references"]) == 4
    assert {(row["month"], row["hours"]) for row in result["references"]} == {("2001-01", 744), ("2004-02", 696)}
    assert all(row["absolute_error_mm"] < 1e-10 for row in result["references"])
    assert next(row["expected_mm"] for row in result["references"] if row["region_id"] == "09" and row["month"] == "2004-02") == 2.2241061738193544


def test_reference_regression_is_rejected(real_database):
    inputs = preparation.load_inputs(INPUTS)
    inputs["references"][0]["expected_mm"] += 1e-7
    with pytest.raises(ValueError, match="independent scientific reference"):
        preparation.verify_database(real_database, inputs["references"], 1e-10)


def test_missing_sources_leave_existing_outputs_unchanged(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    originals = {"gaia.sqlite": b"existing artifact sentinel", "manifest.json": b"existing manifest sentinel"}
    for name, value in originals.items():
        (output / name).write_bytes(value)
    with pytest.raises(ValueError, match="289 expected original"):
        preparation.prepare(tmp_path / "no-sources", INPUTS, output)
    assert {name: (output / name).read_bytes() for name in originals} == originals
    assert not list(output.glob(".gaia-prepare-*"))


def test_changed_weight_input_fails_before_preparation(tmp_path):
    inputs_dir = tmp_path / "inputs"
    shutil.copytree(INPUTS, inputs_dir)
    with (inputs_dir / "weights-09.csv").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="input hash mismatch"):
        preparation.load_inputs(inputs_dir)


def test_original_change_since_validation_is_rejected():
    inputs = preparation.load_inputs(INPUTS)
    item = next(row for row in inputs["originals"] if row["month"] == "2001-01")
    source = preparation.PROJECT / "data/sources" / item["filename"]
    if not source.is_file():
        pytest.skip("Original local NASA file is not present")
    item["sha256"] = "0" * 64
    _, weights = preparation.load_regions(INPUTS)
    with pytest.raises(ValueError, match="original changed"):
        preparation.build_observations({"originals": [item]}, {item["filename"]: source}, weights)


def test_real_observations_geometry_and_provenance_are_complete(real_database):
    inputs = preparation.load_inputs(INPUTS)
    features, _ = preparation.load_regions(INPUTS)
    with closing(sqlite3.connect(real_database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        metadata = connection.execute("SELECT unit, provenance_json FROM dataset_metadata").fetchone()
        assert metadata[0] == "mm"
        provenance = json.loads(metadata[1])
        assert provenance["precipitation"]["processing_version"] == "V07B"
        assert str(provenance["boundaries"]["edition"]) == "2024"
        assert len(provenance["originals"]) == 289
        assert provenance["quality_index_policy"] == "diagnostic only; not a precipitation rejection mask"
        for code, geometry, boundary in connection.execute("SELECT region_id, geometry_geojson, boundary_reference FROM regions"):
            assert json.loads(geometry) == features[code]["geometry"]
            assert json.loads(boundary)["region_identity"] == f"inegi-mg2024-agee-{code}"
        rows = connection.execute("SELECT region_id, year, month, precipitation_mm, quality_status, missing_reason, valid_area_fraction FROM monthly_observations").fetchall()
        assert len(rows) == 578
        assert len({row[:3] for row in rows}) == 578
        assert sum(row[1:3] == (2000, 12) for row in rows) == 2
        assert all(math.isfinite(row[3]) and row[3] >= 0 and row[4:] == ("observed", None, 1.) for row in rows)
        expected_hashes = {row["filename"]: row["sha256"] for row in inputs["originals"]}
        assert dict(connection.execute("SELECT DISTINCT source_filename, source_sha256 FROM monthly_observations")) == expected_hashes


def test_sqlite_rejects_duplicate_monthly_keys(real_database, tmp_path):
    copy = tmp_path / "constraint-check.sqlite"
    shutil.copyfile(real_database, copy)
    with closing(sqlite3.connect(copy)) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO monthly_observations SELECT * FROM monthly_observations LIMIT 1")


@pytest.mark.parametrize("existing", [True, False])
def test_manifest_publication_failure_restores_previous_artifacts(real_database, tmp_path, monkeypatch, existing):
    output = tmp_path / "output"
    output.mkdir()
    original_manifest = (real_database.parent / "manifest.json").read_bytes()
    original_database = real_database.read_bytes()
    if existing:
        (output / "gaia.sqlite").write_bytes(original_database)
        (output / "manifest.json").write_bytes(original_manifest)
    with closing(sqlite3.connect(real_database)) as connection:
        connection.row_factory = sqlite3.Row
        observations = [dict(row) for row in connection.execute("SELECT * FROM monthly_observations")]
    monkeypatch.setattr(preparation, "find_originals", lambda *args: {})
    monkeypatch.setattr(preparation, "build_observations", lambda *args: observations)
    real_replace = preparation.os.replace
    def failing_manifest_replace(source, destination):
        if Path(source).name == "manifest.json":
            raise PermissionError("test publication failure")
        real_replace(source, destination)
    monkeypatch.setattr(preparation.os, "replace", failing_manifest_replace)
    with pytest.raises(PermissionError, match="test publication failure"):
        preparation.prepare(tmp_path / "unused", INPUTS, output, prepared_at="2026-11-15T00:00:00+00:00")
    assert (output / "gaia.sqlite").exists() == existing
    assert (output / "manifest.json").exists() == existing
    if existing:
        assert (output / "gaia.sqlite").read_bytes() == original_database
        assert (output / "manifest.json").read_bytes() == original_manifest
    assert not list(output.glob(".gaia-prepare-*"))
