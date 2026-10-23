"""
Fourth-generation deepseek prompt: `deepseek_v3` with its criterion-3 rule for tagged datasets (BGL,
Thunderbird) reversed. v2 and v3 are left unchanged so their cached runs stay comparable; everything v4 keeps
from v3 (rubric, rules, HDFS check and examples, detail check and example F) is imported, not copied. Only the
tagged cause check and examples A, B and H are v4's own.

What the v3 run showed (search split, 140 records, gold_all_relabeled.json), and what changes:
  - v3 said sentence 3 fails only when NONE of the events it offers is tagged [abnormal]; naming the real
    [abnormal] event next to [normal] ones passed. It was written against labels where 7 records passed on
    that reading. On 2026-10-20 the reviewer relabeled those records to FAIL (commit ddc398f): the gold rule is
    that criterion 3 fails when sentence 3 offers ANY [normal]-tagged line as part of what rules out the
    opposite verdict, even beside the real driver. v3 therefore encoded the opposite of the gold.
  - Cost of that: on the 24 abnormal BGL/Thunderbird records whose contrast the human failed, v2 missed 6 and
    v3 missed 18 (Thunderbird 0 -> 9 of 12); 11 of the 20 v3 contrast misses quote the exception as their
    reason. The exception bought nothing: v2 had a single contrast false alarm on those records, v3 none.
  - v4 step 4 restores the "any" test, and spells out that a [normal] event named only to be dismissed as
    routine, or only as what a normal run would show, is not an offered signal (example B), while a sentence 3
    that names the real event and a [normal] one together is a fail (example H). Sentence 1 being mixed does not
    by itself fail criterion 3 (relabel rule 2): judge sentence 3's own wording.
  - Unchanged from v3 on purpose, so the effect of this one rule can be read off a single run: the
    dismissed-abnormal step, the detail check, the HDFS branch. Not addressed here: a normal sequence's
    sentence 3 calling errors "handled or expected" with no line saying so (bgl fa399ffc), and an HDFS
    sentence 3 that only restates the cause (hdfs dd517e8b).

The rubric text is NOT changed (it is shared with the human reviewer). As with v2 and v3, the rules were
written after reading failures in the gold pool, so scores on it are optimistic.
"""

from src.prompts.judge_criteria import deepseek_v2, deepseek_v3
from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, JudgePrompt, PromptInput, bullets, input_facts, numbered, render_log_block, render_rubric,
)

PROMPT_ID = "deepseek_v4"

_TAGGED_CHECK = [
    "Find the discriminating evidence: the lines tagged [abnormal]. For a normal sequence there are none; the "
    "evidence is that nothing is tagged [abnormal].",
    "Take sentence 1 and list every event it names as part of the cause, including events joined to the cause "
    "with words like \"interleaved with\", \"alongside\", \"together with\", \"after\" or \"and\".",
    "Look up each listed event's tag. If the sequence is abnormal and ANY listed event is tagged [normal], "
    "criterion 1 FAILS: a wrong event is blamed together with the real one, even when the real driver is also "
    "named. If the cause is ambiguous, fail. Name the [normal] event in `evidence`.",
    "Sentence 3, list and tag: list every event it offers as part of what separates this sequence from the "
    "opposite verdict. That includes events joined with \"and\", \"alongside\", \"together with\" or "
    "\"interleaved with\", and phrases that cover them such as \"fault indicators\", \"recurring errors\" or "
    "\"repeated failures\". Write each event's tag next to it. If the sequence is abnormal and ANY listed event "
    "is tagged [normal], criterion 3 FAILS, even when the real [abnormal] event is also named: the contrast "
    "then leans on a line that occurs in healthy windows. Name the [normal] event in `evidence`. It passes only "
    "when every listed event is tagged [abnormal]. Judge sentence 3 by its own wording: a mixed sentence 1 "
    "does not fail criterion 3, and a clean sentence 1 does not rescue a mixed sentence 3.",
    "Not an offered signal: a [normal] event that sentence 3 names only to dismiss it as routine, or only as "
    "what a normal run would show (\"the polls are routine\", \"a normal run would show the polls without a "
    "failed reset\"). Say in `evidence` that it was only dismissed.",
    "The opposite mistake: if any sentence calls an [abnormal]-tagged event routine, expected, harmless or "
    "something that \"could fit\" a normal pattern, criterion 3 FAILS (the distinction it draws is false) and "
    "criterion 5 FAILS (no line supports that claim). Name the [abnormal] lines in `evidence`.",
    "Not a fail: a [normal] event that sentence 1 itself calls routine or not a fault, or that appears only as "
    "background in sentence 2. If the sequence is normal, steps 3 to 6 do not apply.",
]

