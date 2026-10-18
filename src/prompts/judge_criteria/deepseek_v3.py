"""
Third-generation deepseek prompt: `deepseek_v2` with its HDFS bug fixed and a detail check for criteria 2, 4
and 5. v2 is left unchanged so its cached runs stay comparable; everything v3 keeps from v2 (rubric, rules,
tagged cause check, examples A-D, reference table) is imported from it, not copied.

What the v2 batch showed (search split, 140 records), and what each change answers:
  - HDFS normal blocks: v2's untagged check ("every named event is common in normal blocks -> criterion 1
    fails") had no class condition, so it failed criterion 1 on all 24 normal HDFS blocks (and criterion 3
    on 12): a normal block is explained by routine events. -> separate abnormal and normal branches, as the
    tagged check already has, plus worked example E (a normal block).
  - Criteria 2, 4 and 5 did not improve over v1 (best v2 config missed 7/9, 8/13 and 14/19 human fails).
    The reviewer notes on the gold records that fail them show four recurring patterns, each turned into one
    step of the DETAIL CHECK:
      1. order/position words that the line numbers contradict ("followed by" for an earlier line, "ends
         with" X when the last line is Y, "near the middle" for line 18 of 20, "alternates" for runs of
         identical lines); reviewers score these under criterion 2 wherever they appear;
      2. recovery stories the lines do not show ("handled", "transient", "recovered", "localized", nothing
         failing "after" an event that is the last line, success lines of another subsystem read as
         recovery);
      3. mechanisms and cause-effect links the lines do not state ("interrupted and retried", "failed
         cleanup", "stalled", X "leading to" Y);
      4. counts and quantity words that are wrong ("repeated" or "persistent" for one line, "multiple
         retries" with none, "dominated by" a minority, "the only failure" when there are others).
    Worked example F shows the four steps on one synthetic sequence.

The rubric text is NOT changed (it is shared with the human reviewer). As with v2, the rules were written
after reading failures in the gold pool, so scores on it are optimistic.
"""

from src.prompts.judge_criteria import deepseek_v2
from src.prompts.judge_criteria.common import (
    BREVITY_NOTE, JudgePrompt, PromptInput, bullets, input_facts, numbered, render_log_block, render_rubric,
)

PROMPT_ID = "deepseek_v3"

_UNTAGGED_CHECK = [
    "Find the discriminating evidence: the events in this block that are rare in normal blocks and common in "
    "anomalous ones, using the REFERENCE TABLE. An event that most normal blocks contain does not "
    "discriminate, however alarming it sounds. For a normal block the evidence is that it contains none of "
    "those anomaly-typical events.",
    "If the block is classified abnormal: take sentence 1 and list the events it names as the cause. If every "
    "one of them is common in normal blocks (roughly 50% or more of normal blocks), criterion 1 FAILS: the cause "
    "does not distinguish this block. If at least one named event is genuinely discriminating, criterion 1 can "
    "pass even if routine events are named too.",
    "If the block is classified abnormal, do the same for sentence 3: if it says a normal block would not "
    "contain an event that the table shows most normal blocks do contain, that claim is false and criterion 3 "
    "FAILS.",
    "If the block is classified normal: its cause IS routine block handling, so a sentence 1 built from events "
    "common in normal blocks is correct and passes. Criterion 1 fails only if it names an event that is not in "
    "the block, or calls an event routine that the table shows is rare in normal blocks and common in anomalous "
    "ones. Sentence 3 passes when it truthfully says the block lacks anomaly-typical events, has no error "
    "lines, or that its alarming-looking events are common in normal blocks; it fails only if such a statement "
    "is false for this block or by the table.",
    "An event missing from the table, or rare in both classes, is not routine. Judge a cause built on it on "
    "whether the cited event really is in the block.",
]

