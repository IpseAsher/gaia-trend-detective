import json
import io
import logging

import pytest
from fastapi.testclient import TestClient

from gaia.application.health import DatasetIncompatible
from gaia.main import create_app
from gaia.presentation.api import logger


def test_unprovisioned_dataset_is_unavailable():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "error": {
            "code": "dataset_unavailable",
            "message": "The precipitation dataset is not available yet.",
        }
    }


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [
        ("GET", "/api/v1/unknown", 404, "not_found"),
        ("GET", "/api/v1/health/", 404, "not_found"),
        ("POST", "/api/v1/health", 405, "method_not_allowed"),
    ],
)
def test_common_http_errors(method, path, status, code):
    with TestClient(create_app()) as client:
        response = client.request(method, path)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    if status == 405:
        assert response.headers["allow"] == "GET"


def test_incompatible_dataset_never_reports_healthy():
    class IncompatibleRepository:
        def verify(self):
            raise DatasetIncompatible

    with TestClient(create_app(IncompatibleRepository())) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dataset_incompatible"


def test_unexpected_failure_is_json_without_internal_details():
    class BrokenRepository:
        def verify(self):
            raise RuntimeError("private filesystem detail")

    with TestClient(create_app(BrokenRepository())) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "private filesystem detail" not in response.text


def test_request_log_excludes_query_values_and_headers():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    logger.addHandler(handler)
    try:
        with TestClient(create_app()) as client:
            client.get("/api/v1/health?private=do-not-log", headers={"X-Test": "secret-value"})
    finally:
        logger.removeHandler(handler)
    event = json.loads(output.getvalue())
    assert event["route"] == "/api/v1/health"
    assert event["error_code"] == "dataset_unavailable"
    assert event["status"] == 503
    assert "do-not-log" not in output.getvalue()
    assert "secret-value" not in output.getvalue()


def test_openapi_describes_success_and_unavailable_responses():
    schema = create_app().openapi()
    responses = schema["paths"]["/api/v1/health"]["get"]["responses"]
    assert "200" in responses
    assert "503" in responses
    assert "application/json" in responses["503"]["content"]
