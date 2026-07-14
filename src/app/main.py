from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from app.archive.api import router as archive_documents_router
from app.archive.error_handlers import register_archive_exception_handlers
from app.archive.metrics import record_archive_supportability, validate_archive_metric_contracts
from app.archive.runtime import runtime_posture
from app.archive.settings import ArchiveRuntimeSettings
from app.archive.service_profile import archive_supportability, service_posture
from app.build_metadata import BuildMetadata, build_metadata
from app.contracts.errors import error_response
from app.middleware.correlation import CorrelationIdMiddleware, configure_request_logging
from starlette.exceptions import HTTPException as StarletteHTTPException

SERVICE_NAME = "lotus-archive"
SERVICE_VERSION = "0.1.0"
ROUNDING_POLICY_VERSION = "v1"
HTTP_422_UNPROCESSABLE_CONTENT = 422

configure_request_logging()

app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION)
app.state.archive_runtime_settings = ArchiveRuntimeSettings()
app.add_middleware(CorrelationIdMiddleware, service_name=SERVICE_NAME)
validate_archive_metric_contracts()
Instrumentator().instrument(app).expose(app)
app.include_router(archive_documents_router)


def _correlation_id(request: Request) -> str:
    return str(
        getattr(request.state, "correlation_id", request.headers.get("X-Correlation-Id", ""))
    )


register_archive_exception_handlers(app, service_name=SERVICE_NAME, correlation_id=_correlation_id)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == status.HTTP_404_NOT_FOUND else "internal_error"
    return error_response(
        code=code,
        http_status=exc.status_code,
        correlation_id=_correlation_id(request),
        service=SERVICE_NAME,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    _exc: RequestValidationError,
) -> JSONResponse:
    return error_response(
        code="validation_failed",
        http_status=HTTP_422_UNPROCESSABLE_CONTENT,
        correlation_id=_correlation_id(request),
        service=SERVICE_NAME,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    return error_response(
        code="internal_error",
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        correlation_id=_correlation_id(request),
        service=SERVICE_NAME,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "live"}


@app.get("/health/ready")
async def health_ready(response: Response) -> dict[str, str]:
    if bool(getattr(app.state, "is_draining", False)):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "draining"}
    posture = runtime_posture(app.state.archive_runtime_settings)
    if posture.state == "unavailable":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": posture.state, "reason": posture.reason}


@app.get("/metadata")
async def metadata() -> dict[str, object]:
    runtime = runtime_posture(app.state.archive_runtime_settings)
    supportability = archive_supportability(
        is_draining=bool(getattr(app.state, "is_draining", False))
    )
    record_archive_supportability(
        state=str(supportability["state"]),
        reason=str(supportability["reason"]),
        freshness_bucket=str(supportability["freshnessBucket"]),
    )
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "roundingPolicyVersion": ROUNDING_POLICY_VERSION,
        "archivePosture": service_posture(),
        "runtimePosture": runtime.__dict__,
        "supportability": supportability,
        "build": build_metadata().model_dump(),
    }


@app.get(
    "/version",
    response_model=BuildMetadata,
    summary="Get runtime build metadata",
    description=(
        "Returns source-safe build and image provenance metadata for support diagnostics. "
        "Published CI images expose the immutable image digest through deployment-provided "
        "runtime metadata; local builds report a not-published posture."
    ),
    tags=["operations"],
)
async def version() -> BuildMetadata:
    return build_metadata()
