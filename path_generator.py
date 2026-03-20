"""
path_generator.py
─────────────────
PURE LOGIC — No LLM involved.
Takes skill gaps and generates an ordered, dependency-aware learning roadmap.

Ordering logic (multi-key sort):
  1. Priority weight  (master > learn > revise)
  2. Importance       (higher JD importance → earlier)
  3. Gap size         (larger gap → earlier, more urgent)
  4. Dependency order (prerequisites always come first via topological sort)

Time estimation:
  estimated_hours = gap × HOURS_PER_LEVEL[priority]
  revise → 3h/level, learn → 5h/level, master → 8h/level
"""

from collections import defaultdict, deque
from engine.skill_gap import SkillGap, Priority

# ── Constants ─────────────────────────────────────────────────────────────────

# Hours required per gap level by priority category
HOURS_PER_LEVEL: dict[Priority, int] = {
    "revise": 3,
    "learn":  5,
    "master": 8,
}

# Priority sort weight (higher = placed earlier)
PRIORITY_WEIGHT: dict[Priority, int] = {
    "master": 3,
    "learn":  2,
    "revise": 1,
    "skip":   0,
}

# ── Dependency Graph ──────────────────────────────────────────────────────────
# Maps skill → list of prerequisites.
# Normalized to lowercase for matching.
# Extend this map as needed — it drives the topological ordering.

RAW_DEPENDENCY_MAP: dict[str, list[str]] = {
    # Programming foundations
    "python advanced":      ["python"],
    "data analysis":        ["python"],
    "pandas":               ["python"],
    "numpy":                ["python"],

    # Data science chain
    "machine learning":     ["python", "statistics"],
    "deep learning":        ["machine learning"],
    "natural language processing": ["deep learning"],
    "computer vision":      ["deep learning"],
    "reinforcement learning": ["deep learning"],

    # AI/LLM chain
    "llm fine-tuning":      ["deep learning", "natural language processing"],
    "prompt engineering":   ["machine learning"],
    "rag systems":          ["natural language processing"],

    # Data engineering
    "data engineering":     ["python", "sql"],
    "apache spark":         ["python", "sql"],
    "airflow":              ["python", "data engineering"],

    # MLOps chain
    "mlops":                ["machine learning", "docker"],
    "kubernetes":           ["docker"],
    "model deployment":     ["machine learning", "docker"],

    # Backend chain
    "fastapi":              ["python"],
    "django":               ["python"],
    "rest api":             ["python"],
    "graphql":              ["rest api"],

    # Frontend chain
    "react":                ["javascript"],
    "nextjs":               ["react"],
    "typescript":           ["javascript"],

    # Cloud chain
    "aws sagemaker":        ["machine learning", "amazon web services"],
    "google vertex ai":     ["machine learning", "google cloud"],

    # Database chain
    "postgresql":           ["sql"],
    "mongodb":              ["nosql basics"],

    # Healthcare chain
    "ehr systems":          ["healthcare basics"],
    "clinical informatics": ["healthcare basics", "sql"],

    # Soft skill chain
    "technical leadership": ["communication"],
}


def _normalize(name: str) -> str:
    """Lowercase + strip for consistent key matching."""
    return name.lower().strip()


def _build_dep_map(skills_in_roadmap: list[str]) -> dict[str, list[str]]:
    """
    Build a dependency map restricted to skills that actually appear
    in the current roadmap. Ignores external dependencies not in scope.
    """
    skill_set  = {_normalize(s) for s in skills_in_roadmap}
    dep_map: dict[str, list[str]] = {}

    for skill in skills_in_roadmap:
        key      = _normalize(skill)
        raw_deps = RAW_DEPENDENCY_MAP.get(key, [])
        # Only keep deps that are also in the roadmap
        in_scope = [d for d in raw_deps if _normalize(d) in skill_set]
        dep_map[key] = in_scope

    return dep_map


# ── Topological Sort (Kahn's Algorithm) ──────────────────────────────────────

def _topological_sort(skills: list[str], dep_map: dict[str, list[str]]) -> list[str]:
    """
    Kahn's BFS topological sort.
    Ensures prerequisites always appear before the skills that depend on them.
    If no dependency exists between two skills, their relative order is preserved
    from the priority-sorted input.
    """
    norm_to_orig = {_normalize(s): s for s in skills}
    in_degree    = defaultdict(int)
    adjacency    = defaultdict(list)   # prereq → skills that need it

    for skill in skills:
        key  = _normalize(skill)
        deps = dep_map.get(key, [])
        in_degree[key] = len(deps)
        for dep in deps:
            adjacency[dep].append(key)

    # Start with skills that have no prerequisites (in roadmap scope)
    # Preserve the priority ordering within each "free" layer
    queue = deque(
        [_normalize(s) for s in skills if in_degree[_normalize(s)] == 0]
    )
    ordered: list[str] = []

    while queue:
        node = queue.popleft()
        if node in norm_to_orig:
            ordered.append(norm_to_orig[node])
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Safety: append any nodes not reached (cycles or missing deps)
    reached = {_normalize(s) for s in ordered}
    for s in skills:
        if _normalize(s) not in reached:
            ordered.append(s)

    return ordered


