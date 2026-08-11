"""
Step 4: Results & Export endpoints.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.store import store
from app.schemas import ClassSummary, PaperStatus, GradedPaper
from app.services.export import build_sasams_export, build_class_report

router = APIRouter(prefix="/api/sessions", tags=["results"])


@router.get("/{session_id}/results")
async def get_results(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    return {
        "session_id": session.session_id,
        "subject": session.subject,
        "grade": session.grade,
        "test_name": session.test_name,
        "total_marks": session.total_marks,
        "status": session.status,
        "papers": [session.papers[pid] for pid in session.paper_order],
    }


@router.patch("/{session_id}/papers/{paper_id}")
async def edit_paper_result(session_id: str, paper_id: str, updates: dict):
    """Allow a teacher to manually override AI marks/name before export."""
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    if paper_id not in session.papers:
        raise HTTPException(404, "Paper not found.")

    paper: GradedPaper = session.papers[paper_id]
    if "student_name" in updates:
        paper.student_name = updates["student_name"]
    if "matched_class_list_name" in updates:
        paper.matched_class_list_name = updates["matched_class_list_name"]
    if "total_marks_awarded" in updates:
        try:
            marks = float(updates["total_marks_awarded"])
            paper.total_marks_awarded = marks
            if session.total_marks > 0:
                paper.percentage = round(max(0, min(100, (marks / session.total_marks) * 100)), 1)
            paper.status = PaperStatus.DONE
        except (TypeError, ValueError):
            raise HTTPException(400, "total_marks_awarded must be a number")
    if "ai_comment" in updates:
        paper.ai_comment = updates["ai_comment"]

    return paper


@router.get("/{session_id}/summary", response_model=ClassSummary)
async def get_class_summary(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")

    graded = [
        session.papers[pid] for pid in session.paper_order
        if session.papers[pid].status == PaperStatus.DONE and session.papers[pid].percentage is not None
    ]

    if not graded:
        return ClassSummary(
            class_average_percentage=0, highest_percentage=0, lowest_percentage=0,
            total_students_graded=0, hardest_questions=[], intervention_list=[],
        )

    percentages = [p.percentage for p in graded]

    from collections import defaultdict
    question_stats = defaultdict(list)
    for paper in graded:
        for q in paper.question_breakdown:
            if q.marks_possible:
                question_stats[q.question].append((q.marks_awarded / q.marks_possible) * 100)

    hardest = sorted(
        [{"question": q, "avg_percentage": round(sum(v) / len(v), 1)} for q, v in question_stats.items()],
        key=lambda x: x["avg_percentage"]
    )[:5]

    intervention = [
        {
            "name": p.matched_class_list_name or p.student_name or p.filename,
            "percentage": p.percentage,
            "comment": p.ai_comment,
        }
        for p in sorted(graded, key=lambda x: x.percentage) if p.percentage < 40
    ]

    return ClassSummary(
        class_average_percentage=round(sum(percentages) / len(percentages), 1),
        highest_percentage=round(max(percentages), 1),
        lowest_percentage=round(min(percentages), 1),
        total_students_graded=len(graded),
        hardest_questions=hardest,
        intervention_list=intervention,
    )


@router.get("/{session_id}/export/sasams")
async def export_sasams(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    if session.total_papers == 0:
        raise HTTPException(400, "No papers to export.")

    path = build_sasams_export(session)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/{session_id}/export/report")
async def export_report(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    if session.total_papers == 0:
        raise HTTPException(400, "No papers to export.")

    path = build_class_report(session)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
