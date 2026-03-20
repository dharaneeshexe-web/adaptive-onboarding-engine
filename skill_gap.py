"""
skill_gap.py
────────────
PURE LOGIC — No LLM involved.
Computes the gap between what a candidate has and what a role requires.

Gap classification:
  gap <= 0  → "skip"    (already qualified)
  gap 1–3   → "revise"  (needs refreshing)
  gap 4–6   → "learn"   (needs structured learning)
  gap 7+    → "master"  (needs deep, long-term effort)
"""

from dataclasses import dataclass, field
from typing import Literal

# ── Types ─────────────────────────────────────────────────────────────────────

Priority = Literal["skip", "revise", "learn", "master"]

@dataclass
class SkillGap:
    skill:          str
    user_level:     int          # 1–10, from resume (0 if not found)
    required_level: int          # 1–10, from JD
    gap:            int          # required - user (can be negative)
    priority:       Priority
    importance:     int          # 1–10, from JD
    reason:         str          # Human-readable reasoning trace

    def to_dict(self) -> dict:
        return {
            "skill":          self.skill,
            "user_level":     self.user_level,
            "required_level": self.required_level,
            "gap":            self.gap,
            "priority":       self.priority,
            "importance":     self.importance,
            "reason":         self.reason,
        }


# ── Gap Classifier ────────────────────────────────────────────────────────────

def _classify_gap(gap: int) -> Priority:
    """
    Map numeric gap to priority category.
    This is the core classification logic — intentionally simple and auditable.
    """
    if gap <= 0:  return "skip"
    if gap <= 3:  return "revise"
    if gap <= 6:  return "learn"
    return "master"


def _build_reason(
    skill: str,
    user_level: int,
    required_level: int,
    gap: int,
    priority: Priority,
    importance: int,
    found_in_resume: bool,
) -> str:
    """
    Construct a human-readable reasoning trace for each gap decision.
    This is the mandatory reasoning trace required by the hackathon spec.
    """
    if priority == "skip":
        return (
            f"Candidate already meets the requirement for '{skill}' "
            f"(user level {user_level} ≥ required {required_level}) → skipped."
        )

    source = (
        f"user level {user_level}"
        if found_in_resume
        else f"skill not found in resume (assumed level 1)"
    )
    imp_label = (
        "critical" if importance >= 8
        else "important" if importance >= 5
        else "supplementary"
    )

    return (
        f"'{skill}': {source}, required level {required_level} → "
        f"gap = {gap} → classified as '{priority}'. "
        f"JD importance {importance}/10 ({imp_label}) → "
        f"{'placed early in roadmap' if importance >= 7 else 'placed later in roadmap'}."
    )


# ── Main Gap Engine ───────────────────────────────────────────────────────────

def compute_skill_gaps(
    resume_skills: list[dict],
    jd_skills:     list[dict],
) -> list[SkillGap]:
    """
    Core gap computation engine.

    Algorithm:
    1. Build a lookup map from resume skills (normalized lowercase key)
    2. For each JD skill, find the candidate's level (0 if missing)
    3. Compute gap = required - user
    4. Classify into priority bucket
    5. Attach importance from JD for downstream sorting

    Args:
        resume_skills: [{"name": str, "level": int}]
        jd_skills:     [{"name": str, "level": int, "importance": int}]

    Returns:
        List of SkillGap objects (includes "skip" entries for completeness)
    """
    # Build resume lookup: normalized name → level
    resume_map: dict[str, int] = {
        s["name"].lower().strip(): s["level"]
        for s in resume_skills
    }

    gaps: list[SkillGap] = []

    for jd_skill in jd_skills:
        name           = jd_skill["name"]
        required_level = jd_skill["level"]
        importance     = jd_skill.get("importance", 5)

        # Look up user's level (exact match first, then partial)
        key            = name.lower().strip()
        found_in_resume = key in resume_map

        if not found_in_resume:
            # Try partial match (e.g. "Machine Learning" vs "ML")
            for resume_key, lvl in resume_map.items():
                if key in resume_key or resume_key in key:
                    found_in_resume = True
                    resume_map[key] = lvl   # Cache the match
                    break

        user_level = resume_map.get(key, 1 if not found_in_resume else 1)
        if not found_in_resume:
            user_level = 0   # Completely missing from resume

        gap      = required_level - user_level
        priority = _classify_gap(gap)
        reason   = _build_reason(name, user_level, required_level, gap, priority, importance, found_in_resume)

        gaps.append(SkillGap(
            skill=name,
            user_level=user_level,
            required_level=required_level,
            gap=gap,
            priority=priority,
            importance=importance,
            reason=reason,
        ))

    return gaps


def filter_actionable_gaps(gaps: list[SkillGap]) -> list[SkillGap]:
    """Return only gaps that require action (exclude 'skip')."""
    return [g for g in gaps if g.priority != "skip"]


def get_summary_stats(gaps: list[SkillGap]) -> dict:
    """Aggregate statistics across all gaps for the frontend dashboard."""
    actionable = filter_actionable_gaps(gaps)
    by_priority = {"revise": 0, "learn": 0, "master": 0}
    for g in actionable:
        by_priority[g.priority] = by_priority.get(g.priority, 0) + 1

    matched = [g for g in gaps if g.priority == "skip"]

    return {
        "total_jd_skills":    len(gaps),
        "matched_skills":     len(matched),
        "skills_to_develop":  len(actionable),
        "by_priority":        by_priority,
        "critical_gaps":      [g.skill for g in actionable if g.importance >= 8],
    }
