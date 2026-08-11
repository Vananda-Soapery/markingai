"""
Step 3: AI Processing endpoints. Kicks off async grading of all uploaded
papers and exposes a progress endpoint the frontend can poll.
"""
from __future__ import annotations
import asyncio
import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from openai import AsyncOpenAI

from app.config import settings
from app.store import store, TestSession
from app.schemas import SessionStatus, PaperStatus, ProcessingProgress
from app.services.file_processing import file_to_base64_images
from app.services.grading import grade_single_paper

router = APIRouter(prefix="/api/sessions", tags=["processing"])
logger = logging.getLogger("markingai.processing")


async def _process_session(session: TestSession):
    if not settings.openai_configured:
        session.status = SessionStatus.FAILED
        session.error_message = (
            "OpenAI API key is not configured on the server. "
            "Ask your administrator to set OPENAI_API_KEY in the backend .env file."
        )
        return

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    semaphore = asyncio.Semaphore(max(1, settings.max_concurrent_grading))
    session.status = SessionStatus.PROCESSING

    async def grade_one(paper_id: str):
        async with semaphore:
            paper = session.papers[paper_id]
            paper.status = PaperStatus.PROCESSING
            filepath = session.paper_filepaths[paper_id]
            try:
                page_images = file_to_base64_images(filepath)
                if not page_images:
                    raise ValueError("Could not extract any readable pages from this file.")

                result = await grade_single_paper(
                    client=client,
                    paper_id=paper_id,
                    filename=paper.filename,
                    page_images_b64=page_images,
                    memo_text=session.memo_text,
                    total_marks=session.total_marks,
                    subject=session.subject,
                    grade=session.grade,
                    class_list=session.class_list,
                )
                session.papers[paper_id] = result
            except Exception as e:
                logger.exception(f"Failed processing paper {paper.filename}")
                paper.status = PaperStatus.FAILED
                paper.error_message = f"Could not process file: {str(e)[:200]}"

    tasks = [grade_one(pid) for pid in session.paper_order]
    await asyncio.gather(*tasks)

    session.status = SessionStatus.COMPLETED


@router.post("/{session_id}/process")
async def start_processing(session_id: str, background_tasks: BackgroundTasks):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    if session.total_papers == 0:
        raise HTTPException(400, "No papers uploaded yet.")
    if session.status == SessionStatus.PROCESSING:
        raise HTTPException(409, "Processing already in progress for this session.")

    if not settings.openai_configured:
        raise HTTPException(
            500,
            "OpenAI API key is not configured on the server. "
            "Set OPENAI_API_KEY in backend/.env and restart the server.",
        )

    background_tasks.add_task(_process_session, session)
    return {"status": "started", "total_papers": session.total_papers}


@router.get("/{session_id}/progress", response_model=ProcessingProgress)
async def get_progress(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")

    current_filename = None
    for pid in session.paper_order:
        if session.papers[pid].status == PaperStatus.PROCESSING:
            current_filename = session.papers[pid].filename
            break

    return ProcessingProgress(
        session_id=session.session_id,
        status=session.status,
        total_papers=session.total_papers,
        processed_papers=session.processed_papers,
        current_filename=current_filename,
        papers=[session.papers[pid] for pid in session.paper_order],
    )


@router.post("/{session_id}/papers/{paper_id}/retry")
async def retry_paper(session_id: str, paper_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    if paper_id not in session.papers:
        raise HTTPException(404, "Paper not found.")
    if not settings.openai_configured:
        raise HTTPException(500, "OpenAI API key not configured on server.")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    paper = session.papers[paper_id]
    paper.status = PaperStatus.PROCESSING
    filepath = session.paper_filepaths[paper_id]

    try:
        page_images = file_to_base64_images(filepath)
        result = await grade_single_paper(
            client=client,
            paper_id=paper_id,
            filename=paper.filename,
            page_images_b64=page_images,
            memo_text=session.memo_text,
            total_marks=session.total_marks,
            subject=session.subject,
            grade=session.grade,
            class_list=session.class_list,
        )
        session.papers[paper_id] = result
        return result
    except Exception as e:
        paper.status = PaperStatus.FAILED
        paper.error_message = f"Retry failed: {str(e)[:200]}"
        raise HTTPException(500, paper.error_message)
