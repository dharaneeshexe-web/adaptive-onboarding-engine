"""
routers/analyze.py
──────────────────
Main analysis endpoint.
Orchestrates: PDF parse → Gemini extract → Gap engine → Path generator → Response
"""

import time
import uuid
from io import BytesIO

import httpx
from fastapi import APIRouter, Form, File, UploadFile, Request, HTTPException
from fastapi.responses import JSONResponse
from pypdf import PdfReader

from engine.extractor import extract_resume_skills, extract_jd_skills
from engine.skill_gap import compute_skill_gaps, filter_actionable_gaps, get_summary_stats
from engine.path_generator import generate_learning_path

router = APIRouter()


# ── Helper: get logger from app.state ────────────────────────────────────────

def _log(request: Request, level: str, msg: str):
    sid = request.state.sid
    request.app.state.push_log(sid, level, msg)


# ── POST /api/analyze ─────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze(
    request:    Request,
    api_key:    str        = Form(...),
    jd_text:    str        = Form(...),
    sid:        str        = Form(default=""),
    resume:     UploadFile = File(...),
):
    """
    Full analysis pipeline:
    1. Parse PDF → extract resume text
    2. Gemini: extract resume skills with levels
    3. Gemini: extract JD skills with levels + importance
    4. Skill Gap Engine: compute gap per skill (NO LLM)
    5. Path Generator: sort, resolve deps, build roadmap (NO LLM)
    6. Return structured JSON response
    """
    # Attach session ID for SSE logging
    request.state.sid = sid or str(uuid.uuid4())

    def log(level: str, msg: str):
        _log(request, level, msg)

    t_start = time.time()

    try:
        # ── Step 1: Parse PDF ─────────────────────────────────────────────────
        log("info", f"Session {request.state.sid[:8]} · request received")

        if resume.content_type != "application/pdf":
            raise HTTPException(400, "Only PDF resumes are accepted.")

        pdf_bytes   = await resume.read()
        log("info", f"PDF received · {len(pdf_bytes)//1024} KB")

        reader      = PdfReader(BytesIO(pdf_bytes))
        resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)

        if not resume_text.strip():
            log("error", "PDF text extraction failed — scanned image PDF?")
            raise HTTPException(400, "Could not extract text from PDF. Use a text-based PDF.")

        log("ok", f"PDF parsed · {len(resume_text)} chars · {len(reader.pages)} page(s)")

        # ── Step 2: Gemini — Resume Skill Extraction ──────────────────────────
        log("info", "Calling Gemini: resume skill extraction...")
        t_gemini = time.time()

        try:
            resume_skills = await extract_resume_skills(resume_text, api_key)
        except httpx.HTTPStatusError as e:
            log("error", f"Gemini API error: {e.response.status_code}")
            raise HTTPException(502, f"Gemini API error: {e}")

        log("ok", f"Resume skills extracted · {len(resume_skills)} skills · {round(time.time()-t_gemini,2)}s")
        for s in resume_skills:
            log("info", f"  · {s['name']} (level {s['level']}/10)")

        # ── Step 3: Gemini — JD Skill Extraction ─────────────────────────────
        log("info", "Calling Gemini: JD skill extraction...")
        t_jd = time.time()

        try:
            jd_skills = await extract_jd_skills(jd_text, api_key)
        except httpx.HTTPStatusError as e:
            log("error", f"Gemini API error on JD: {e.response.status_code}")
            raise HTTPException(502, f"Gemini API error: {e}")

        log("ok", f"JD skills extracted · {len(jd_skills)} required · {round(time.time()-t_jd,2)}s")
        for s in jd_skills:
            log("info", f"  · {s['name']} (req level {s['level']}/10, importance {s['importance']}/10)")

        # ── Step 4: Skill Gap Engine (pure logic, no LLM) ─────────────────────
        log("info", "Running Skill Gap Engine (no LLM)...")
        t_gap = time.time()

        all_gaps       = compute_skill_gaps(resume_skills, jd_skills)
        actionable     = filter_actionable_gaps(all_gaps)
        summary        = get_summary_stats(all_gaps)

        log("ok", f"Gap analysis complete · {round(time.time()-t_gap, 4)}s")
        log("ok",  f"Matched: {summary['matched_skills']} · To develop: {summary['skills_to_develop']}")
        log("info", f"By priority → revise:{summary['by_priority']['revise']} "
                    f"learn:{summary['by_priority']['learn']} "
                    f"master:{summary['by_priority']['master']}")
        if summary["critical_gaps"]:
            log("warn", f"Critical gaps: {', '.join(summary['critical_gaps'])}")

        # ── Step 5: Adaptive Path Generator (pure logic, no LLM) ─────────────
        log("info", "Running Adaptive Path Generator (no LLM)...")
        t_path = time.time()

        path_result = generate_learning_path(actionable)

        log("ok", f"Roadmap generated · {len(path_result['roadmap'])} steps · "
                  f"{path_result['total_hours']}h total · {round(time.time()-t_path, 4)}s")

        for item in path_result["roadmap"]:
            log("info", f"  Step {item['step']:02d} · {item['skill']} · "
                        f"{item['priority']} · {item['estimated_hours']}h")

        # ── Final Response ────────────────────────────────────────────────────
        total_elapsed = round(time.time() - t_start, 2)
        log("ok", f"Analysis complete · total time {total_elapsed}s")

        # Signal SSE stream to close
        request.app.state.close_log(request.state.sid)

        return JSONResponse({
            # Extracted data
            "resume_skills": resume_skills,
            "jd_skills":     jd_skills,

            # Gap analysis (all gaps including "skip")
            "all_gaps": [g.to_dict() for g in all_gaps],

            # Actionable gaps only
            "actionable_gaps": [g.to_dict() for g in actionable],

            # Summary statistics
            "summary": summary,

            # Final roadmap
            "roadmap":         path_result["roadmap"],
            "total_hours":     path_result["total_hours"],
            "total_weeks":     path_result["total_weeks"],
            "phase_breakdown": path_result["phase_breakdown"],

            # Meta
            "meta": {
                "elapsed_seconds": total_elapsed,
                "session_id":      request.state.sid,
                "gemini_used_for": "skill extraction only",
                "decision_engine": "custom logic (no LLM)",
            }
        })

    except HTTPException:
        request.app.state.close_log(request.state.sid)
        raise
    except Exception as e:
        log("error", f"Unexpected error: {str(e)}")
        request.app.state.close_log(request.state.sid)
        raise HTTPException(500, f"Internal server error: {str(e)}")
