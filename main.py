"""
MarkingAI backend - FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
"""
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import setup, papers, processing, results

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("markingai")

app = FastAPI(
    title="MarkingAI API",
    description="AI-powered test paper marking for South African teachers",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(setup.router)
app.include_router(papers.router)
app.include_router(processing.router)
app.include_router(results.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again."},
    )


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "openai_configured": settings.openai_configured,
        "model": settings.openai_model,
    }


@app.get("/")
async def root():
    return {"message": "MarkingAI API is running. See /docs for API documentation."}
