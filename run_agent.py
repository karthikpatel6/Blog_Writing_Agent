from __future__ import annotations
import operator
from typing import TypedDict, List, Annotated
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from pydantic import BaseModel, Field
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import SystemMessage, HumanMessage

# ── Models ──────────────────────────────────────────────────────────────────

class Task(BaseModel):
    id: int
    title: str
    brief: str = Field(..., description="What to cover")

class Plan(BaseModel):
    blog_title: str
    tasks: List[Task]

class State(TypedDict):
    topic: str
    plan: Plan
    sections: Annotated[List[str], operator.add]
    final: str

# ── LLM ─────────────────────────────────────────────────────────────────────

model = ChatMistralAI(model_name="mistral-small-2506")

# ── Nodes ────────────────────────────────────────────────────────────────────

def orchestrator(state: State) -> dict:
    plan = model.with_structured_output(Plan).invoke([
        SystemMessage(content="Create a blog plan with 5-7 sections on the following topic."),
        HumanMessage(content=f"Topic: {state['topic']}"),
    ])
    print(f"Plan created: '{plan.blog_title}' with {len(plan.tasks)} sections")
    return {"plan": plan}

def fanout(state: State) -> list:
    return [
        Send("worker", {"task": task, "topic": state["topic"], "plan": state["plan"]})
        for task in state["plan"].tasks
    ]

def worker(payload: dict) -> dict:
    task  = payload["task"]
    topic = payload["topic"]
    plan  = payload["plan"]

    print(f"  Writing section: {task.title}")
    section_md = model.invoke([
        SystemMessage(content="Write one clean Markdown section."),
        HumanMessage(content=(
            f"Blog: {plan.blog_title}\n"
            f"Topic: {topic}\n\n"
            f"Section: {task.title}\n"
            f"Brief: {task.brief}\n"
            "Return only the section content in Markdown."
        )),
    ]).content.strip()
    return {"sections": [section_md]}

def reducer(state: State) -> dict:
    title = state["plan"].blog_title
    body  = "\n\n".join(state["sections"]).strip()
    final_md = f"# {title}\n\n{body}\n"

    import re
    safe_title = re.sub(r'[\\/:*?"<>|]', '', title.lower()).strip().replace(" ", "_").replace("-", "_")
    output_path = Path(__file__).parent / (safe_title + ".md")
    output_path.write_text(final_md, encoding="utf-8")
    print(f"\nBlog saved to: {output_path}")
    return {"final": final_md}

# ── Graph ────────────────────────────────────────────────────────────────────

g = StateGraph(State)
g.add_node("orchestrator", orchestrator)
g.add_node("worker", worker)
g.add_node("reducer", reducer)

g.add_edge(START, "orchestrator")
g.add_conditional_edges("orchestrator", fanout, ["worker"])
g.add_edge("worker", "reducer")
g.add_edge("reducer", END)

app = g.compile()

# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    topic = "Write a blog on MCP(model context protocol)"
    print(f"Generating blog on: '{topic}'\n")
    out = app.invoke({"topic": topic, "sections": []})
    print("\n--- Preview (first 500 chars) ---")
    print(out["final"][:500])
