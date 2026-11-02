"""INSTITRACE FastAPI application entry point.

Synthetic-data demo build: centralised complaint monitoring and cross-bureau
coordination for institution-related grievances (SIH 2026, PS SIH26264).
"""
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .routers import admin, alerts, audit, auth, cases, dashboard, health, institutions, relationships, reports

settings = get_settings()

app = FastAPI(
    title="INSTITRACE - Institution Complaint Monitoring & Cross-Bureau Coordination",
    description=(
        "Demo build for SIH 2026 problem statement SIH26264. "
        "All data is synthetic. Distinguishes same-institution coordination "
        "alerts from explainable same-incident relationship assessments."
    ),
    version=settings.app_version,
)

# Consistent error envelope --------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": str(exc.detail)}},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        {"loc": ".".join(str(p) for p in err.get("loc", [])), "msg": err.get("msg", "")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": 422, "message": "Validation failed", "details": details}},
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):  # pragma: no cover
    return JSONResponse(
        status_code=500,
        content={"error": {"code": 500, "message": "Internal server error"}},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https://.*\.e2b\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router, health.router, dashboard.router, institutions.router, cases.router,
    relationships.router, alerts.router, reports.router, audit.router, admin.router,
):
    app.include_router(router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "app": "INSTITRACE",
        "docs": "/docs",
        "api_prefix": "/api/v1",
        "demo_notice": "Synthetic data only - local demo build.",
    }
