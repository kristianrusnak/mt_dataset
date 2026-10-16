"""
`deepseek_v2` plus an instruction to fill the `scratchpad` audit before the verdicts. A separate prompt id so
the grid can compare "reasoning requested in the prompt" against "reasoning left to the model's effort
setting" -- see the deepseek_v2 docstring for why this is not simply switched on.
"""

from src.prompts.judge_criteria import deepseek_v2
from src.prompts.judge_criteria.common import JudgePrompt, PromptInput

PROMPT_ID = "deepseek_v2_cot"


def build(inp: PromptInput) -> JudgePrompt:
    return deepseek_v2._build(inp, cot=True)


def fingerprint_extra() -> str:
    return deepseek_v2._build(PromptInput("hdfs", ["1. x"], True, "abnormal", "e"), cot=True).user
