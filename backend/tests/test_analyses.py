from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from gaia.application.analyses import AnalysesResponse
from gaia.infrastructure.dataset import DEFAULT_DATA_DIRECTORY, SQLiteDatasetRepository
from gaia.main import create_app

REFERENCE = json.loads((Path(__file__).parent / "fixtures/trend_reference.json").read_text(encoding="utf-8"))
QUERY = {"region_id": ["09", "15"], "start_year": 2001, "end_year": 2024, "aggregation": "season:DJF"}


@pytest.fixture
def client():
    if not (DEFAULT_DATA_DIRECTORY / "gaia.sqlite").is_file():
        pytest.skip("Prepared MVP dataset is required")
    with TestClient(create_app()) as instance:
        yield instance


def assert_real_estimate(result, region_id, aggregation):
    expected = next(case for case in REFERENCE["real_cases"] if case["region_id"] == region_id and case["aggregation"] == aggregation)
    tolerance = REFERENCE["tolerances"]
    assert result["requested_years"] == result["valid_years"] == 24 and result["coverage"] == 1
    assert result["status"] == expected["expected"]["status"]
    assert [point["year"] for point in result["series"]] == expected["years"]
    assert [point["precipitation_mm"] for point in result["series"]] == pytest.approx(expected["values_mm"], abs=tolerance["aggregated_mm"], rel=0)
    assert result["slope_mm_per_decade"] == pytest.approx(expected["expected"]["slope_mm_per_decade"], abs=tolerance["slope_and_ci_mm_per_decade"], rel=0)
    assert result["confidence_interval_95_mm_per_decade"] == pytest.approx(expected["expected"]["confidence_interval_95_mm_per_decade"], abs=tolerance["slope_and_ci_mm_per_decade"], rel=0)
    assert result["p_value"] == pytest.approx(expected["expected"]["p_value"], abs=tolerance["p_and_z"], rel=0)


def test_actual_two_region_djf_and_independent_annual_context(client):
    response = client.get("/api/v1/analyses", params=QUERY)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-cache"
    TypeAdapter(AnalysesResponse).validate_json(response.content)
    result = response.json()
    assert [region["region_id"] for region in result["regions"]] == ["09", "15"]
    for region in result["regions"]:
        assert_real_estimate(region["analysis"], region["region_id"], "season:DJF")
        assert_real_estimate(region["annual_context"], region["region_id"], "annual")
        assert region["boundary_provenance"]["region_identity"] == f"inegi-mg2024-agee-{region['region_id']}"
    assert result["method"]["version"] == "gaia-sen-mk-v1"
    assert result["method"]["slope_unit"] == "mm/decade"
    assert len(result["method"]["limitations"]) == 3
    assert result["provenance"]["precipitation"]["processing_version"] == "V07B"
    assert str(result["provenance"]["boundaries"]["edition"]) == "2024"
    assert result["dataset"]["sqlite_sha256"] == REFERENCE["dataset_sha256"]


@pytest.mark.parametrize("aggregation", ["annual", "month:01", "month:12", "season:MAM", "season:JJA", "season:SON"])
def test_all_aggregation_families_and_single_region(client, aggregation):
    response = client.get("/api/v1/analyses", params={**QUERY, "region_id": "09", "aggregation": aggregation})
    assert response.status_code == 200
    result = response.json()
    assert len(result["regions"]) == 1 and result["regions"][0]["region_id"] == "09"
    assert result["regions"][0]["analysis"]["valid_years"] == 24
    if aggregation == "annual":
        assert result["regions"][0]["analysis"] == result["regions"][0]["annual_context"]


@pytest.mark.parametrize("updates,status,code", [
    ({"region_id": ["09", "09"]}, 422, "invalid_regions"),
    ({"region_id": ["09", "15", "unknown"]}, 422, "invalid_request"),
    ({"region_id": "unknown"}, 404, "unknown_region"),
    ({"region_id": "09';DROP TABLE regions;--"}, 404, "unknown_region"),
    ({"region_id": ""}, 422, "invalid_request"),
    ({"aggregation": "month:1"}, 422, "invalid_aggregation"),
    ({"aggregation": "month:13"}, 422, "invalid_aggregation"),
    ({"aggregation": "season:djf"}, 422, "invalid_aggregation"),
    ({"start_year": 2000}, 422, "invalid_period"),
    ({"end_year": 2025}, 422, "invalid_period"),
    ({"start_year": 2024, "end_year": 2001}, 422, "invalid_period"),
    ({"start_year": "not-a-year"}, 422, "invalid_request"),
    ({"start_year": 0}, 422, "invalid_request"),
    ({"unexpected": "value"}, 422, "invalid_request"),
])
def test_query_validation_is_json_and_not_cacheable(client, updates, status, code):
    response = client.get("/api/v1/analyses", params={**QUERY, **updates}, headers={"If-None-Match": "*"})
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == code
    assert "ETag" not in response.headers


def test_missing_and_duplicate_scalar_parameters_are_rejected(client):
    assert client.get("/api/v1/analyses").status_code == 422
    params = [("region_id", "09"), ("start_year", "2001"), ("start_year", "2002"),
              ("end_year", "2024"), ("aggregation", "annual")]
    response = client.get("/api/v1/analyses", params=params)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"


