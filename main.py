"""Booking Service — personalized booking pages with Cal.com embed."""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("booking")

app = FastAPI(
    title="Booking Service",
    description="Personalized booking pages with Cal.com integration",
    version="1.0.0",
)

# CORS — configure via CORS_ORIGINS env var (comma-separated), defaults to "*"
origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routes
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "booking-service"}


@app.get("/")
async def root():
    """Redirect root to booking page."""
    return RedirectResponse(url="/book", status_code=301)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.exception("Internal server error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
