"""
Judge prompt for the 5-criterion binary rubric (src/help_functions/review_criteria.py), one prompt per model.

Separate from judge_prompt.py on purpose: that one emits the older hallucination-flag vocabulary that the
existing per-dataset llm_as_judge.py scripts still depend on. This one scores the same 5 criteria the human
reviewer scored.

Layout: `common.py` holds what is identical for every model (rubric, scoring rules, input rendering); each
model has its own file holding only what is tuned to it, with the reasons in its docstring. To add a model,
add a file with PROMPT_ID and build(), register it below, and point a search_space.json mode at the id.
"""

from src.prompts.judge_criteria import (
    deepseek, deepseek_v2, deepseek_v2_cot, deepseek_v3, deepseek_v4, deepseek_v5, deepseek_v6, glm, laguna, minimax, qwen27b, qwen_next,
)
from src.prompts.judge_criteria.common import JudgePrompt, PromptInput

_MODULES = [deepseek, minimax, glm, qwen27b, qwen_next, laguna, deepseek_v2, deepseek_v2_cot, deepseek_v3, deepseek_v4, deepseek_v5, deepseek_v6]
_BUILDERS = {m.PROMPT_ID: m.build for m in _MODULES}

PROMPT_IDS = list(_BUILDERS)


def fingerprint_extra(prompt_id: str) -> str:
    """Text a prompt wants included in its cache fingerprint beyond the tagged dummy render (e.g. an HDFS-only
    section). Prompts that don't define it return "", which leaves their existing fingerprints unchanged."""
    module = next(m for m in _MODULES if m.PROMPT_ID == prompt_id)
    return module.fingerprint_extra() if hasattr(module, "fingerprint_extra") else ""


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
