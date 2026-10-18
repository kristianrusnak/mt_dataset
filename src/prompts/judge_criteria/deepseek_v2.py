"""
Second-generation deepseek prompt, built from reading the first grid against the gold labels. Same layout
and the same rubric as `deepseek`; what is added is the guidance the judge was missing for criteria 1 and 3.

What the grid showed, and what each addition answers:
  - Tagged datasets (BGL, Thunderbird): the judge tested criterion 1 as "is the cited event real and tagged
    [abnormal]?" and passed explanations that name the real driver *together with* a [normal] line. The
    reviewer fails those (24 of 28 BGL, 15 of 18 Thunderbird records whose sentence 1 mentions a [normal]
    line). -> an explicit attribution check using the tags, with the tie-break "if the cause is ambiguous,
    fail" (the decision taken for the labels, see the validation doc).
  - Untagged dataset (HDFS): the reviewer failed explanations that blame events present in most normal blocks
    (invalidSet, Deleting block, serving exceptions). One block alone cannot show that, so the prompt carries
    a reference table of how common each event is in normal vs anomalous blocks (hdfs_profile.json, built by
    help_functions/build_hdfs_profile.py from records outside the gold pool).
  - Criteria 1 and 3 fail together (43 of 60 human criterion-1 fails are also criterion-3 fails) because
    sentence 3 usually repeats sentence 1's cause. The shared rule "score every criterion independently" is
    replaced by: work out what separates this sequence from the opposite verdict once, then test sentence 1
    and sentence 3 against it.
  - Two worked examples per dataset type (synthetic, so no gold record is used as a shot).
  - `deepseek_v2_cot` additionally asks for the `scratchpad` audit before the verdicts. Kept as a separate
    prompt because R1-style reasoning models are reported to do worse with explicit step-by-step
    instructions [medium confidence]; the grid can settle it.

The rubric text is NOT changed (it is shared with the human reviewer). Everything above is judge-side
wording, so the judge's text is no longer word-for-word the human's.
"""

import json
import os

from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, SCORING_RULES, JudgePrompt, PromptInput, bullets, input_facts, numbered, render_log_block,
    render_rubric,
)

PROMPT_ID = "deepseek_v2"

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "hdfs_profile.json")

# The shared first rule says criteria never influence each other; this prompt says how criteria 1 and 3 relate.
_RULES = [
    "Score each criterion on its own evidence. Criteria 1 and 3 are usually decided by the same fact, so work "
    "that fact out once (see CAUSE CHECK) and test sentence 1 and sentence 3 against it: a mistake that "
    "appears in both sentences fails both, and a fail on one criterion does not by itself fail another.",
    *SCORING_RULES[1:],
]

_TAGGED_CHECK = [
    "Find the discriminating evidence: the lines tagged [abnormal]. For a normal sequence there are none; the "
    "evidence is that nothing is tagged [abnormal].",
    "Take sentence 1 and list every event it names as part of the cause, including events joined to the cause "
    "with words like \"interleaved with\", \"alongside\", \"together with\", \"after\" or \"and\".",
    "Look up each listed event's tag. If the sequence is abnormal and ANY listed event is tagged [normal], "
    "criterion 1 FAILS: a wrong event is blamed together with the real one, even when the real driver is also "
    "named. If the cause is ambiguous, fail. Name the [normal] event in `evidence`.",
    "Do the same for sentence 3: if it offers a [normal]-tagged event as the signal that separates this "
    "sequence from the opposite verdict, criterion 3 FAILS.",
    "Not a fail: a [normal] event that sentence 1 itself calls routine or not a fault, or that appears only as "
    "background in sentence 2. If the sequence is normal, this check does not apply.",
]

_UNTAGGED_CHECK = [
    "Find the discriminating evidence: the events in this block that are rare in normal blocks and common in "
    "anomalous ones, using the REFERENCE TABLE. An event that most normal blocks contain does not "
    "discriminate, however alarming it sounds.",
    "Take sentence 1 and list the events it names as the cause. If every one of them is common in normal "
    "blocks (roughly 50% or more of normal blocks), criterion 1 FAILS: the cause does not distinguish this "
    "block. If at least one named event is genuinely discriminating, criterion 1 can pass even if routine "
    "events are named too.",
    "Do the same for sentence 3: if it says a normal block would not contain an event that the table shows "
    "most normal blocks do contain, that claim is false and criterion 3 FAILS.",
    "An event missing from the table, or rare in both classes, is not routine. Judge a cause built on it on "
    "whether the cited event really is in the block.",
]

