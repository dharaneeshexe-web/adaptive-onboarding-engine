"""
extractor.py
────────────
Gemini is ONLY used here. Nothing else in the system calls the LLM.
Responsible for:
  - Extracting skills + levels from resume text
  - Extracting skills + levels + importance from JD text
  - Strict JSON validation and normalization
"""

import re
import json
import httpx
from typing import Any

# ── Prompt Templates ──────────────────────────────────────────────────────────

RESUME_PROMPT = """You are a technical skills extractor.
Analyze the resume and return ONLY this exact JSON — no markdown, no explanation:
{{"skills":[{{"name":"Python","level":7}},{{"name":"SQL","level":6}}]}}

Rules:
- level: 1-10 (1=heard of it, 5=used it, 8=proficient, 10=expert)
- max 20 skills, short names only (under 25 chars)
- Include technical skills, tools, frameworks, soft skills
- Normalize: ML->Machine Learning, k8s->Kubernetes, JS->JavaScript

RESUME TEXT:
{resume_text}"""

JD_PROMPT = """You are a job requirements extractor.
Analyze the job description and return ONLY this exact JSON — no markdown, no explanation:
{{"skills":[{{"name":"Python","level":8,"importance":9}},{{"name":"SQL","level":6,"importance":7}}]}}

Rules:
- level: minimum proficiency required (1-10)
- importance: how critical this skill is for the role (1-10)
- max 18 skills, short names only (under 25 chars)
- Normalize: ML->Machine Learning, k8s->Kubernetes

JOB DESCRIPTION:
{jd_text}"""


# ── Gemini API Call ───────────────────────────────────────────────────────────

async def _call_gemini(prompt: str, api_key: str) -> str:
    """
    Single async call to Gemini 2.5 Flash.
    Returns raw text response.
    """
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,       # Zero temp = deterministic, structured output
            "maxOutputTokens": 2048,
        },
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


# ── JSON Parser ───────────────────────────────────────────────────────────────

def _parse_json_safe(raw: str, context: str = "") -> dict:
    """
    Robust JSON parser:
    1. Strip markdown fences
    2. Extract first { ... } block
    3. Validate required keys exist
    """
    # Strip ```json fences
    clean = re.sub(r"```(?:json)?|```", "", raw).strip()

    # Extract outermost JSON object
    start = clean.find("{")
    end   = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"[{context}] No JSON object found in: {raw[:200]}")

    parsed = json.loads(clean[start:end])

    if "skills" not in parsed or not isinstance(parsed["skills"], list):
        raise ValueError(f"[{context}] Missing 'skills' array in response")

    return parsed


# ── Skill Normalizer ──────────────────────────────────────────────────────────

SKILL_ALIASES = {
    "ml": "Machine Learning", "ai": "Machine Learning",
    "dl": "Deep Learning",    "nn": "Neural Networks",
    "nlp": "Natural Language Processing",
    "cv": "Computer Vision",  "js": "JavaScript",
    "ts": "TypeScript",       "k8s": "Kubernetes",
    "tf": "TensorFlow",       "gcp": "Google Cloud",
    "aws": "Amazon Web Services",
}

def _normalize_skill_name(name: str) -> str:
    lower = name.lower().strip()
    return SKILL_ALIASES.get(lower, name.strip().title())


def _validate_skill(skill: dict, has_importance: bool = False) -> dict | None:
    """Validate and clamp a single skill dict. Returns None if invalid."""
    name = skill.get("name", "")
    if not name or len(name) > 35:
        return None

    level = max(1, min(10, int(skill.get("level", 5))))
    result = {"name": _normalize_skill_name(name), "level": level}

    if has_importance:
        importance = max(1, min(10, int(skill.get("importance", 5))))
        result["importance"] = importance

    return result


# ── Public Extraction Functions ───────────────────────────────────────────────

async def extract_resume_skills(resume_text: str, api_key: str) -> list[dict]:
    """
    Extract skills from resume text via Gemini.
    Returns: [{"name": str, "level": int}, ...]
    """
    prompt = RESUME_PROMPT.format(resume_text=resume_text[:2000])
    raw    = await _call_gemini(prompt, api_key)
    parsed = _parse_json_safe(raw, context="resume")

    skills = []
    for s in parsed["skills"]:
        validated = _validate_skill(s, has_importance=False)
        if validated:
            skills.append(validated)

    return skills[:20]   # Hard cap


async def extract_jd_skills(jd_text: str, api_key: str) -> list[dict]:
    """
    Extract required skills from JD text via Gemini.
    Returns: [{"name": str, "level": int, "importance": int}, ...]
    """
    prompt = JD_PROMPT.format(jd_text=jd_text[:2000])
    raw    = await _call_gemini(prompt, api_key)
    parsed = _parse_json_safe(raw, context="jd")

    skills = []
    for s in parsed["skills"]:
        validated = _validate_skill(s, has_importance=True)
        if validated:
            skills.append(validated)

    return skills[:18]   # Hard cap
