"""
Judge prompt for the 5-criterion binary rubric (src/help_functions/review_criteria.py), one prompt per model.

Separate from judge_prompt.py on purpose: that one emits the older hallucination-flag vocabulary that the
existing per-dataset llm_as_judge.py scripts still depend on. This one scores the same 5 criteria the human
reviewer scored.

Layout: `common.py` holds what is identical for every model (rubric, scoring rules, input rendering); each
model has its own file holding only what is tuned to it, with the reasons in its docstring. To add a model,
add a file with PROMPT_ID and build(), register it below, and point a search_space.json mode at the id.
"""

from src.prompts.judge_criteria import deepseek, glm, laguna, minimax, qwen27b, qwen_next
from src.prompts.judge_criteria.common import JudgePrompt, PromptInput

_MODULES = [deepseek, minimax, glm, qwen27b, qwen_next, laguna]
_BUILDERS = {m.PROMPT_ID: m.build for m in _MODULES}

PROMPT_IDS = list(_BUILDERS)


def get_criteria_judge_prompt(
        prompt_id: str,
        log_lines: list,
        session_based: bool,
        sequence_classification: str,
        dataset_name: str,
        explanation: str,
) -> JudgePrompt:
    """
    log_lines is the already-numbered display from human_review_io.format_logs_for_review
    ("1. [abnormal] text" or "1. text"), so the judge reads the same thing the human did.
    """
    if prompt_id not in _BUILDERS:
        raise ValueError(f"Unknown prompt_id {prompt_id!r}; expected one of {PROMPT_IDS}")
    return _BUILDERS[prompt_id](PromptInput(
        dataset_name=dataset_name,
        log_lines=log_lines,
        session_based=session_based,
        sequence_classification=sequence_classification,
        explanation=explanation,
    ))
