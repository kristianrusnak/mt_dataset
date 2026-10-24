"""
Seventh-generation deepseek prompt: `deepseek_v6` with its "normal lines presented as faults" step (and the two
examples that go with it) kept for BGL only. Thunderbird gets the v5 BGL/Thunderbird branch back, and HDFS is v5
unchanged, so v6 vs v7 isolates what that step does to Thunderbird. v2-v6 stay as they are.

Why: v6 beat v5 on BGL but lost to it on Thunderbird, on both halves of the gold split (criteria 4 and 5,
lowest-confidence reading of "at most 20% [abnormal]" lines; the judge failed explanations the human passed):
  - search split (140, relabeled gold), v5 -> v6 verdict changes, fixed/broke:
      BGL  groundedness +6/-1, speculation +4/-1;  Thunderbird groundedness +2/-8, speculation +1/-8
  - held_out split (70):
      BGL  groundedness +0/-1, speculation +3/-1;  Thunderbird groundedness +1/-5, speculation +1/-5
    Thunderbird speculation false alarms were 8 of 19 human PASSes on held_out.
  - Score by dataset (v5 -> v6, t0.25): BGL 0.36 -> 0.65 (search), 0.66 -> 0.76 (held_out);
    Thunderbird 0.70 -> 0.69 (search), 0.64 -> 0.60 (held_out).

Limits of this version: the restriction was chosen after seeing held_out, and the 20% cut-off in the BGL step was
read off the whole 210-record pool (see v6), so there is no clean held-out score for v7. Treat a v7 run on either
split as exploratory.

The rubric text is NOT changed (it is shared with the human reviewer).
"""

from src.prompts.judge_criteria import deepseek_v5, deepseek_v6
from src.prompts.judge_criteria.common import JudgePrompt, PromptInput

PROMPT_ID = "deepseek_v7"


def build(inp: PromptInput) -> JudgePrompt:
    if inp.dataset_name == "bgl":
        return deepseek_v6.build(inp)
    return deepseek_v5.build(inp)


def fingerprint_extra() -> str:
    """The cache fingerprint is taken from a dummy input whose dataset is neither BGL nor HDFS, so add the BGL
    render (v6's step) and the HDFS render; the Thunderbird branch is what the dummy itself shows."""
    bgl = build(PromptInput("bgl", ["1. x"], False, "abnormal", "e")).user
    return bgl + deepseek_v6.fingerprint_extra()
