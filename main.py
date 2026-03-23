"""Jarvis Booking Service — personalized booking pages with Cal.com embed."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("booking")

app = FastAPI(
    title="Jarvis Booking Service",
    description="Personalized booking pages with Cal.com integration",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routes
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check for Cloud Run load balancer."""
    return {"status": "healthy", "service": "jarvis-booking-service"}


@app.get("/")
async def root():
    """Root endpoint (health check fallback)."""
    return {"status": "healthy", "service": "jarvis-booking-service"}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.exception("Internal server error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
