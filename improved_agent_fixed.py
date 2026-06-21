# ============================================================
# CELL 1 — Install packages using the KERNEL's own Python
# (paste this as first cell in your notebook to fix ModuleNotFoundError)
# ============================================================
import sys
import subprocess
subprocess.check_call([sys.executable, "-m", "pip", "install",
                       "pydantic", "langgraph", "langchain_mistralai",
                       "langchain_core", "langchain_community", "python-dotenv"])

# ============================================================
# CELL 2 — Imports
# ============================================================
from __future__ import annotations

import operator
from pathlib import Path
from typing import TypedDict, List, Annotated, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import SystemMessage, HumanMessage

# ============================================================
# CELL 3 — Load env
# ============================================================
from dotenv import load_dotenv
load_dotenv()

# ============================================================
# CELL 4 — Task model
# BUG FIX: Added missing `target_words` field that is referenced
#           in worker(). Also fixed the `bullets` field description.
# ============================================================
class Task(BaseModel):
    id: int
    title: str
    goal: str = Field(
        ...,
        description="One sentence describing what the reader should be able to do/understand after this section.",
    )
    bullets: List[str] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3-5 concrete, specific, non-overlapping bullet points for the section.",
    )
    # ✅ FIX: Added the missing `target_words` field
    target_words: int = Field(
        ...,
        description="Target word count for this section (120-450).",
    )
    section_type: Literal[
        "intro", "core", "example", "checklist", "common_mistakes", "conclusion"
    ] = Field(
        ...,
        description="Use 'common_mistakes' exactly once in the plan.",
    )

# ============================================================
# CELL 5 — Plan model
# ============================================================
class Plan(BaseModel):
    blog_title: str
    audience: str = Field(..., description="Target audience and writing tone (e.g., practitioner, crisp).")
    tasks: List[Task]

# ============================================================
# CELL 6 — State
# ============================================================
class State(TypedDict):
    topic: str
    plan: Plan
    sections: Annotated[List[str], operator.add]
    final: str

# ============================================================
# CELL 7 — Model
# ============================================================
model = ChatMistralAI(model_name="mistral-small-2506")

# ============================================================
# CELL 8 — Orchestrator node
# ============================================================
def orchestrator(state: State) -> dict:
    planner = model.with_structured_output(Plan)
    plan = planner.invoke(
        [
            SystemMessage(
                content=(
                    "You are a senior technical writer and developer advocate. Your job is to produce a "
                    "highly actionable outline for a technical blog post.\n\n"
                    "Hard requirements:\n"
                    "- Create 5–7 sections (tasks) that fit a technical blog.\n"
                    "- Each section must include:\n"
                    "  1) goal (1 sentence: what the reader can do/understand after the section)\n"
                    "  2) 3–5 bullets that are concrete, specific, and non-overlapping\n"
                    "  3) target word count (120–450)\n"
                    "- Include EXACTLY ONE section with section_type='common_mistakes'.\n\n"
                    "Make it technical (not generic):\n"
                    "- Assume the reader is a developer; use correct terminology.\n"
                    "- Prefer design/engineering structure: problem → intuition → approach → implementation → "
                    "trade-offs → testing/observability → conclusion.\n"
                    "- Bullets must be actionable and testable (e.g., 'Show a minimal code snippet for X', "
                    "'Explain why Y fails under Z condition', 'Add a checklist for production readiness').\n"
                    "- Explicitly include at least ONE of the following somewhere in the plan (as bullets):\n"
                    "  * a minimal working example (MWE) or code sketch\n"
                    "  * edge cases / failure modes\n"
                    "  * performance/cost considerations\n"
                    "  * security/privacy considerations (if relevant)\n"
                    "  * debugging tips / observability (logs, metrics, traces)\n"
                    "- Avoid vague bullets like 'Explain X' or 'Discuss Y'. Every bullet should state what "
                    "to build/compare/measure/verify.\n\n"
                    "Ordering guidance:\n"
                    "- Start with a crisp intro and problem framing.\n"
                    "- Build core concepts before advanced details.\n"
                    "- Include one section for common mistakes and how to avoid them.\n"
                    "- End with a practical summary/checklist and next steps.\n\n"
                    "Output must strictly match the Plan schema."
                )
            ),
            HumanMessage(content=f"Topic: {state['topic']}"),
        ]
    )
    return {"plan": plan}

