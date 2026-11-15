import json
import logging
import sys
from datetime import datetime, timezone
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from gaia.application.health import CheckHealth, DatasetUnavailable

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


def create_api(check_health: CheckHealth) -> FastAPI:
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

    return app
