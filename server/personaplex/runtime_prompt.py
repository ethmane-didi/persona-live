"""Print the PersonaPlex runtime prompt from prompts/persona.md.

Only the "## Runtime prompt" section is sent to the model; the character sheet
is reference material for humans. Usage:

    python server/personaplex/runtime_prompt.py            # default persona file
    python server/personaplex/runtime_prompt.py path/to/other.md

The LiveKit agent (phase 2) will import `load_runtime_prompt` from here too.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PERSONA_FILE = REPO_ROOT / "prompts" / "persona.md"
SECTION_HEADING = "## runtime prompt"


def load_runtime_prompt(path: Path = DEFAULT_PERSONA_FILE) -> str:
    """Return the text under '## Runtime prompt', collapsed to one line."""
    lines = path.read_text(encoding="utf-8").splitlines()
    collected: list[str] = []
    in_section = False
    for line in lines:
        if line.strip().lower() == SECTION_HEADING:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            collected.append(line.strip())
    prompt = " ".join(part for part in collected if part)
    if not prompt:
        raise ValueError(f"No '## Runtime prompt' section found in {path}")
    return prompt


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PERSONA_FILE
    print(load_runtime_prompt(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