# ============================================================
# CELL 9 — Fanout (Send to workers)
# ============================================================
def fanout(state: State):
    return [
        Send(
            "worker",
            {"task": task, "topic": state["topic"], "plan": state["plan"]},
        )
        for task in state["plan"].tasks
    ]

# ============================================================
# CELL 10 — Worker node
# BUG FIXES:
#   1. Plan.blog_title  → plan.blog_title   (instance, not class)
#   2. Plan.audience    → plan.audience     (instance, not class)
#   3. Removed Plan.tone (field doesn't exist on Plan model)
#   4. task.target_words now works after adding field to Task model
#   5. return {"sections": {section_md}}    (set)
#      → return {"sections": [section_md]}  (list) ✅
# ============================================================
def worker(payload: dict) -> dict:
    task: Task = payload["task"]
    topic: str = payload["topic"]
    plan: Plan = payload["plan"]          # ✅ FIX: use local `plan` variable

    bullets_text = "\n- " + "\n- ".join(task.bullets)
    section_md = model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a senior technical writer and developer advocate. Write ONE section of a technical blog post in Markdown.\n\n"
                    "Hard constraints:\n"
                    "- Follow the provided Goal and cover ALL Bullets in order (do not skip or merge bullets).\n"
                    "- Stay close to the Target words (±15%).\n"
                    "- Output ONLY the section content in Markdown (no blog title H1, no extra commentary).\n\n"
                    "Technical quality bar:\n"
                    "- Be precise and implementation-oriented (developers should be able to apply it).\n"
                    "- Prefer concrete details over abstractions: APIs, data structures, protocols, and exact terms.\n"
                    "- When relevant, include at least one of:\n"
                    "  * a small code snippet (minimal, correct, and idiomatic)\n"
                    "  * a tiny example input/output\n"
                    "  * a checklist of steps\n"
                    "  * a diagram described in text (e.g., 'Flow: A -> B -> C')\n"
                    "- Explain trade-offs briefly (performance, cost, complexity, reliability).\n"
                    "- Call out edge cases / failure modes and what to do about them.\n"
                    "- If you mention a best practice, add the 'why' in one sentence.\n\n"
                    "Markdown style:\n"
                    "- Start with a '## <Section Title>' heading.\n"
                    "- Use short paragraphs, bullet lists where helpful, and code fences for code.\n"
                    "- Avoid fluff. Avoid marketing language.\n"
                    "- If you include code, keep it focused on the bullet being addressed.\n"
                )
            ),
            HumanMessage(
                content=(
                    f"Blog: {plan.blog_title}\n"          # ✅ FIX: plan (instance)
                    f"Audience: {plan.audience}\n"         # ✅ FIX: plan (instance)
                    # ✅ FIX: Removed f"Tone: {Plan.tone}\n" — `tone` field does not exist
                    f"Topic: {topic}\n\n"
                    f"Section: {task.title}\n"
                    f"Section type: {task.section_type}\n"
                    f"Goal: {task.goal}\n"
                    f"Target words: {task.target_words}\n"  # ✅ Works after adding field to Task
                    f"Bullets:{bullets_text}\n"
                )
            ),
        ]
    ).content.strip()

    return {"sections": [section_md]}     # ✅ FIX: list [...] not set {...}

# ============================================================
# CELL 11 — Reducer node
# ============================================================
def reducer(state: State) -> dict:
    title = state["plan"].blog_title
    body = "\n\n".join(state["sections"]).strip()

    final_md = f"# {title}\n\n{body}\n"

    filename = "".join(c if c.isalnum() or c in (" ", "_", "-") else "" for c in title)
    filename = filename.strip().lower().replace(" ", "_") + ".md"
    Path(filename).write_text(final_md, encoding="utf-8")
    return {"final": final_md}

# ============================================================
# CELL 12 — Build & compile graph
# ============================================================
g = StateGraph(State)
g.add_node("orchestrator", orchestrator)
g.add_node("worker", worker)
g.add_node("reducer", reducer)

g.add_edge(START, "orchestrator")
g.add_conditional_edges("orchestrator", fanout, ["worker"])
g.add_edge("worker", "reducer")
g.add_edge("reducer", END)

app = g.compile()
app

# ============================================================
# CELL 13 — Run
# ============================================================
out = app.invoke({"topic": "Write a blog on Self Attention", "sections": []})
print(out["final"])