# ── Time Estimation ───────────────────────────────────────────────────────────

def estimate_hours(gap: int, priority: Priority) -> int:
    """
    Time estimation formula:
        hours = max(gap, 1) × hours_per_level[priority]

    Examples:
        gap=2, revise → 6h
        gap=5, learn  → 25h
        gap=8, master → 64h
    """
    return max(gap, 1) * HOURS_PER_LEVEL.get(priority, 5)


# ── Roadmap Item ──────────────────────────────────────────────────────────────

def _build_roadmap_item(step: int, gap: SkillGap) -> dict:
    """Build a single roadmap step dict from a SkillGap."""
    hours = estimate_hours(gap.gap, gap.priority)
    weeks = round(hours / 10, 1)   # Assumes ~10h/week learning pace

    priority_labels = {
        "revise": "🔄 Revise",
        "learn":  "📘 Learn",
        "master": "🔥 Master",
    }

    return {
        "step":            step,
        "skill":           gap.skill,
        "priority":        gap.priority,
        "priority_label":  priority_labels.get(gap.priority, gap.priority),
        "user_level":      gap.user_level,
        "required_level":  gap.required_level,
        "gap":             gap.gap,
        "importance":      gap.importance,
        "estimated_hours": hours,
        "estimated_weeks": weeks,
        "reason":          gap.reason,
        "milestone":       _get_milestone(step, gap.priority, gap.importance),
    }


def _get_milestone(step: int, priority: Priority, importance: int) -> str:
    if step == 1:                              return "🚀 Start Here"
    if priority == "master" and importance>=8: return "⚡ Critical Skill"
    if priority == "master":                   return "🏔 Deep Mastery"
    if priority == "learn" and importance>=8:  return "🎯 High Priority"
    if priority == "learn":                    return "📈 Core Learning"
    return "✅ Quick Win"


# ── Main Path Generator ───────────────────────────────────────────────────────

def generate_learning_path(actionable_gaps: list[SkillGap]) -> dict:
    """
    Main adaptive path generation function.

    Steps:
    1. Sort gaps by (priority_weight DESC, importance DESC, gap DESC)
    2. Build dependency map for skills in this roadmap
    3. Topological sort to enforce prerequisites
    4. Build final roadmap with time estimates + reasoning
    5. Compute aggregate stats

    Args:
        actionable_gaps: List of SkillGap with priority != "skip"

    Returns:
        {
          "roadmap": [...],
          "total_hours": int,
          "total_weeks": float,
          "phase_breakdown": {...}
        }
    """
    if not actionable_gaps:
        return {
            "roadmap":         [],
            "total_hours":     0,
            "total_weeks":     0.0,
            "phase_breakdown": {},
        }

    # Step 1: Priority sort (multi-key, descending)
    sorted_gaps = sorted(
        actionable_gaps,
        key=lambda g: (
            PRIORITY_WEIGHT[g.priority],    # master first
            g.importance,                    # higher importance first
            g.gap,                           # bigger gap first
        ),
        reverse=True,
    )

    # Step 2: Build dependency map
    skill_names = [g.skill for g in sorted_gaps]
    dep_map     = _build_dep_map(skill_names)

    # Step 3: Topological sort (preserves priority order within free layers)
    ordered_names = _topological_sort(skill_names, dep_map)

    # Rebuild gap lookup
    gap_lookup = {g.skill: g for g in sorted_gaps}

    # Step 4: Build roadmap items
    roadmap      = []
    phase_hours  = {"revise": 0, "learn": 0, "master": 0}
    total_hours  = 0

    for step, skill_name in enumerate(ordered_names, 1):
        gap = gap_lookup.get(skill_name)
        if not gap:
            continue
        item = _build_roadmap_item(step, gap)
        roadmap.append(item)
        total_hours              += item["estimated_hours"]
        phase_hours[gap.priority] = phase_hours.get(gap.priority, 0) + item["estimated_hours"]

    total_weeks = round(total_hours / 10, 1)   # 10h/week pace

    # Step 5: Phase breakdown with week ranges
    phase_breakdown = {}
    week_cursor     = 1
    for priority_key in ["revise", "learn", "master"]:
        hrs   = phase_hours.get(priority_key, 0)
        weeks = round(hrs / 10, 1)
        phase_breakdown[priority_key] = {
            "hours":       hrs,
            "weeks":       weeks,
            "week_start":  week_cursor,
            "week_end":    round(week_cursor + weeks - 0.1, 1),
        }
        week_cursor += weeks

    return {
        "roadmap":         roadmap,
        "total_hours":     total_hours,
        "total_weeks":     total_weeks,
        "phase_breakdown": phase_breakdown,
    }
