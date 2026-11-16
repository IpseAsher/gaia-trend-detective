import json
from dataclasses import asdict
import hashlib
import logging
import re
import sys
from datetime import datetime, timezone
from time import perf_counter
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from gaia.application.health import CheckHealth, DatasetUnavailable
from gaia.application.analyses import AnalysisInputError, AnalysesResponse, AnalyzeRegions, UnknownRegion
from gaia.domain.analysis import AGGREGATIONS

logger = logging.getLogger("gaia.http")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok"]
    dataset_version: str
    sqlite_read_only: Literal[True]


class AnalysesParameters(BaseModel):
    model_config = {"extra": "forbid"}

    region_id: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        min_length=1, max_length=2, description="One or two distinct dataset region IDs")
    start_year: int = Field(ge=1, le=9999)
    end_year: int = Field(ge=1, le=9999)
    aggregation: str = Field(json_schema_extra={"enum": list(AGGREGATIONS)})


def etag_matches(condition: str, etag: str) -> bool:
    if condition.strip() == "*":
        return True
    # GET If-None-Match uses weak comparison; opaque tags may contain commas.
    tags = re.findall(r'(?:W/)?"[\x21\x23-\x7e\x80-\xff]*"', condition)
    return any(tag.removeprefix("W/") == etag for tag in tags)


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request.state.error_code = code
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers={**(headers or {}), "Cache-Control": "no-store"},
    )


def create_api(check_health: CheckHealth, analyze_regions: AnalyzeRegions) -> FastAPI:
    app = FastAPI(
        title="GAIA API",
        version="0.1.0",
        redirect_slashes=False,
    )

    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            response = error_response(
                request, 500, "internal_error", "An unexpected error occurred."
            )
        route = request.scope.get("route")
        logger.info(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "info" if response.status_code < 500 else "error",
            "event": "http_request",
            "method": request.method,
            "route": getattr(route, "path", "unmatched"),
            "status": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
            "dataset_version": getattr(request.state, "dataset_version", None),
            "error_code": getattr(request.state, "error_code", None),
        }))
        return response

    @app.exception_handler(DatasetUnavailable)
    async def dataset_error(request: Request, exc: DatasetUnavailable):
        return error_response(request, 503, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        errors = {
            404: ("not_found", "The requested endpoint does not exist."),
            405: ("method_not_allowed", "This method is not allowed."),
        }
        code, message = errors.get(exc.status_code, ("http_error", "Request failed."))
        return error_response(request, exc.status_code, code, message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(request, 422, "invalid_request", "Invalid request parameters.")

    @app.exception_handler(AnalysisInputError)
    async def analysis_input_error(request: Request, exc: AnalysisInputError):
        return error_response(request, 404 if isinstance(exc, UnknownRegion) else 422, exc.code, exc.message)

    @app.get(
        "/api/v1/health",
        response_model=HealthResponse,
        responses={503: {"model": ErrorResponse, "description": "Dataset unavailable or incompatible"}},
        summary="Check availability of the verified, read-only dataset",
    )
    def health(request: Request, response: Response) -> HealthResponse:
        dataset = check_health.execute()
        request.state.dataset_version = dataset.dataset_version
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(
            status="ok", dataset_version=dataset.dataset_version, sqlite_read_only=True
        )

    @app.get(
        "/api/v1/analyses",
        response_model=AnalysesResponse,
        responses={304: {"description": "Representation unchanged; no response body"},
                   404: {"model": ErrorResponse, "description": "Unknown region"},
                   422: {"model": ErrorResponse, "description": "Invalid query or analysis period"},
                   503: {"model": ErrorResponse, "description": "Dataset unavailable or incompatible"}},
        summary="Analyze precipitation and its annual context using the fixed Sen/MK method",
    )
    def analyses(request: Request, parameters: Annotated[AnalysesParameters, Query()]):
        if any(len(request.query_params.getlist(key)) != 1 for key in ("start_year", "end_year", "aggregation")):
            raise AnalysisInputError
        result = analyze_regions.execute(tuple(parameters.region_id), parameters.start_year,
                                         parameters.end_year, parameters.aggregation)
        request.state.dataset_version = result.dataset.dataset_version
        content = json.dumps(asdict(result), sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        etag = '"' + hashlib.sha256(content).hexdigest() + '"'
        headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
        if etag_matches(",".join(request.headers.getlist("if-none-match")), etag):
            return Response(status_code=304, headers=headers)
        return Response(content, media_type="application/json", headers=headers)

    return app