_DETAIL_CHECK = [
    "Order and position (criterion 2). List every word in the explanation that places events in order or in "
    "the window: before, after, followed by, then, later, first, last, starts with, ends with / on, in the "
    "middle, alternates, interleaved, precedes, culminates, leading to. Check each against the line numbers. "
    "If any one is contradicted, criterion 2 FAILS, in whichever sentence it appears; name the word and the "
    "lines. \"Alternates\" or \"interleaved\" needs the event types to take turns; runs of the same line are "
    "not alternation. An order or position mistake is scored under criterion 2 only, not also criterion 4.",
    "Recovery and resolution (criterion 5). A claim that something was handled, recovered, corrected, "
    "resolved, transient, localized, bounded, or returned to normal needs a line that says so, for the same "
    "component, after the fault. Success lines of a different component or subsystem do not count. Nothing "
    "can be known about what happens after the last line, so \"no further failure after X\" when X is at or "
    "near the end is unsupported. Otherwise criterion 5 FAILS.",
    "Mechanisms and cause-effect links (criterion 5). A claim that one event caused, led to, interrupted, "
    "retried, stalled, broke or failed to clean up something needs a line that states it. Two lines occurring "
    "one after the other is not evidence that one caused the other, and an effect cannot be caused by a line "
    "that comes after it. Otherwise criterion 5 FAILS.",
    "Counts and quantity words (criterion 4). Count the lines behind every quantity word: one, single, two, "
    "several, multiple, repeated, recurring, persistent, sustained, dominated by, only, all, every. "
    "\"Repeated\", \"multiple\", \"persistent\" or \"sustained\" for a single line, \"dominated by\" for a "
    "minority of lines, or \"the only failure\" when there are others, FAILS criterion 4 (in sentence 2 it "
    "also fails criterion 2, as the rubric says).",
]

_DETAIL_EXAMPLE = """\
Example F (illustrative, not from the dataset). Sequence is normal.
1. disk <*> latency warning
2. disk <*> latency warning
3. fan <*> speed restored to normal
4. disk <*> latency warning
5. service <*> started successfully
6. disk <*> latency warning
Explanation: "This log sequence is normal because the disk latency warnings are transient and were handled, as the subsystem recovered. The sequence begins with a latency warning that is followed by a return to normal, and ends with the service starting. The repeated warnings never escalate into a persistent fault after recovery, so nothing points to an abnormal window."
Correct scoring:
- Sequence summary: FAIL. The window ends with a latency warning (line 6), not the service start (line 5); "followed by a return to normal" is only true for the fan, not the disk.
- Speculation: FAIL. Nothing says the disk warnings were handled or recovered: line 3 is a different component (fan) and line 5 is a service start, so "transient", "handled" and "recovered" are not shown, and nothing can be known after line 6.
- Groundedness: PASS. Four warnings is "repeated", and every named event is in lines 1-6.
- Root cause and contrast are not what this example is about."""


_NORMAL_HDFS_EXAMPLE = (
    "Sequence is normal. The block shows allocation, three Receiving block, three PacketResponder terminating, "
    "three addStoredBlock, one \"Got exception while serving\" (78% of normal blocks) and then Deleting block "
    "entries; no replication request.\n"
    "Explanation: \"This log sequence is normal because it shows routine block handling: the block is "
    "allocated, received by three nodes, stored and later deleted. The sequence moves from allocation and "
    "receipt through the block-map updates to one serving exception and the final deletions. The single "
    "serving exception does not make it abnormal, because such exceptions appear in most normal blocks and "
    "nothing anomaly-typical, such as a replication request, occurs.\"\n"
    "Correct scoring: all five criteria PASS. For a normal block, routine events are the right cause; "
    "sentence 3 is true by the table and by the block."
)


def _build(inp: PromptInput, cot: bool) -> JudgePrompt:
    if inp.session_based:
        check = ("## REFERENCE TABLE\nHow many HDFS blocks of each class contain each event (measured on other "
                 "blocks, not this one):\n" + deepseek_v2.hdfs_reference_table()
                 + "\n\n## CAUSE CHECK (before scoring criteria 1 and 3)\n" + numbered(_UNTAGGED_CHECK))
        examples = deepseek_v2._UNTAGGED_EXAMPLES + "\n\nExample E (illustrative). " + _NORMAL_HDFS_EXAMPLE
    else:
        check = ("## CAUSE CHECK (before scoring criteria 1 and 3)\nThe tags show which lines drove the "
                 "classification, so use them to test what the explanation blames.\n"
                 + numbered(deepseek_v2._TAGGED_CHECK))
        examples = deepseek_v2._TAGGED_EXAMPLES

    sections = [
        f"Fact-check an AI-written explanation of why a log sequence from {inp.dataset_name} was classified as "
        "it was. Score it on the five independent pass/fail criteria below.",
        "You are given:\n" + bullets(input_facts(inp)) + "\n\n" + BREVITY_NOTE,
        render_rubric(),
        "## RULES\n" + bullets(deepseek_v2._RULES),
        check,
        "## DETAIL CHECK (before scoring criteria 2, 4 and 5)\n" + numbered(_DETAIL_CHECK),
        "## WORKED EXAMPLES\n" + examples + "\n\n" + _DETAIL_EXAMPLE,
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
    """The cache fingerprint is taken from a tagged dummy input, which never reaches the HDFS-only text
    (reference table, untagged check, examples C-E). Include it so editing any of it invalidates cached verdicts."""
    return _build(PromptInput("hdfs", ["1. x"], True, "abnormal", "e"), cot=False).user
