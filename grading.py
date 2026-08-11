"""
Core AI grading logic. Sends a student's scanned paper (as images) plus the
memo text to GPT-4o Vision and parses a structured JSON grading result.
"""
from __future__ import annotations
import json
import logging
from difflib import SequenceMatcher
from typing import Optional

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

from app.config import settings
from app.schemas import GradedPaper, PaperStatus, QuestionBreakdown

logger = logging.getLogger("markingai.grading")

SYSTEM_PROMPT = """You are an expert South African CAPS-curriculum teacher's assistant. \
Your job is to mark a scanned student test paper strictly according to the memo \
(marking guideline) provided. You are meticulous, fair, and consistent.

Rules:
1. Read the student's handwritten or typed answers from the page image(s) provided.
2. Compare each answer against the memo to award marks. Award partial marks where the \
memo or working shown justifies it, exactly as a real teacher would.
3. If the student's name is visible on the paper, extract it exactly as written. If not \
visible or illegible, set student_name to null.
4. Total the marks awarded and compute a percentage against the stated total marks for the test.
5. Write a short, encouraging, specific comment (2-3 sentences) aimed at the student, \
noting a strength and a concrete area to improve, in a South African classroom tone.
6. Provide a per-question breakdown where question numbers are identifiable in the memo.
7. If the paper is illegible, blank, or clearly not a valid test paper, set status to \
"needs_review" and explain why in error_message, leaving marks as 0.

You MUST respond with ONLY valid JSON (no markdown fences, no commentary) matching exactly \
this schema:
{
  "student_name": string or null,
  "total_marks_awarded": number,
  "question_breakdown": [
    {"question": string, "marks_awarded": number, "marks_possible": number or null, "comment": string or null}
  ],
  "ai_comment": string,
  "status": "done" or "needs_review",
  "error_message": string or null
}
"""


def _build_user_content(memo_text: str, total_marks: float, subject: str, grade: str,
                         page_images_b64: list[str]) -> list[dict]:
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Subject: {subject}\n"
                f"Grade: {grade}\n"
                f"Total marks possible for this test: {total_marks}\n\n"
                f"MEMO / MARKING GUIDELINE:\n{memo_text if memo_text else '(No text memo provided - use your subject knowledge and the memo images if included as additional pages.)'}\n\n"
                f"Below are the page image(s) of the student's scanned answer paper, in order. "
                f"Mark this paper according to the memo above and respond with the required JSON only."
            ),
        }
    ]
    for b64 in page_images_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
        })
    return content


def _safe_json_parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    return json.loads(raw)


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def match_to_class_list(student_name: Optional[str], class_list: list[dict]) -> Optional[str]:
    """Fuzzy-match the AI-extracted name to the closest name in the class list."""
    if not student_name or not class_list:
        return None
    best_name = None
    best_score = 0.0
    for entry in class_list:
        score = _name_similarity(student_name, entry["name"])
        if score > best_score:
            best_score = score
            best_name = entry["name"]
    return best_name if best_score >= 0.6 else None


async def grade_single_paper(
    client: AsyncOpenAI,
    paper_id: str,
    filename: str,
    page_images_b64: list[str],
    memo_text: str,
    total_marks: float,
    subject: str,
    grade: str,
    class_list: list[dict],
) -> GradedPaper:
    """Grade one student paper via GPT-4o Vision and return a GradedPaper result."""
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_content(
                    memo_text, total_marks, subject, grade, page_images_b64
                )},
            ],
            max_tokens=1500,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw_text = response.choices[0].message.content or "{}"
        data = _safe_json_parse(raw_text)

        marks_awarded = float(data.get("total_marks_awarded") or 0)
        percentage = round((marks_awarded / total_marks) * 100, 1) if total_marks > 0 else 0.0
        percentage = max(0.0, min(100.0, percentage))

        breakdown = [
            QuestionBreakdown(
                question=str(q.get("question", "")),
                marks_awarded=float(q.get("marks_awarded") or 0),
                marks_possible=(float(q["marks_possible"]) if q.get("marks_possible") is not None else None),
                comment=q.get("comment"),
            )
            for q in data.get("question_breakdown", []) or []
        ]

        status_str = data.get("status", "done")
        status = PaperStatus.NEEDS_REVIEW if status_str == "needs_review" else PaperStatus.DONE

        student_name = data.get("student_name")
        matched_name = match_to_class_list(student_name, class_list)

        return GradedPaper(
            paper_id=paper_id,
            filename=filename,
            status=status,
            student_name=student_name,
            matched_class_list_name=matched_name,
            total_marks_awarded=round(marks_awarded, 1),
            total_marks_possible=total_marks,
            percentage=percentage,
            ai_comment=data.get("ai_comment"),
            question_breakdown=breakdown,
            error_message=data.get("error_message"),
        )

    except (RateLimitError, APIConnectionError, APIError) as e:
        logger.error(f"OpenAI API error grading {filename}: {e}")
        return GradedPaper(
            paper_id=paper_id,
            filename=filename,
            status=PaperStatus.FAILED,
            error_message=f"AI service error: {str(e)[:200]}",
        )
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error grading {filename}: {e}")
        return GradedPaper(
            paper_id=paper_id,
            filename=filename,
            status=PaperStatus.FAILED,
            error_message="Could not parse AI response. Please retry this paper.",
        )
    except Exception as e:
        logger.exception(f"Unexpected error grading {filename}")
        return GradedPaper(
            paper_id=paper_id,
            filename=filename,
            status=PaperStatus.FAILED,
            error_message=f"Unexpected error: {str(e)[:200]}",
        )