_TAGGED_EXAMPLES = """\
Example A (illustrative, not from the dataset). Sequence is abnormal.
1. [normal] link card <*> status poll ok
2. [abnormal] link card <*> reset failed, code=<*>
3. [normal] link card <*> status poll ok
4. [abnormal] link card <*> reset failed, code=<*>
5. [normal] link card <*> status poll ok
Explanation: "This log sequence is abnormal because link card reset failures are interleaved with status polls, showing a recurring link problem. The sequence alternates between a poll and a failed reset on every other line. A normal sequence would not alternate failures with polls in this way."
Correct scoring:
- Root cause: FAIL. Sentence 1 puts the status polls (lines 1, 3, 5, tagged [normal]) into the cause next to the reset failures (lines 2, 4, the only [abnormal] lines).
- Sequence summary: PASS. Lines alternate poll / failed reset, as described.
- Contrast: FAIL. Sentence 3 offers the alternation with polls as the separating signal, but polls are [normal] and occur in any healthy window.
- Groundedness: PASS. Every named detail is in lines 1-5.
- Speculation: PASS. "recurring link problem" does not go beyond two repeated failures.

Example B (illustrative). Same sequence, different explanation: "This log sequence is abnormal because the link card reset fails twice (lines 2 and 4), the only fault in the window; the status polls between them are routine and not themselves a fault. The sequence alternates a poll and a failed reset on every other line. A normal sequence would contain the polls alone, with no failed reset."
Correct scoring: all five criteria PASS. Sentence 1 isolates the [abnormal] lines and calls the [normal] polls routine; sentence 3 contrasts on the failed resets, which is the real difference."""

_UNTAGGED_EXAMPLES = """\
Example C (illustrative table values). Sequence is anomalous. The table says "Deleting block" appears in 95% of normal blocks and "ask ... to replicate" in 3%. The block contains both.
Explanation: "This log sequence is abnormal because the block ends with repeated Deleting block entries after it was stored, indicating a failed cleanup. The sequence shows allocation, receipt, a replication request and then four deletions. A normal block would not end with repeated deletions."
Correct scoring:
- Root cause: FAIL. The only cause named is Deleting block, which 95% of normal blocks contain; the discriminating replication request is only mentioned in passing.
- Contrast: FAIL. "A normal block would not end with repeated deletions" is false by the table.
- Speculation: FAIL. "failed cleanup" is not shown by any line.
- Sequence summary and groundedness: PASS if the order and the count of four are right.

Example D (illustrative). Same block, explanation: "This log sequence is abnormal because the namenode asks for the block to be replicated right after the write (a request only 3% of normal blocks contain), which then precedes the usual deletions. The sequence shows allocation, receipt, the replication request and then four deletions. A normal block goes straight from storage to deletion without any replication request."
Correct scoring: root cause, contrast, groundedness and summary PASS; the cause is the discriminating event and the contrast is true by the table."""

_COT_INSTRUCTIONS = (
    "Fill `scratchpad` before the verdicts, as a short audit: (1) the discriminating evidence, (2) for each of "
    "the three sentences, the events and claims it makes with their line numbers and tags (or table shares), "
    "(3) which claims no line supports. Then write each criterion's `evidence` and `passed` from that audit."
)


def hdfs_reference_table() -> str:
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        profile = json.load(f)
    rows = [t for t in profile["templates"] if max(t["normal_share"], t["anomaly_share"]) >= 0.02]
    rows.sort(key=lambda t: (-t["normal_share"], -t["anomaly_share"]))
    lines = [f"{t['normal_share']:>4.0%} of normal blocks | {t['anomaly_share']:>4.0%} of anomalous blocks | {t['template']}"
             for t in rows]
    return "\n".join(lines)


def _untagged_section(inp: PromptInput) -> tuple[list, str]:
    """HDFS cause-check steps and worked examples. The same for both verdicts here; deepseek_v3 splits them."""
    return _UNTAGGED_CHECK, _UNTAGGED_EXAMPLES


def _build(inp: PromptInput, cot: bool, untagged_section=_untagged_section) -> JudgePrompt:
    if inp.session_based:
        untagged_check, examples = untagged_section(inp)
        check = ("## REFERENCE TABLE\nHow many HDFS blocks of each class contain each event (measured on other "
                 "blocks, not this one):\n" + hdfs_reference_table()
                 + "\n\n## CAUSE CHECK (before scoring criteria 1 and 3)\n" + numbered(untagged_check))
    else:
        check = ("## CAUSE CHECK (before scoring criteria 1 and 3)\nThe tags show which lines drove the "
                 "classification, so use them to test what the explanation blames.\n" + numbered(_TAGGED_CHECK))
        examples = _TAGGED_EXAMPLES

    sections = [
        f"Fact-check an AI-written explanation of why a log sequence from {inp.dataset_name} was classified as "
        "it was. Score it on the five independent pass/fail criteria below.",
        "You are given:\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric(),
        "## RULES\n" + bullets(_RULES),
        check,
        "## WORKED EXAMPLES\n" + examples,
        f"## INPUT\nDataset: {inp.dataset_name}\nOverall classification: {inp.sequence_classification}\n\n"
        "Log sequence:\n" + render_log_block(inp),
        "## EXPLANATION TO SCORE\n" + inp.explanation,
    ]
    if cot:
        sections.append(_COT_INSTRUCTIONS)
    sections.append("Score the five criteria now. For each, give a one-sentence justification that cites log "
                    "line numbers, then the verdict.")
    return JudgePrompt(system=None, user="\n\n".join(sections))


def build(inp: PromptInput) -> JudgePrompt:
    return _build(inp, cot=False)


def fingerprint_extra() -> str:
    """The cache fingerprint is taken from a tagged dummy input, which never reaches the HDFS-only text
    (reference table, examples). Include it so editing hdfs_profile.json invalidates cached verdicts."""
    return _build(PromptInput("hdfs", ["1. x"], True, "abnormal", "e"), cot=False).user
