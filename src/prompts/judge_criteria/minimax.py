"""
Prompt for minimax-m2.5.

Why it looks like this (confidence in brackets):
  - Role and rules in a system message. The model ships with a default system prompt ("You are a helpful
    assistant. Your name is MiniMax-M2.5 ...") and was trained on agent-style, system-prompted setups
    [medium].
  - A numbered procedure in the user message. The model card describes a planning habit (it breaks a
    requirement into steps before acting), so an explicit step list matches what it does anyway instead of
    fighting it [medium].
  - Nothing about "thinking". M2.5 always reasons (interleaved thinking, inline <think> blocks unless the
    API splits them out) and the proxy lists no `reasoning_effort` for it; judge.parse_review already
    strips <think> blocks from a text fallback [high].
"""

from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, SCORING_RULES, JudgePrompt, PromptInput, bullets, input_facts, numbered, render_log_block,
    render_rubric,
)

PROMPT_ID = "minimax"

_PROCEDURE = [
    "Read the explanation one sentence at a time and note each specific claim it makes (an event, error, "
    "component, count, ordering or cause).",
    "Take the criteria in order. For each one, find the log line numbers that support or contradict the "
    "claims it covers, and write them in `evidence` together with what those lines show.",
    "Decide `passed` from that evidence alone, using the rubric's PASS and FAIL wording.",
    "Return the structured result. Do not describe these steps in your answer.",
]


def build(inp: PromptInput) -> JudgePrompt:
    system = "\n\n".join([
        f"You are a strict but fair fact-checker. An AI wrote a short explanation of why a log sequence from "
        f"{inp.dataset_name} was classified the way it was; you score that explanation against five independent "
        "pass/fail criteria.",
        "## RULES\n" + bullets(SCORING_RULES),
    ])
    user = "\n\n".join([
        "## CONTEXT\nYou are given:\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric(),
        f"## INPUT\nDataset: {inp.dataset_name}\nOverall classification: {inp.sequence_classification}\n\n"
        "Log sequence:\n" + render_log_block(inp),
        "## EXPLANATION TO SCORE\n" + inp.explanation,
        "## PROCEDURE\n" + numbered(_PROCEDURE),
    ])
    return JudgePrompt(system=system, user=user)