def test_short_valid_period_is_a_200_insufficient_result(client):
    response = client.get("/api/v1/analyses", params={**QUERY, "start_year": 2020})
    assert response.status_code == 200
    for region in response.json()["regions"]:
        for result in (region["analysis"], region["annual_context"]):
            assert result["status"] == "insufficient_data"
            assert result["valid_years"] == result["requested_years"] == 5 and result["coverage"] == 1
            assert result["slope_mm_per_decade"] is result["p_value"] is result["confidence_interval_95_mm_per_decade"] is None
            assert result["insufficient_reasons"] == ["fewer_than_20_valid_years"]
    assert response.headers["cache-control"] == "private, no-cache"


def test_selected_aggregation_region_and_annual_sufficiency_are_independent():
    base = SQLiteDatasetRepository(DEFAULT_DATA_DIRECTORY / "gaia.sqlite", DEFAULT_DATA_DIRECTORY / "manifest.json")
    snapshot = base.read_analysis_data(("09", "15"), 2001, 2024)
    regions = []
    for region in snapshot.regions:
        observations = tuple(replace(row, precipitation_mm=None, quality_status="missing", missing_reason="test_gap")
            if region.region_id == "09" and row.month == 7 and 2001 <= row.year <= 2005 else row for row in region.observations)
        regions.append(replace(region, observations=observations))
    class MemoryRepository:
        def read_analysis_data(self, *args):
            return replace(snapshot, regions=tuple(regions))
    with TestClient(create_app(MemoryRepository())) as client:
        response = client.get("/api/v1/analyses", params={**QUERY, "aggregation": "month:01"})
    assert response.status_code == 200
    cdmx, mexico = response.json()["regions"]
    assert cdmx["analysis"]["valid_years"] == 24 and cdmx["analysis"]["status"] != "insufficient_data"
    assert cdmx["annual_context"]["valid_years"] == 19 and cdmx["annual_context"]["status"] == "insufficient_data"
    assert len(cdmx["annual_context"]["series"]) == 24
    assert mexico["analysis"]["valid_years"] == mexico["annual_context"]["valid_years"] == 24


@pytest.mark.parametrize("condition", ["strong", "weak", "list", "wildcard", "quoted_comma"])
def test_etag_matches_return_bodyless_304(client, condition):
    initial = client.get("/api/v1/analyses", params=QUERY)
    tag = initial.headers["etag"]
    assert tag == '"' + hashlib.sha256(initial.content).hexdigest() + '"'
    headers = {"strong": tag, "weak": "W/" + tag, "list": '"unrelated", W/' + tag,
               "wildcard": "*", "quoted_comma": '"unrelated,comma", ' + tag}
    response = client.get("/api/v1/analyses", params=QUERY, headers={"If-None-Match": headers[condition]})
    assert response.status_code == 304 and response.content == b""
    assert response.headers["etag"] == tag and response.headers["cache-control"] == "private, no-cache"
    assert "content-type" not in response.headers


def test_etag_is_stable_for_canonical_region_order_and_changes_with_query(client):
    first = client.get("/api/v1/analyses", params=QUERY)
    reversed_regions = client.get("/api/v1/analyses", params={**QUERY, "region_id": ["15", "09"]})
    assert first.content == reversed_regions.content and first.headers["etag"] == reversed_regions.headers["etag"]
    changed = client.get("/api/v1/analyses", params={**QUERY, "start_year": 2002}, headers={"If-None-Match": first.headers["etag"]})
    assert changed.status_code == 200 and changed.headers["etag"] != first.headers["etag"]


def test_unavailable_or_changed_dataset_does_not_return_cached_304(dataset_copy):
    database, manifest = dataset_copy
    with TestClient(create_app(SQLiteDatasetRepository(database, manifest))) as client:
        first = client.get("/api/v1/analyses", params=QUERY)
        assert first.status_code == 200
        with database.open("ab") as stream:
            stream.write(b"changed")
        response = client.get("/api/v1/analyses", params=QUERY, headers={"If-None-Match": first.headers["etag"]})
    assert response.status_code == 503 and response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "dataset_incompatible"


def test_new_verified_dataset_identity_changes_the_etag(dataset_copy):
    database, manifest = dataset_copy
    with TestClient(create_app(SQLiteDatasetRepository(database, manifest))) as client:
        first = client.get("/api/v1/analyses", params=QUERY)
        contents = json.loads(manifest.read_text(encoding="utf-8"))
        contents["dataset_version"] += "-verification"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("UPDATE dataset_metadata SET dataset_version=?", (contents["dataset_version"],))
            connection.commit()
        contents["sqlite_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
        contents["sqlite_bytes"] = database.stat().st_size
        manifest.write_text(json.dumps(contents), encoding="utf-8")
        second = client.get("/api/v1/analyses", params=QUERY, headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 200 and second.headers["etag"] != first.headers["etag"]
    assert second.json()["dataset"]["dataset_version"] == contents["dataset_version"]


def test_openapi_covers_query_and_response_contract(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/analyses"]["get"]
    assert {p["name"] for p in operation["parameters"]} == {"region_id", "start_year", "end_year", "aggregation"}
    assert all(p["in"] == "query" and p["required"] for p in operation["parameters"])
    assert {"200", "304", "404", "422", "503"} <= set(operation["responses"])
    assert "content" not in operation["responses"]["304"]
    assert operation["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
