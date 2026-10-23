"""
Fifth-generation deepseek prompt: `deepseek_v4` (criterion-3 fix) plus three changes to the DETAIL CHECK that
make the judge as lenient as the human reviewer where the v3 run showed it was stricter. v2-v4 are left
unchanged so their cached runs stay comparable; the tagged cause check and examples are imported from v4, the
HDFS cause check and examples from v3/v2.

What the v3 run showed (search split, 140 records, gold_all_relabeled.json), and what each change answers:
  - Sequence summary (J 0.46): 31 of its 42 false alarms were "alternates" / "interleaved" / "back-and-forth"
    read as strict turn-taking ("lines 3-4 are both interrupt summaries"). Across all 210 gold records 83
    explanations use such words and 78 pass criterion 2; none of the 5 fails is about alternation itself (the
    nearest, hdfs 78aa5ed6, fails because verification is placed before the block-map updates). -> alternation
    words are a loose description of two kinds of line mixing and never fail criterion 2 on their own; a wrong
    order or position claim still does.
  - Groundedness (J 0.47): 9 of 18 false alarms read wording or hidden <*> values too literally. Standard
    technical readings ("CE" as a memory error, "no answer" as a timeout) and qualitative phrases ("over short
    spans") passed with the human. The human did fail claims that two events involve the SAME or DIFFERENT
    hidden value ("that node and port", "multiple ports/QPNs"). "Only" failed with the human only when the
    explanation itself names the other cases (thunderbird 510aa775); the three other judge fails on "only" were
    human passes. -> hidden-value rule narrowed to identity/distinctness claims, wording rule widened, "only"
    narrowed to self-contradiction. "Dominated by" and plural-count rules are unchanged.
  - Speculation (J 0.42), HDFS only: the human failed 3 of 47 HDFS records, the judge failed 14 (6 normal blocks
    with "brief", "transient", "completed"; 8 abnormal blocks with "failure state", "failure path", "error
    pattern", which restate the label). The 3 human fails were explicit mechanisms: "interrupted and retried",
    "stalled or broke", "causing the PacketResponder to terminate" / "multiple retries". -> for HDFS, only a
    named mechanism or a claim about what follows the last line fails criterion 5. The tagged datasets keep the
    v3 recovery and mechanism steps: there they caught 6 of 6 human fails on normal windows.

Not in this prompt: the "[normal] lines presented as faults" step (deepseek_v6 adds it on top).

The rubric text is NOT changed (it is shared with the human reviewer). As with earlier versions, the rules were
written after reading failures in the gold pool, so scores on it are optimistic; the held-out split is the check.
"""

from src.prompts.judge_criteria import deepseek_v2, deepseek_v3, deepseek_v4
from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, JudgePrompt, PromptInput, bullets, input_facts, numbered, render_log_block, render_rubric,
)

PROMPT_ID = "deepseek_v5"

_ORDER_STEP = (
    "Order and position (criterion 2). List every word in the explanation that places events in order or in "
    "the window: before, after, followed by, then, later, first, last, starts with, ends with / on, in the "
    "middle, precedes, culminates, leading to. Check each against the line numbers. If any one is "
    "contradicted (an event placed after something that actually comes after it, a claimed last event that "
    "is not at or next to the end, \"near the middle\" for line 18 of 20), criterion 2 FAILS, in whichever "
    "sentence it appears; name the word and the lines. An order or position mistake is scored under "
    "criterion 2 only, not also criterion 4. Not an order claim: \"alternates\", \"interleaved\", "
    "\"back-and-forth\", \"mixed with\" and \"steady\", used to say two kinds of line occur in turns or mixed "
    "through the window. Reviewers read them loosely: two or three identical lines in a row inside the pattern, "
    "or a stretch of one kind before a stretch of the other, do not fail criterion 2. They fail only if the "
    "same sentence also gives a specific order or line position that the line numbers contradict."
)

_RECOVERY_STEP_TAGGED = deepseek_v3._DETAIL_CHECK[1]
_MECHANISM_STEP_TAGGED = deepseek_v3._DETAIL_CHECK[2]

_RECOVERY_STEP_HDFS = (
    "Recovery and resolution (criterion 5, HDFS block). Fail only a claim that something was recovered from, "
    "retried, repaired or fixed, or a claim about what happens after the last line. Not a fail: soft "
    "descriptions of the events the block lists, such as \"brief\", \"isolated\", \"transient\", \"handled "
    "routinely\" or \"completed\" for a block whose storing and deleting lines are shown. Reviewers pass these "
    "on HDFS blocks."
)

