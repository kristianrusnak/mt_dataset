"""
Prompt for laguna-s-2.1.

Why it looks like this (confidence in brackets):
  - Short and direct, no persona or scaffolding. Poolside's launch post shows the model responding well to
    plain goal statements, and it is built for coding/agent work rather than for judging text [medium].
  - Told to be decisive and keep `evidence` to one sentence. Poolside lists "may overthink before making
    progress" as a known weakness [medium].
  - A literal JSON skeleton at the end. Poolside lists "may generate invalid JSON when tools expect
    complex arguments" as a known weakness, and the structured-output schema here is nested (five objects
    inside one). The skeleton also lets judge.parse_review recover the answer if the model replies in plain
    text instead of a tool call [medium]. It is built from CRITERIA_KEYS so it cannot drift from the schema.
  - No sampling or system-prompt guidance exists for this model, and thinking is off by default in its
    chat template, so effort "none" probably means no hidden reasoning at all; the visible `evidence`
    sentence is then all the reasoning there is.
"""

import json

from src.help_functions.review_criteria import CRITERIA_KEYS
from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, SCORING_RULES, JudgePrompt, PromptInput, bullets, input_facts, render_log_block, render_rubric,
)

PROMPT_ID = "laguna"


def _skeleton() -> str:
    shape = {key: {"evidence": "<one sentence citing log line numbers>", "passed": True} for key in CRITERIA_KEYS}
    return json.dumps(shape, indent=2).replace("true", "true or false")


def build(inp: PromptInput) -> JudgePrompt:
    user = "\n\n".join([
        f"Score an AI-written explanation of a {inp.dataset_name} log sequence on five independent pass/fail "
        "criteria. Be decisive: apply the rubric as written, keep each `evidence` to one sentence, and do not "
        "deliberate beyond what the rubric asks.",
        "You are given:\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric("## RUBRIC"),
        "## RULES\n" + bullets(SCORING_RULES),
        f"## INPUT\nDataset: {inp.dataset_name}\nOverall classification: {inp.sequence_classification}\n\n"
        "Log sequence:\n" + render_log_block(inp),
        "## EXPLANATION TO SCORE\n" + inp.explanation,
        "## OUTPUT\nReturn exactly this shape, one entry per criterion, `evidence` first:\n" + _skeleton(),
    ])
    return JudgePrompt(system=None, user=user)
