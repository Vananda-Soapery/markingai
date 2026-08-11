"""
Pydantic models used across the MarkingAI API.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    CREATED = "created"
    PAPERS_UPLOADED = "papers_uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PaperStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class TestSetupRequest(BaseModel):
    subject: str = Field(..., min_length=1)
    grade: str = Field(..., min_length=1)
    total_marks: float = Field(..., gt=0)
    test_name: Optional[str] = "Test"


class SessionCreateResponse(BaseModel):
    session_id: str
    status: SessionStatus


class ClassListStudent(BaseModel):
    name: str
    student_number: Optional[str] = None


class MemoParseResult(BaseModel):
    filename: str
    memo_text: str
    char_count: int


class QuestionBreakdown(BaseModel):
    question: str
    marks_awarded: float
    marks_possible: Optional[float] = None
    comment: Optional[str] = None


class GradedPaper(BaseModel):
    paper_id: str
    filename: str
    status: PaperStatus
    student_name: Optional[str] = None
    matched_class_list_name: Optional[str] = None
    total_marks_awarded: Optional[float] = None
    total_marks_possible: Optional[float] = None
    percentage: Optional[float] = None
    ai_comment: Optional[str] = None
    question_breakdown: list[QuestionBreakdown] = []
    error_message: Optional[str] = None


class ProcessingProgress(BaseModel):
    session_id: str
    status: SessionStatus
    total_papers: int
    processed_papers: int
    current_filename: Optional[str] = None
    papers: list[GradedPaper] = []


class ClassSummary(BaseModel):
    class_average_percentage: float
    highest_percentage: float
    lowest_percentage: float
    total_students_graded: int
    hardest_questions: list[dict]
    intervention_list: list[dict]
