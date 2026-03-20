# 🧭 PathfinderAI v2 — Adaptive Onboarding Engine

> **ARTPARK CodeForge Hackathon** · Production-grade AI-driven skill gap engine

---

## 📁 Folder Structure

```
pathfinder-v2/
└── backend/
    ├── main.py                  # FastAPI app + SSE log streaming
    ├── requirements.txt
    ├── templates/
    │   └── index.html           # Full frontend (served by FastAPI)
    ├── engine/
    │   ├── __init__.py
    │   ├── extractor.py         # Gemini calls ONLY — skill extraction
    │   ├── skill_gap.py         # Pure logic gap engine (NO LLM)
    │   └── path_generator.py    # Pure logic path algorithm (NO LLM)
    └── routers/
        ├── __init__.py
        └── analyze.py           # POST /api/analyze endpoint
```

---

## 🚀 Setup & Run

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000**

---
## API KEY---

Get a free Gemini API key at:
https://aistudio.google.com/app/apikey
Enter it in the UI before clicking Analyze.


## 🏗 Architecture

```
Frontend (HTML/JS)
    │
    ├── POST /api/analyze  (FormData: resume PDF + JD text + API key)
    │
    └── GET  /logs/{sid}   (SSE: real-time backend log stream)

Backend (FastAPI)
    │
    ├── [extractor.py]    Gemini 2.5 Flash  ← ONLY LLM usage
    │   ├── extract_resume_skills() → [{name, level}]
    │   └── extract_jd_skills()     → [{name, level, importance}]
    │
    ├── [skill_gap.py]    Pure Python — NO LLM
    │   ├── compute_skill_gaps()     → [SkillGap]
    │   ├── filter_actionable_gaps() → [SkillGap]
    │   └── get_summary_stats()      → {counts, critical_gaps}
    │
    └── [path_generator.py]  Pure Python — NO LLM
        ├── Priority sort (master > learn > revise, then importance, then gap)
        ├── Dependency resolution (prerequisite map)
        ├── Topological sort (Kahn's BFS)
        └── Time estimation (gap × hours_per_level)
```

---

## 📡 API Reference

### `POST /api/analyze`

**Form fields:**
| Field     | Type | Required | Description |
|-----------|------|----------|-------------|
| `resume`  | File | ✅ | PDF resume |
| `jd_text` | str  | ✅ | Job description text |
| `api_key` | str  | ✅ | Gemini API key |
| `sid`     | str  | Optional | Session ID for SSE logs |

### `GET /logs/{sid}`

Server-Sent Events stream. Open before POST. Receives:
- `{"ts":"12:00:01","level":"ok","msg":"PDF parsed · 3241 chars"}`
- `__DONE__` when analysis completes

---

## 📊 Example API Response

```json
{
  "resume_skills": [
    {"name": "Python", "level": 7},
    {"name": "Pandas", "level": 6},
    {"name": "SQL", "level": 5}
  ],
  "jd_skills": [
    {"name": "Python", "level": 8, "importance": 9},
    {"name": "Machine Learning", "level": 7, "importance": 9},
    {"name": "Docker", "level": 6, "importance": 8},
    {"name": "Deep Learning", "level": 7, "importance": 7}
  ],
  "all_gaps": [
    {
      "skill": "Python",
      "user_level": 7,
      "required_level": 8,
      "gap": 1,
      "priority": "revise",
      "importance": 9,
      "reason": "'Python': user level 7, required level 8 → gap = 1 → classified as 'revise'. JD importance 9/10 (critical) → placed early in roadmap."
    },
    {
      "skill": "Machine Learning",
      "user_level": 0,
      "required_level": 7,
      "gap": 7,
      "priority": "master",
      "importance": 9,
      "reason": "'Machine Learning': skill not found in resume (assumed level 1), required level 7 → gap = 7 → classified as 'master'. JD importance 9/10 (critical) → placed early in roadmap."
    }
  ],
  "summary": {
    "total_jd_skills": 4,
    "matched_skills": 1,
    "skills_to_develop": 3,
    "by_priority": {"revise": 1, "learn": 1, "master": 2},
    "critical_gaps": ["Machine Learning", "Docker"]
  },
  "roadmap": [
    {
      "step": 1,
      "skill": "Python",
      "priority": "revise",
      "priority_label": "🔄 Revise",
      "user_level": 7,
      "required_level": 8,
      "gap": 1,
      "importance": 9,
      "estimated_hours": 3,
      "estimated_weeks": 0.3,
      "milestone": "🚀 Start Here",
      "reason": "'Python': user level 7, required level 8 → gap = 1 → classified as 'revise'..."
    },
    {
      "step": 2,
      "skill": "Machine Learning",
      "priority": "master",
      "priority_label": "🔥 Master",
      "user_level": 0,
      "required_level": 7,
      "gap": 7,
      "importance": 9,
      "estimated_hours": 56,
      "estimated_weeks": 5.6,
      "milestone": "⚡ Critical Skill",
      "reason": "'Machine Learning': not found in resume → gap = 7 → 'master'..."
    }
  ],
  "total_hours": 94,
  "total_weeks": 9.4,
  "phase_breakdown": {
    "revise": {"hours": 3,  "weeks": 0.3, "week_start": 1,   "week_end": 1.3},
    "learn":  {"hours": 35, "weeks": 3.5, "week_start": 1.3, "week_end": 4.8},
    "master": {"hours": 56, "weeks": 5.6, "week_start": 4.8, "week_end": 10.4}
  },
  "meta": {
    "elapsed_seconds": 3.4,
    "session_id": "abc123...",
    "gemini_used_for": "skill extraction only",
    "decision_engine": "custom logic (no LLM)"
  }
}
```

---

## 🧠 Gap Classification Logic

```python
gap <= 0  → "skip"    # Already meets requirement
gap 1–3   → "revise"  # Needs refreshing (3h per gap level)
gap 4–6   → "learn"   # Needs structured learning (5h per gap level)
gap 7+    → "master"  # Deep, long-term effort (8h per gap level)
```

## ⏱ Time Estimation Formula

```
estimated_hours = gap × hours_per_level[priority]
  revise: 3h/level
  learn:  5h/level
  master: 8h/level
```

---

## 📦 Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI |
| LLM | Google Gemini 2.5 Flash (extraction only) |
| PDF Parsing | pypdf |
| Gap Engine | Custom pure-Python logic |
| Path Algorithm | Priority sort + Kahn's topological sort |
| Streaming | Server-Sent Events (SSE) |
| Frontend | Vanilla HTML/CSS/JS |
