"""
Prompt for qwen3.8-27b.

Why it looks like this (confidence in brackets):
  - Alibaba's prompting guidance for Qwen: break the task into explicit numbered steps, separate blocks
    with rarely-occurring delimiters (### / ===), and show the output format. The model card also stresses
    standardising the output format [medium; the delimiter/step/example advice is from Qwen's docs, the
    3.8 card itself only covers sampling and effort].
  - Data fenced with === lines. The explanation under review is model-written text and could contain
    instruction-like phrases; fences keep "what to do" apart from "what to score" [medium].
  - A format-only example with placeholder content, so the shape is shown without handing over a verdict
    to copy [medium].
  - System message holds the role only. Thinking is on by default and the effort setting controls it, so
    the prompt does not ask for extra reasoning.
Note: Qwen recommends temperature 1.0 (thinking) / 0.7 (non-thinking) with top_k 20; the proxy decides
top_k, so only temperature is searched.
"""

from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, SCORING_RULES, JudgePrompt, PromptInput, bullets, input_facts, numbered, render_log_block,
    render_rubric,
)

PROMPT_ID = "qwen27b"

_STEPS = [
    "Read the explanation and note each specific claim it makes.",
    "For criterion 1 to 5 in order: find the log line numbers that support or contradict the claims that "
    "criterion covers.",
    "Write those line numbers and what they show in `evidence`.",
    "Set `passed` using the rubric's PASS and FAIL wording and your evidence.",
]

_FORMAT_EXAMPLE = """\
Shape of one criterion's answer (placeholder text, not a real verdict):
evidence: "Line 4 shows <what the line says>, which <matches / contradicts> the claim '<quote from the explanation>'."
passed: true or false"""


def build(inp: PromptInput) -> JudgePrompt:
    system = ("You are a strict but fair fact-checker. You score an AI-written explanation of a log sequence "
              "against five independent pass/fail criteria.")
    user = "\n\n".join([
        "### TASK\nScore the explanation between the === fences on five criteria, using the log sequence "
        f"from {inp.dataset_name} and its classification.",
        "### INPUTS\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric("### RUBRIC (five binary criteria)"),
        "### RULES\n" + bullets(SCORING_RULES),
        "### STEPS\n" + numbered(_STEPS),
        "### FORMAT\n" + _FORMAT_EXAMPLE,
        f"### DATA\nDataset: {inp.dataset_name}\nOverall classification: {inp.sequence_classification}\n\n"
        "Log sequence:\n===\n" + render_log_block(inp) + "\n===\n\n"
        "Explanation to score:\n===\n" + inp.explanation + "\n===",
    ])
    return JudgePrompt(system=system, user=user)
