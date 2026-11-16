"""Integration checks against copies of the prepared, real-source MVP dataset."""

from contextlib import closing
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from gaia.infrastructure.dataset import DEFAULT_DATA_DIRECTORY, SQLiteDatasetRepository
from gaia.main import create_app


def read_manifest(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def resign(database, path):
    value = read_manifest(path)
    value["sqlite_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
    value["sqlite_bytes"] = database.stat().st_size
    write_manifest(path, value)


def health(database, manifest):
    with TestClient(create_app(SQLiteDatasetRepository(database, manifest))) as client:
        return client.get("/api/v1/health")


def test_real_dataset_health_matches_manifest(dataset_copy):
    database, manifest = dataset_copy
    response = health(database, manifest)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"status": "ok", "dataset_version": read_manifest(manifest)["dataset_version"], "sqlite_read_only": True}


def test_mode_ro_blocks_writes_even_without_query_only(dataset_copy):
    database, manifest = dataset_copy
    original_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    repository = SQLiteDatasetRepository(database, manifest)
    with repository.open_read_only() as (connection, _):
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        for query_only in ("ON", "OFF"):
            connection.execute(f"PRAGMA query_only={query_only}")
            with pytest.raises(sqlite3.OperationalError) as caught:
                connection.execute("UPDATE dataset_metadata SET dataset_version=dataset_version")
            assert caught.value.sqlite_errorcode == sqlite3.SQLITE_READONLY
    assert hashlib.sha256(database.read_bytes()).hexdigest() == original_hash


@pytest.mark.parametrize("missing", ["database", "manifest"])
def test_missing_artifacts_are_never_created(dataset_copy, missing):
    database, manifest = dataset_copy
    target = database if missing == "database" else manifest
    target.unlink()
    response = health(database, manifest)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dataset_unavailable"
    assert not target.exists()


def test_changed_bytes_are_detected_after_a_successful_check(dataset_copy):
    database, manifest = dataset_copy
    repository = SQLiteDatasetRepository(database, manifest)
    assert repository.verify().dataset_version == read_manifest(manifest)["dataset_version"]
    with database.open("ab") as stream:
        stream.write(b"changed")
    response = health(database, manifest)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dataset_incompatible"


@pytest.mark.parametrize("sql", [
    "UPDATE dataset_metadata SET dataset_version='different-version'",
    "UPDATE dataset_metadata SET observation_start='2001-01'",
    "PRAGMA user_version=2",
    "ALTER TABLE regions RENAME COLUMN geometry_geojson TO incompatible_geometry",
    "DELETE FROM monthly_observations WHERE region_id='09' AND year=2000 AND month=12",
    "UPDATE monthly_observations SET region_id='unknown' WHERE region_id='09'",
])
def test_incompatible_content_is_rejected_even_with_matching_hash(dataset_copy, sql):
    database, manifest = dataset_copy
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(sql)
        connection.commit()
    resign(database, manifest)
    response = health(database, manifest)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "dataset_incompatible"


@pytest.mark.parametrize("value", [None, [], {}, {"manifest_version": 1}, "invalid manifest"])
def test_invalid_manifest_is_a_controlled_503(dataset_copy, value):
    database, manifest = dataset_copy
    write_manifest(manifest, value)
    response = health(database, manifest)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dataset_incompatible"


@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("schema_version", True), ("sqlite_sha256", "0" * 64),
    ("sqlite_file", "../other.sqlite"), ("region_count", 3), ("monthly_observation_count", 577),
])
def test_manifest_mismatches_fail_closed(dataset_copy, field, value):
    database, manifest = dataset_copy
    contents = read_manifest(manifest)
    contents[field] = value
    write_manifest(manifest, contents)
    response = health(database, manifest)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dataset_incompatible"


def test_default_composition_reads_the_included_manifest():
    if not (DEFAULT_DATA_DIRECTORY / "gaia.sqlite").is_file():
        pytest.skip("Prepared real-source artifact is not present")
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["dataset_version"] == read_manifest(DEFAULT_DATA_DIRECTORY / "manifest.json")["dataset_version"]
        assert client.get("/api/v1/analyses").status_code == 422
