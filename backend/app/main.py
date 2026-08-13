"""FastAPI application factory and entry point.

Feature routers, middleware, and startup/shutdown hooks are added by later
tasks; this module only establishes the minimal executable entry point for
the scaffolded project.
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(title="Twitter Smart Clone API", version="0.1.0")

    @app.get("/api/v1/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Liveness/readiness probe used by orchestration and monitoring."""
        return {"status": "ok"}

    return app


app = create_app()
