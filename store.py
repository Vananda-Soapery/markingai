"""
Simple in-memory session store.

For a real production deployment you'd swap this for Redis / a database,
but for a single-teacher-at-a-time marking workflow, an in-process store
keeps the app dependency-free and easy to self-host on a school server.
"""
from __future__ import annotations
import threading
from typing import Optional
from app.schemas import SessionStatus, PaperStatus, GradedPaper


class TestSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.status = SessionStatus.CREATED
        self.subject: str = ""
        self.grade: str = ""
        self.test_name: str = "Test"
        self.total_marks: float = 0.0
        self.memo_text: str = ""
        self.memo_filename: str = ""
        self.class_list: list[dict] = []  # [{name, student_number}]
        self.papers: dict[str, GradedPaper] = {}  # paper_id -> GradedPaper
        self.paper_order: list[str] = []
        self.paper_filepaths: dict[str, str] = {}  # paper_id -> path on disk
        self.error_message: Optional[str] = None

    @property
    def total_papers(self) -> int:
        return len(self.paper_order)

    @property
    def processed_papers(self) -> int:
        return sum(
            1 for pid in self.paper_order
            if self.papers[pid].status in (PaperStatus.DONE, PaperStatus.FAILED, PaperStatus.NEEDS_REVIEW)
        )


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, TestSession] = {}
        self._lock = threading.Lock()

    def create(self, session_id: str) -> TestSession:
        with self._lock:
            session = TestSession(session_id)
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> Optional[TestSession]:
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> TestSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")
        return session


store = SessionStore()
