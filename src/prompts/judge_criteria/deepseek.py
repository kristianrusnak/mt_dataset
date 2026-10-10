"""
Prompt for deepseek-v4.1-flash.

Why it looks like this (confidence in brackets):
  - Single user message, no system prompt. DeepSeek's reasoning-model line (R1 onward) is documented to do
    best with one short zero-shot instruction and no persona; the V4.1 card is silent on prompting [medium,
    inherited from R1].
  - No "think step by step". It reasons natively when reasoning is on, and explicit CoT instructions were
    reported to hurt R1-style models. The `evidence`-before-`passed` fields in the output schema already
    give a visible justification at effort "none" [medium].
  - Task first, then data, then a one-line restatement. Instructions placed before a long input and
    repeated after it are the usual advice for long-input prompts; the log block can be long [low, from
    third-party guides, not DeepSeek].
Not controllable from the prompt: DeepSeek's thinking mode ignores `temperature` (docs), so the temperature
axis only means something at effort "none".
"""

from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, SCORING_RULES, JudgePrompt, PromptInput, bullets, input_facts, render_log_block, render_rubric,
)

PROMPT_ID = "deepseek"


def build(inp: PromptInput) -> JudgePrompt:
    user = "\n\n".join([
        f"Fact-check an AI-written explanation of why a log sequence from {inp.dataset_name} was classified as "
        "it was. Score it on the five independent pass/fail criteria below.",
        "You are given:\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric(),
        "## RULES\n" + bullets(SCORING_RULES),
        f"## INPUT\nDataset: {inp.dataset_name}\nOverall classification: {inp.sequence_classification}\n\n"
        "Log sequence:\n" + render_log_block(inp),
        "## EXPLANATION TO SCORE\n" + inp.explanation,
        "Score the five criteria now. For each, give a one-sentence justification that cites log line "
        "numbers, then the verdict.",
    ])
    return JudgePrompt(system=None, user=user)
