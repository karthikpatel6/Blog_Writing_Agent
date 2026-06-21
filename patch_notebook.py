"""
Patches 2_Improved_agent.ipynb with all required bug fixes:
 1. Adds pip-install cell (fixes ModuleNotFoundError in Jupyter kernels)
 2. Adds `target_words` field to Task model
 3. Fixes worker(): Plan.blog_title → plan.blog_title, Plan.audience → plan.audience
 4. Removes non-existent Plan.tone line from worker()
 5. Fixes return {"sections": {section_md}} → return {"sections": [section_md]}
"""

import json, copy, re, pathlib

NB_PATH = pathlib.Path(r"d:\Blog_Writing_Agent\2_Improved_agent.ipynb")

# ── load ──────────────────────────────────────────────────────────────────────
with NB_PATH.open("r", encoding="utf-8") as f:
    nb = json.load(f)

cells = nb["cells"]

# ── helper ────────────────────────────────────────────────────────────────────
def cell_source(cell):
    """Return the cell source as a single string."""
    src = cell.get("source", [])
    return "".join(src) if isinstance(src, list) else src

def set_source(cell, text: str):
    """Write text back as a list of lines (notebook convention)."""
    lines = text.splitlines(keepends=True)
    cell["source"] = lines

def make_code_cell(source_text: str) -> dict:
    """Create a brand-new code cell."""
    lines = source_text.splitlines(keepends=True)
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": "pip_install_fix",
        "metadata": {},
        "outputs": [],
        "source": lines,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1 — Add pip-install cell at position 0 (only if not already present)
# ═══════════════════════════════════════════════════════════════════════════════
PIP_SOURCE = """\
# Fix: install packages using THIS kernel's Python (avoids ModuleNotFoundError)
import sys, subprocess
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "--quiet",
    "pydantic", "langgraph", "langchain_mistralai",
    "langchain_core", "langchain_community", "python-dotenv",
])\
"""

first_src = cell_source(cells[0])
if "subprocess" not in first_src and "sys.executable" not in first_src:
    cells.insert(0, make_code_cell(PIP_SOURCE))
    print("[OK] FIX 1: Added pip-install cell at top of notebook")
else:
    print("[SKIP] FIX 1: pip-install cell already present, skipping")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2 — Add `target_words` field to Task model cell
# ═══════════════════════════════════════════════════════════════════════════════
for cell in cells:
    src = cell_source(cell)
    if "class Task(BaseModel):" in src and "target_words" not in src:
        # Fix the bullets field description (was wrongly saying "Target word count")
        # and add target_words field after bullets block
        new_src = src.replace(
            '        description="Target word count for this section (120-450).",',
            '        description="3-5 concrete, specific, non-overlapping bullet points.",',
        )
        # Insert target_words before section_type
        new_src = new_src.replace(
            '    section_type: Literal[',
            '    target_words: int = Field(\n'
            '        ...,\n'
            '        description="Target word count for this section (120-450).",\n'
            '    )\n'
            '    section_type: Literal[',
        )
        set_source(cell, new_src)
        print("[OK] FIX 2: Added `target_words` field to Task model")
        break
else:
    print("[SKIP] FIX 2: Task model already has `target_words`, skipping")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 3, 4, 5 — Fix worker() function cell
# ═══════════════════════════════════════════════════════════════════════════════
for cell in cells:
    src = cell_source(cell)
    if "def worker(" not in src:
        continue

    original = src
    changed = []

    # FIX 3a: Plan.blog_title → plan.blog_title
    if "Plan.blog_title" in src:
        src = src.replace("Plan.blog_title", "plan.blog_title")
        changed.append("Plan.blog_title -> plan.blog_title")

    # FIX 3b: Plan.audience → plan.audience
    if "Plan.audience" in src:
        src = src.replace("Plan.audience", "plan.audience")
        changed.append("Plan.audience -> plan.audience")

    # FIX 4: Remove the non-existent Plan.tone / plan.tone line
    # Match any f-string line containing .tone
    src_lines = src.splitlines(keepends=True)
    filtered = []
    for line in src_lines:
        if re.search(r'[Pp]lan\.tone', line):
            changed.append(f"Removed non-existent tone line: {line.strip()}")
        else:
            filtered.append(line)
    src = "".join(filtered)

    # FIX 5: {section_md} (set) → [section_md] (list)
    # Match the exact pattern in the return statement
    new_src, n = re.subn(
        r'return\s*\{\s*"sections"\s*:\s*\{(section_md)\}\s*\}',
        r'return {"sections": [\1]}',
        src,
    )
    if n:
        src = new_src
        changed.append('return {"sections": {section_md}} -> return {"sections": [section_md]}')

    if src != original:
        set_source(cell, src)
        for msg in changed:
            print(f"[OK] FIX (worker): {msg}")
    else:
        print("[SKIP] worker() fixes: nothing to change")
    break

# ── save ──────────────────────────────────────────────────────────────────────
with NB_PATH.open("w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("\n[DONE] Notebook saved successfully:", NB_PATH)
