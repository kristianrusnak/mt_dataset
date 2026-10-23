"""
Sixth-generation deepseek prompt: `deepseek_v5` plus one step for BGL/Thunderbird that fails criteria 4 and 5
when an abnormal sequence's explanation presents [normal]-tagged lines as faults. Everything else, including the
whole HDFS branch, is v5 unchanged, so v5 vs v6 isolates this one step. v2-v5 stay as they are.

What the v3 run showed (search split, 140 records, gold_all_relabeled.json):
  - All 5 of the judge's groundedness misses and 5 of its 7 speculation misses share one cause: the explanation
    calls [normal] lines faults ("multiple hardware fault indicators", "unresolved faults", "recurring trouble")
    while only a few lines are tagged [abnormal] (bgl d0ebbf6a 3/20, 28b6f4af 1/20, a459858d 4/20, 3b70248e
    1/20; thunderbird dcd69dc0 1/20). v3 deliberately skipped a rule for this because the labels applied it in
    only 6 of 32 BGL criterion-1 fails.
  - Conditioned on how few lines are abnormal the pattern is sharper. Over the whole 210-record gold pool, among
    abnormal BGL/Thunderbird records with a failed cause (criterion 1), the human failed groundedness in 8 of 24
    when at most 20% of the lines were tagged [abnormal], and in 0 of 27 above that. -> the step fires only when
    at most 20% of the lines are [abnormal] AND the explanation presents [normal] lines as faults.
  - The 20% cut-off was read off the same pool the judge is scored on (24 records), so it can be overfitted;
    check it on the held-out split. Precision is about one in three, which is acceptable for the metric used
    (Youden's J counts a missed fail about 7-14 times more than a false alarm because human fails are rare), but
    it is a choice: raise the bar if false alarms are costly.

The rubric text is NOT changed (it is shared with the human reviewer).
"""

from src.prompts.judge_criteria import deepseek_v4, deepseek_v5
from src.prompts.judge_criteria.common import JudgePrompt, PromptInput

PROMPT_ID = "deepseek_v6"

_OVERSOLD_STEP = (
    "Normal lines presented as faults (criteria 4 and 5). Count the lines tagged [abnormal] and the lines in "
    "the window. If the sequence is abnormal, the [abnormal] lines are a small minority (at most 20% of the "
    "lines, for example 4 of 20), and the explanation presents [normal] lines as faults, then criterion 4 "
    "FAILS (a fault is attributed to lines the labels say are routine) and criterion 5 FAILS (nothing but the "
    "classification supports treating them as faults). Presenting means calling them errors, faults, "
    "failures, \"fault indicators\", \"uncorrectable\", \"unresolved\" or \"several distinct errors\", or "
    "counting them as further evidence that something failed. Give the count and name the [normal] lines in "
    "`evidence`."
)

_NOT_A_FAIL_STEP = (
    "Not a fail: a [normal] event that sentence 1 itself calls routine or not a fault, or that appears only as "
    "background in sentence 2; [normal] lines named neutrally or called routine by the explanation; an "
    "abnormal sequence with more than 20% [abnormal] lines (step 7 does not apply, though criterion 1 may "
    "still fail). If the sequence is normal, steps 3 to 7 do not apply."
)

# v4's list minus its closing "not a fail" step, which is replaced by a version that knows about step 7.
_TAGGED_CHECK = deepseek_v4._TAGGED_CHECK[:-1] + [_OVERSOLD_STEP, _NOT_A_FAIL_STEP]

_EXAMPLES_ADDED = """\

Example I (illustrative). Sequence is abnormal; 1 of 8 lines is tagged [abnormal] (12%).
1. [normal] cache <*> parity error detected and corrected
2. [normal] cache <*> parity error detected and corrected
3. [normal] bus <*> arbitration error detected and corrected
4. [normal] cache <*> parity error detected and corrected
5. [abnormal] machine check interrupt <*>
6. [normal] bus <*> arbitration error detected and corrected
7. [normal] cache <*> parity error detected and corrected
8. [normal] bus <*> arbitration error detected and corrected
Explanation: "This log sequence is abnormal because a machine check interrupt occurs at line 5. The sequence runs through cache parity and bus arbitration errors, reaches the machine check in the middle, and then continues with more bus and cache errors. A normal window would not contain a machine check alongside this many distinct hardware fault indicators."
Correct scoring:
- Root cause: PASS. Sentence 1 names only the machine check, the single [abnormal] line.
- Sequence summary: PASS. The order is right, with the machine check at line 5 of 8.
- Contrast: FAIL. Sentence 3 offers "this many distinct hardware fault indicators" as part of what rules out a normal window, and those are the [normal] corrected-error lines.
- Groundedness: FAIL. Seven of the eight lines are tagged [normal] and say "detected and corrected", yet sentences 2 and 3 present them as "errors" and "hardware fault indicators". Count: 1 of 8 lines is [abnormal].
- Speculation: FAIL. Nothing but the classification supports treating the corrected lines as faults.

Example J (illustrative). Same sequence, different explanation: "This log sequence is abnormal because of the machine check interrupt at line 5, the only fault in the window; the cache parity and bus arbitration lines around it are routine corrected errors. The sequence runs through corrected errors, reaches the machine check at line 5, and then returns to corrected errors. A normal window would show the corrected errors without any machine check."
Correct scoring: all five criteria PASS. The [normal] lines are called routine and corrected, which is what they say, and sentence 3 offers only the machine check as the difference."""

_TAGGED_EXAMPLES = deepseek_v4._TAGGED_EXAMPLES + _EXAMPLES_ADDED


def build(inp: PromptInput) -> JudgePrompt:
    return deepseek_v5._build(inp, cot=False, tagged_check=_TAGGED_CHECK, tagged_examples=_TAGGED_EXAMPLES)


def fingerprint_extra() -> str:
    """As in v3: include the HDFS-only text (identical to v5's) so editing it invalidates cached verdicts."""
    return deepseek_v5._build(PromptInput("hdfs", ["1. x"], True, "abnormal", "e"), cot=False,
                              tagged_check=_TAGGED_CHECK, tagged_examples=_TAGGED_EXAMPLES).user
