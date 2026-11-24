import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, get_settings
from app.database import check_database, get_engine
from app.errors import ApiException, ServiceUnavailable
from app.migrate import run_configured_migrations
from app.middleware import ApiHardeningMiddleware, RedisRateLimitMiddleware
from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.routes.media import router as media_router
from app.routes.profiles import discovery_router, router as profiles_router
from app.routes.location import router as location_router

logger = logging.getLogger("uvicorn.error")


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    def apply_pending_migrations() -> list[str]:
        if get_engine(app_settings).dialect.name == "mysql":
            return run_configured_migrations(app_settings)
        return []

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        application.state.database_schema_ready = None
        try:
            check_database(app_settings)
        except ServiceUnavailable as exc:
            logger.error("Database connection check failed: %s", exc.message)
        else:
            logger.info("Database connection check succeeded.")
            try:
                applied = apply_pending_migrations()
            except (OSError, RuntimeError, SQLAlchemyError):
                application.state.database_schema_ready = False
                logger.exception("Database schema migration failed.")
            else:
                application.state.database_schema_ready = True
                if applied:
                    logger.info("Applied %d database migration(s).", len(applied))
                elif get_engine(app_settings).dialect.name == "mysql":
                    logger.info("Database schema is up to date.")
        redis_client = application.state.rate_limit_redis
        if app_settings.rate_limiting_enabled:
            if redis_client is None:
                logger.error("Rate-limit storage is not configured; sensitive routes will fail closed.")
            else:
                try:
                    await redis_client.ping()
                except RedisError:
                    logger.error("Rate-limit storage is unavailable; sensitive routes will fail closed.")
                else:
                    logger.info("Rate-limit storage connection succeeded.")
        try:
            yield
        finally:
            if redis_client is not None:
                await redis_client.aclose()

    application = FastAPI(title="Flingra API", version="0.1.0", lifespan=lifespan)
    application.state.settings = app_settings
    application.state.media_storage = None
    application.state.rate_limit_redis = (
        Redis.from_url(
            app_settings.rate_limit_redis_url.get_secret_value(),
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )
        if app_settings.rate_limiting_enabled and app_settings.rate_limit_redis_url
        else None
    )
    application.add_middleware(RedisRateLimitMiddleware)
    application.add_middleware(
        ApiHardeningMiddleware,
        max_request_bytes=app_settings.max_request_bytes,
        max_upload_bytes=app_settings.media_upload_max_bytes + 65_536,
    )
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(profiles_router)
    application.include_router(discovery_router)
    application.include_router(location_router)
    application.include_router(media_router)

    if app_settings.allowed_origins:
        if "*" in app_settings.allowed_origins:
            raise ValueError("FLINGRA_ALLOWED_ORIGINS must not contain '*'.")
        application.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
            expose_headers=["X-CSRF-Token"],
        )

    @application.exception_handler(ApiException)
    async def api_exception_handler(_: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'] if part != 'body')}: {error['msg']}"
            for error in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": details or "The request is invalid.",
                }
            },
        )

    @application.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/", tags=["health"])
    def status() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        check_database(app_settings)
        if application.state.database_schema_ready is None:
            try:
                applied = apply_pending_migrations()
            except (OSError, RuntimeError, SQLAlchemyError) as exc:
                application.state.database_schema_ready = False
                logger.exception("Database schema migration failed.")
                raise ServiceUnavailable("Database schema is not ready.") from exc
            else:
                application.state.database_schema_ready = True
                if applied:
                    logger.info("Applied %d database migration(s).", len(applied))
        if not application.state.database_schema_ready:
            raise ServiceUnavailable("Database schema is not ready.")
        if app_settings.rate_limiting_enabled:
            redis_client = application.state.rate_limit_redis
            if redis_client is None:
                raise ServiceUnavailable("Rate-limit storage is not configured.")
            try:
                await redis_client.ping()
            except RedisError as exc:
                raise ServiceUnavailable("Rate-limit storage is unavailable.") from exc
        return {"status": "ready"}

    return application


app = create_app()
