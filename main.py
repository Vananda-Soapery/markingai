from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

app = FastAPI()

@app.get("/{path:path}")
async def serve_frontend(path: str):
    return FileResponse(os.path.join(os.getcwd(), "index.html"))
