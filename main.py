from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("markingai")

app = FastAPI(
    title="MarkingAI API",
    description="AI-powered test paper marking for South African teachers",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/", StaticFiles(directory=".", html=True), name="static")

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "MarkingAI API is running. See /docs for API documentation."}
