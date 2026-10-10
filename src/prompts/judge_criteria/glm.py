"""
Prompt for glm-5.3-flash.

Why it looks like this (confidence in brackets):
  - Role in a system message; every example in Z.ai's GLM-5.3 docs is role-based [medium].
  - Short and answer-shaped, no "think harder" padding. GLM-5.3 reasoning cannot be turned off (Z.ai docs:
    disabling is rejected), so the effort setting is the knob for thinking depth, not the prompt; guides
    for the GLM line say to state the exact answer shape and leave the thinking to the model [low-medium,
    mostly third-party].
  - One closing self-check. Z.ai pairs deeper effort with explicit verification, and the rubric has many
    near-miss traps (circular cause vs fabricated cause), so the model is asked to re-read each verdict
    against the rubric wording before answering. Worded neutrally so it does not push towards fail or pass
    [low, a hypothesis for the search to test].
Note: Z.ai recommends temperature 1.0 and effort `max` for this model; the search space tries lower
temperatures and efforts low..medium, so results may sit below its documented best.
"""

from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, SCORING_RULES, JudgePrompt, PromptInput, bullets, input_facts, render_log_block, render_rubric,
)

PROMPT_ID = "glm"


def build(inp: PromptInput) -> JudgePrompt:
    system = "\n\n".join([
        "You are a strict but fair fact-checker of log-sequence explanations. You score an explanation against "
        "five independent pass/fail criteria.",
        "Rules:\n" + bullets(SCORING_RULES),
    ])
    user = "\n\n".join([
        f"Dataset: {inp.dataset_name}\nOverall classification (ground truth): {inp.sequence_classification}",
        "Inputs:\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric(),
        "## LOG SEQUENCE\n" + render_log_block(inp),
        "## EXPLANATION TO SCORE\n" + inp.explanation,
        "## ANSWER\n"
        "For each of the five criteria write `evidence` (one or two sentences naming the log line numbers that "
        "decide it) and then `passed`.\n"
        "Before answering, re-read each verdict against the rubric's PASS and FAIL wording and change it if the "
        "evidence you wrote does not support it.",
    ])
    return JudgePrompt(system=system, user=user)