_MECHANISM_STEP_HDFS = (
    "Mechanisms and cause-effect links (criterion 5, HDFS block). Fail a specific mechanism that no line "
    "states: caused, causing, led to, triggered, interrupted, retried, stalled, broke, propagated, cascaded, "
    "\"failed cleanup\", \"transfer failed\". Two lines occurring one after the other is not evidence that "
    "one caused the other. Not a fail: a generic word that only restates the abnormal classification, such "
    "as \"failure state\", \"failure path\", \"error pattern\" or \"concrete failure indicator\"; the "
    "classification itself is given, so repeating it is not speculation."
)

_COUNT_STEP = (
    "Counts and quantity words (criterion 4). Count the lines behind every quantity word: one, single, two, "
    "several, multiple, repeated, recurring, persistent, sustained, dominated by, only, all, every. "
    "\"Repeated\", \"multiple\", \"persistent\" or \"sustained\" for a single line, or \"dominated by\" for a "
    "minority of lines, FAILS criterion 4 (in sentence 2 it also fails criterion 2, as the rubric says). "
    "\"The only failure\" fails only when the explanation itself names other failures elsewhere in its three "
    "sentences; used loosely for the most notable event, it passes."
)

_WORDING_STEP = (
    "Wording of a line (criterion 4). Reading a template's abbreviation or wording in its ordinary technical "
    "sense is paraphrase, not fabrication: \"CE\" as a correctable memory error, \"detected and corrected\" as "
    "a corrected error, a line that says a node gave no answer as a \"timeout\", a memory-error line as an "
    "\"ECC\" message. A qualitative phrase about time or size (\"briefly\", \"over short spans\") is not a "
    "fabricated detail just because the durations are hidden behind <*>. It is fabrication when the "
    "explanation states the opposite of what the line says (\"uncorrectable\" for a line that says "
    "\"corrected\", \"failed\" for a line that says \"received\", \"ok\" or \"succeeded\"), or names a "
    "specific component, code or number the line does not carry."
)

_HIDDEN_STEP = (
    "Hidden values (criterion 4). A <*> hides the value, so a claim that two events involve the SAME or "
    "DIFFERENT node, port, queue or connection (\"the same connection\", \"that node and port\", \"multiple "
    "ports\", \"stays in INIT\" across lines that name no common value) cannot be known from the lines, and "
    "FAILS criterion 4. This applies only to claims of identity or distinctness, not to descriptive words."
)

_DETAIL_CHECK_TAGGED = [_ORDER_STEP, _RECOVERY_STEP_TAGGED, _MECHANISM_STEP_TAGGED, _COUNT_STEP, _WORDING_STEP,
                        _HIDDEN_STEP]
_DETAIL_CHECK_HDFS = [_ORDER_STEP, _RECOVERY_STEP_HDFS, _MECHANISM_STEP_HDFS, _COUNT_STEP, _WORDING_STEP,
                      _HIDDEN_STEP]


def _build(inp: PromptInput, cot: bool, tagged_check: list = None, tagged_examples: str = None) -> JudgePrompt:
    """tagged_check / tagged_examples let a later version (v6) add steps to the BGL/Thunderbird branch only."""
    if inp.session_based:
        check = ("## REFERENCE TABLE\nHow many HDFS blocks of each class contain each event (measured on other "
                 "blocks, not this one):\n" + deepseek_v2.hdfs_reference_table()
                 + "\n\n## CAUSE CHECK (before scoring criteria 1 and 3)\n"
                 + numbered(deepseek_v3._UNTAGGED_CHECK))
        examples = (deepseek_v2._UNTAGGED_EXAMPLES + "\n\nExample E (illustrative). "
                    + deepseek_v3._NORMAL_HDFS_EXAMPLE)
        detail = _DETAIL_CHECK_HDFS
    else:
        check = ("## CAUSE CHECK (before scoring criteria 1 and 3)\nThe tags show which lines drove the "
                 "classification, so use them to test what the explanation blames.\n"
                 + numbered(tagged_check or deepseek_v4._TAGGED_CHECK))
        examples = tagged_examples or deepseek_v4._TAGGED_EXAMPLES
        detail = _DETAIL_CHECK_TAGGED

    sections = [
        f"Fact-check an AI-written explanation of why a log sequence from {inp.dataset_name} was classified as "
        "it was. Score it on the five independent pass/fail criteria below.",
        "You are given:\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric(),
        "## RULES\n" + bullets(deepseek_v2._RULES),
        check,
        "## DETAIL CHECK (before scoring criteria 2, 4 and 5)\n" + numbered(detail),
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