_TAGGED_EXAMPLES = """\
Example A (illustrative, not from the dataset). Sequence is abnormal.
1. [normal] link card <*> status poll ok
2. [abnormal] link card <*> reset failed, code=<*>
3. [normal] link card <*> status poll ok
4. [abnormal] link card <*> reset failed, code=<*>
5. [normal] link card <*> status poll ok
Explanation: "This log sequence is abnormal because link card reset failures are interleaved with status polls, showing a recurring link problem. The sequence alternates between a poll and a failed reset on every other line. A normal sequence would not poll the link card this often."
Correct scoring:
- Root cause: FAIL. Sentence 1 puts the status polls (lines 1, 3, 5, tagged [normal]) into the cause next to the reset failures (lines 2, 4, the only [abnormal] lines).
- Sequence summary: PASS. Lines alternate poll / failed reset, as described.
- Contrast: FAIL. The only separating signal sentence 3 offers is the polling, which is [normal] and occurs in any healthy window; the failed resets are not named.
- Groundedness: PASS. Every named detail is in lines 1-5.
- Speculation: PASS. "recurring link problem" does not go beyond two repeated failures.

Example B (illustrative). Same sequence, different explanation: "This log sequence is abnormal because the link card reset fails twice (lines 2 and 4), the only fault in the window; the status polls between them are routine and not themselves a fault. The sequence alternates a poll and a failed reset on every other line. A normal sequence would show the status polls without any failed reset between them."
Correct scoring: all five criteria PASS. Sentence 1 isolates the [abnormal] lines and calls the [normal] polls routine. Sentence 3 offers only the failed resets as the difference; the polls appear only as what a normal run would show, so they are not an offered signal.

Example H (illustrative). Same sequence, sentence 1 is clean but sentence 3 is mixed: "This log sequence is abnormal because the link card reset fails twice (lines 2 and 4), the only fault in the window; the status polls between them are routine. The sequence alternates a poll and a failed reset on every other line. A normal run would not show the failed resets together with this steady polling, so the resets and the polls rule out a healthy window."
Correct scoring:
- Contrast: FAIL. Sentence 3 offers "the resets and the polls" as what rules out a healthy window. The resets (lines 2, 4) are [abnormal], but the polls (lines 1, 3, 5) are [normal] and occur in any healthy window, so naming the real event beside them does not rescue it.
- Root cause, sequence summary, groundedness and speculation: PASS. Sentence 1 isolates the resets and calls the polls routine, the order is right, and nothing is invented. Criterion 3 fails on sentence 3 alone.

Example G (illustrative). Sequence is abnormal.
1. [abnormal] kernel terminated for reason <*>
2. [abnormal] kernel terminated for reason <*>
3. [abnormal] kernel terminated for reason <*>
4. [abnormal] kernel terminated for reason <*>
5. [abnormal] data TLB error interrupt
Explanation: "This log sequence is abnormal because of the data TLB error interrupt at line 5. The window shows four kernel terminations followed by one TLB error. The terminations alone could fit a routine shutdown, so the TLB error is what makes the window abnormal."
Correct scoring:
- Contrast: FAIL. Sentence 3 calls lines 1-4 routine, but they are tagged [abnormal].
- Speculation: FAIL. No line supports the claim that the terminations could be a routine shutdown.
- Sequence summary and groundedness: PASS; the order and the count of four are right.
- Root cause is not what this example is about."""


def _build(inp: PromptInput, cot: bool) -> JudgePrompt:
    if inp.session_based:
        check = ("## REFERENCE TABLE\nHow many HDFS blocks of each class contain each event (measured on other "
                 "blocks, not this one):\n" + deepseek_v2.hdfs_reference_table()
                 + "\n\n## CAUSE CHECK (before scoring criteria 1 and 3)\n"
                 + numbered(deepseek_v3._UNTAGGED_CHECK))
        examples = (deepseek_v2._UNTAGGED_EXAMPLES + "\n\nExample E (illustrative). "
                    + deepseek_v3._NORMAL_HDFS_EXAMPLE)
    else:
        check = ("## CAUSE CHECK (before scoring criteria 1 and 3)\nThe tags show which lines drove the "
                 "classification, so use them to test what the explanation blames.\n"
                 + numbered(_TAGGED_CHECK))
        examples = _TAGGED_EXAMPLES

    sections = [
        f"Fact-check an AI-written explanation of why a log sequence from {inp.dataset_name} was classified as "
        "it was. Score it on the five independent pass/fail criteria below.",
        "You are given:\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric(),
        "## RULES\n" + bullets(deepseek_v2._RULES),
        check,
        "## DETAIL CHECK (before scoring criteria 2, 4 and 5)\n" + numbered(deepseek_v3._DETAIL_CHECK),
        "## WORKED EXAMPLES\n" + examples + "\n\n" + deepseek_v3._DETAIL_EXAMPLE,
        f"## INPUT\nDataset: {inp.dataset_name}\nOverall classification: {inp.sequence_classification}\n\n"
        "Log sequence:\n" + render_log_block(inp),
        "## EXPLANATION TO SCORE\n" + inp.explanation,
    ]
    if cot:
        sections.append(deepseek_v2._COT_INSTRUCTIONS)
    sections.append("Score the five criteria now. For each, give a one-sentence justification that cites log "
                    "line numbers, then the verdict.")
    return JudgePrompt(system=None, user="\n\n".join(sections))


def build(inp: PromptInput) -> JudgePrompt:
    return _build(inp, cot=False)


def fingerprint_extra() -> str:
    """As in v3: the cache fingerprint is taken from a tagged dummy input, which never reaches the HDFS-only
    text, so include it to make editing any of it invalidate cached verdicts."""
    return _build(PromptInput("hdfs", ["1. x"], True, "abnormal", "e"), cot=False).user
