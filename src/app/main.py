"""FastAPI application for Fortaleza Purchase Agent."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..core.config import get_settings
from ..core.logging import setup_logging, get_logger
from .webhook import router as webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    import os
    setup_logging()
    logger = get_logger(__name__)
    settings = get_settings()

    # Set Google API key once at startup for google.genai client
    # This avoids runtime os.environ mutation and ensures it's set before any agent creation
    if settings.google_api_key:
        os.environ['GOOGLE_API_KEY'] = settings.google_api_key

    logger.info(
        "Fortaleza Purchase Agent starting",
        mode=settings.mode.value,
        headless=settings.headless,
        product_name=settings.product_name
    )

    yield

    # Shutdown
    logger.info("Fortaleza Purchase Agent shutting down")


app = FastAPI(
    title="Fortaleza Purchase Agent",
    description="AI agent that automatically purchases Fortaleza tequila when notified",
    version="1.0.0",
    lifespan=lifespan,
)

# Include webhook router
app.include_router(webhook_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    settings = get_settings()
    return JSONResponse({
        "service": "Fortaleza Purchase Agent",
        "status": "running",
        "mode": settings.mode.value,
        "version": "1.0.0"
    })


@app.get("/health")
async def health():
    """Kubernetes-style health check."""
    return JSONResponse({"status": "healthy"})


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "src.app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=not settings.is_cloud_environment(),
    )
