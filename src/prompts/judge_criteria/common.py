"""
The parts of the 5-criterion judge prompt that must be identical for every model.

Everything the judge is *scored on* lives here: the rubric (rendered from CRITERIA so the judge and the
human reviewer can never see different wording), the scoring rules, and how the input is shown. What a
model-specific file may change is only how the judge is *talked to*: system/user split, section layout,
task procedure, output guidance. That keeps a mode comparison about prompt style, not rubric content.
"""

from dataclasses import dataclass
from typing import Optional

from src.help_functions.review_criteria import CRITERIA


@dataclass(frozen=True)
class PromptInput:
    dataset_name: str
    log_lines: list  # already numbered by human_review_io.format_logs_for_review ("1. [abnormal] text" / "1. text")
    session_based: bool
    sequence_classification: str
    explanation: str


@dataclass(frozen=True)
class JudgePrompt:
    system: Optional[str]  # None = send everything as one user message
    user: str


_LABEL_NOTE_PER_LINE = "Each line carries its own ground-truth tag, [normal] or [abnormal]."
_LABEL_NOTE_SESSION = "This dataset is session-based: there are no per-line tags, only the overall classification."

# What the judge is given; a model file lays these out however suits it.
def input_facts(inp: PromptInput) -> list:
    label_note = _LABEL_NOTE_SESSION if inp.session_based else _LABEL_NOTE_PER_LINE
    return [
        f"The ordered log lines (parsed templates). {label_note}",
        "The overall classification of the sequence. Treat it as ground truth, even if you would have chosen differently.",
        "The explanation to score. It is meant to have exactly three sentences: (1) the root cause, "
        "(2) a brief summary of what the sequence shows, (3) a contrast explaining why the opposite verdict does not apply.",
    ]


BREVITY_NOTE = ("The explanation is deliberately short and does not mention every log line. Brevity and "
                "omissions are expected and are never a reason to fail a criterion.")

SCORING_RULES = [
    "Score every criterion independently. A fail on one says nothing about the others.",
    'Keep "wrong cause" (criterion 1) and "invented detail" (criterion 4) apart, exactly as the rubric defines them.',
    "Judge only what the rubric asks. Do not fail an explanation for being short, generic, or for leaving log lines out.",
    "Reasonable paraphrase and summarising are not fabrication.",
    "Do not re-classify the sequence, rewrite the explanation, or judge style.",
]


def bullets(items: list) -> str:
    return "\n".join(f"- {item}" for item in items)


def numbered(items: list) -> str:
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))


def render_rubric(heading: str = "## RUBRIC (five binary criteria)") -> str:
    lines = [heading]
    for criterion in CRITERIA:
        lines.append(f"\n### {criterion['label']}")
        lines.append(f"Checks: {criterion['question']}")
        lines.append(f"PASS: {criterion['pass']}")
        lines.append(f"FAIL: {criterion['fail']}")
    return "\n".join(lines)


def render_log_block(inp: PromptInput) -> str:
    return "\n".join(inp.log_lines)
