"""
Step 2: Batch paper upload endpoints.
"""
from __future__ import annotations
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
import aiofiles

from app.config import SESSIONS_DIR
from app.store import store
from app.schemas import SessionStatus, PaperStatus, GradedPaper

router = APIRouter(prefix="/api/sessions", tags=["papers"])

ALLOWED_PAPER_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MAX_FILE_SIZE_MB = 25


@router.post("/{session_id}/papers")
async def upload_papers(session_id: str, files: list[UploadFile] = File(...)):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    if not session.memo_text:
        raise HTTPException(400, "Please upload a memo before uploading papers.")

    papers_dir = SESSIONS_DIR / session_id / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    accepted = []
    rejected = []

    for upload in files:
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in ALLOWED_PAPER_TYPES:
            rejected.append({"filename": upload.filename, "reason": f"Unsupported file type: {suffix}"})
            continue

        content = await upload.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            rejected.append({"filename": upload.filename, "reason": f"File too large ({size_mb:.1f}MB, max {MAX_FILE_SIZE_MB}MB)"})
            continue
        if len(content) == 0:
            rejected.append({"filename": upload.filename, "reason": "File is empty"})
            continue

        paper_id = str(uuid.uuid4())
        dest = papers_dir / f"{paper_id}{suffix}"
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)

        session.papers[paper_id] = GradedPaper(
            paper_id=paper_id,
            filename=upload.filename,
            status=PaperStatus.PENDING,
        )
        session.paper_order.append(paper_id)
        session.paper_filepaths[paper_id] = str(dest)
        accepted.append({"paper_id": paper_id, "filename": upload.filename})

    if accepted:
        session.status = SessionStatus.PAPERS_UPLOADED

    return {
        "accepted": accepted,
        "rejected": rejected,
        "total_papers": session.total_papers,
    }


@router.delete("/{session_id}/papers/{paper_id}")
async def remove_paper(session_id: str, paper_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    if paper_id not in session.papers:
        raise HTTPException(404, "Paper not found.")

    session.papers.pop(paper_id, None)
    session.paper_order = [p for p in session.paper_order if p != paper_id]
    filepath = session.paper_filepaths.pop(paper_id, None)
    if filepath:
        try:
            Path(filepath).unlink(missing_ok=True)
        except Exception:
            pass

    return {"removed": paper_id, "total_papers": session.total_papers}


@router.get("/{session_id}/papers")
async def list_papers(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    return {
        "total_papers": session.total_papers,
        "papers": [session.papers[pid] for pid in session.paper_order],
    }
