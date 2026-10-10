"""
Prompt for qwen3.8-flash-next.

Same family and same documented settings as qwen3.8-27b (delimiters, numbered steps, thinking on by
default, effort xhigh/medium/low). What differs is the architecture: Flash-Next mixes Gated DeltaNet
(linear attention, which keeps a compressed running summary of the text instead of attending to every
token) with sparse attention. Hypothesis [low, architecture is documented, the weakness is general
knowledge about linear attention and not stated by Qwen]: such models can blur exact details in a long
input, so this prompt
  - puts the task and a one-line checklist of the criteria *after* the data, next to where the model
    starts writing, and
  - makes `evidence` quote a short verbatim fragment of each cited line, which forces an exact lookup
    rather than a paraphrase from memory (and makes invented details easier to see in the output).
The rubric text itself is unchanged and still comes first.
"""

from src.help_functions.review_criteria import CRITERIA
from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, SCORING_RULES, JudgePrompt, PromptInput, bullets, input_facts, render_log_block, render_rubric,
)

PROMPT_ID = "qwen_next"


def _checklist() -> str:
    return "\n".join(f"{c['label']}: {c['question']}" for c in CRITERIA)


def build(inp: PromptInput) -> JudgePrompt:
    system = ("You are a strict but fair fact-checker. You score an AI-written explanation of a log sequence "
              "against five independent pass/fail criteria.")
    user = "\n\n".join([
        "### INPUTS\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric("### RUBRIC (five binary criteria)"),
        "### RULES\n" + bullets(SCORING_RULES),
        f"### DATA\nDataset: {inp.dataset_name}\nOverall classification: {inp.sequence_classification}\n\n"
        "Log sequence:\n===\n" + render_log_block(inp) + "\n===\n\n"
        "Explanation to score:\n===\n" + inp.explanation + "\n===",
        "### TASK\nScore the explanation above on these five criteria (full PASS/FAIL wording is in the rubric):\n"
        + _checklist() + "\n\n"
        "For each criterion, `evidence` must name the relevant log line number(s) and quote a short verbatim "
        "fragment (a few words) of each. If no line backs a claim, say so in `evidence`. Then give `passed`, "
        "following from that evidence.",
    ])
    return JudgePrompt(system=system, user=user)
