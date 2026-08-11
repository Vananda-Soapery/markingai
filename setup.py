"""
Step 1: Test Setup endpoints - create a session, upload memo, upload class list.
"""
from __future__ import annotations
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import aiofiles

from app.config import SESSIONS_DIR
from app.store import store
from app.schemas import SessionCreateResponse, SessionStatus, MemoParseResult
from app.services.file_processing import parse_memo, parse_class_list, pdf_to_page_images_base64

router = APIRouter(prefix="/api/sessions", tags=["setup"])

ALLOWED_MEMO_TYPES = {".pdf"}
ALLOWED_CLASS_LIST_TYPES = {".csv", ".xlsx", ".xls"}


def _session_dir(session_id: str) -> Path:
    d = SESSIONS_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _save_upload(upload: UploadFile, dest: Path):
    async with aiofiles.open(dest, "wb") as f:
        content = await upload.read()
        await f.write(content)
    return len(content)


@router.post("", response_model=SessionCreateResponse)
async def create_session(
    subject: str = Form(...),
    grade: str = Form(...),
    total_marks: float = Form(...),
    test_name: str = Form("Test"),
):
    if total_marks <= 0:
        raise HTTPException(400, "Total marks must be greater than 0")

    session_id = str(uuid.uuid4())
    session = store.create(session_id)
    session.subject = subject.strip()
    session.grade = grade.strip()
    session.total_marks = total_marks
    session.test_name = test_name.strip() or "Test"
    session.status = SessionStatus.CREATED

    return SessionCreateResponse(session_id=session_id, status=session.status)


@router.post("/{session_id}/memo", response_model=MemoParseResult)
async def upload_memo(session_id: str, file: UploadFile = File(...)):
    session = _require_session(session_id)

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_MEMO_TYPES:
        raise HTTPException(400, f"Memo must be a PDF file. Got: {suffix or 'unknown type'}")

    dest = _session_dir(session_id) / f"memo{suffix}"
    size = await _save_upload(file, dest)
    if size == 0:
        raise HTTPException(400, "Uploaded memo file is empty.")

    try:
        memo_text = parse_memo(dest)
    except Exception as e:
        raise HTTPException(400, f"Could not read memo PDF: {e}")

    if not memo_text:
        # Scanned memo with no text layer: fall back to noting it needs vision
        memo_text = (
            "[This memo was a scanned document with no extractable text. "
            "The AI will be shown the memo pages as images alongside each paper.]"
        )
        try:
            session.memo_images = pdf_to_page_images_base64(dest)  # type: ignore[attr-defined]
        except Exception:
            session.memo_images = []  # type: ignore[attr-defined]
    else:
        session.memo_images = []  # type: ignore[attr-defined]

    session.memo_text = memo_text
    session.memo_filename = file.filename

    return MemoParseResult(filename=file.filename, memo_text=memo_text, char_count=len(memo_text))


@router.post("/{session_id}/class-list")
async def upload_class_list(session_id: str, file: UploadFile = File(...)):
    session = _require_session(session_id)

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_CLASS_LIST_TYPES:
        raise HTTPException(400, f"Class list must be Excel or CSV. Got: {suffix or 'unknown type'}")

    dest = _session_dir(session_id) / f"classlist{suffix}"
    size = await _save_upload(file, dest)
    if size == 0:
        raise HTTPException(400, "Uploaded class list is empty.")

    try:
        students = parse_class_list(dest)
    except Exception as e:
        raise HTTPException(400, f"Could not read class list: {e}")

    if not students:
        raise HTTPException(400, "No student names found in the class list. Check the file format.")

    session.class_list = students
    return {"students_found": len(students), "students": students}


@router.get("/{session_id}")
async def get_session(session_id: str):
    session = _require_session(session_id)
    return {
        "session_id": session.session_id,
        "status": session.status,
        "subject": session.subject,
        "grade": session.grade,
        "test_name": session.test_name,
        "total_marks": session.total_marks,
        "memo_uploaded": bool(session.memo_text),
        "memo_filename": session.memo_filename,
        "class_list_count": len(session.class_list),
        "total_papers": session.total_papers,
    }


def _require_session(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found. Please start a new test setup.")
    return session
