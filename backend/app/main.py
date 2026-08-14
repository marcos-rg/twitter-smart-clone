"""FastAPI application factory and entry point.

Wires the shared platform every feature router depends on: typed settings,
async resource lifecycle (PostgreSQL/Redis/MinIO), API versioning/OpenAPI
metadata, request-ID propagation, structured JSON logging, the standard
error envelope, security headers, and environment-driven CORS. Product
routers are added by later feature tasks.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.resources import create_lifespan
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.users import router as users_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application instance."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        redoc_url=None,
        lifespan=create_lifespan(settings),
    )

    # Starlette wraps outer-to-inner in *reverse* add-order (the last one
    # added is outermost, closest to the client). `RequestContextMiddleware`
    # converts any exception that escapes the router into the standard error
    # envelope itself (see its docstring for why), so it must be innermost of
    # these three, with CORS and security headers wrapping around it —
    # otherwise CORS/security headers would be missing from 500 responses.
    app.add_middleware(RequestContextMiddleware, header_name=settings.request_id_header)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[settings.request_id_header],
    )
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.is_production)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)

    return app


app = create_app()
