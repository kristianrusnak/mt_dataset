"""
Third-generation deepseek prompt: `deepseek_v2` with its HDFS bug fixed and a detail check for criteria 2, 4
and 5. v2 is left unchanged so its cached runs stay comparable; everything v3 keeps from v2 (rubric, rules,
HDFS examples C-D, reference table) is imported from it, not copied. The tagged cause check and examples A-B
are v3's own, because two of their rules changed (see below).

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
  - Tagged datasets (BGL, Thunderbird), criterion 3: v2 failed the contrast whenever sentence 3 mentioned any
    [normal] line; reviewers pass it when sentence 3 also names the real [abnormal] event (7 records failed
    in 4/4 v2 runs). -> sentence 3 fails only when its separating signal is [normal] lines alone. Example A
    and B are rewritten to show the difference.
  - Tagged datasets, the opposite mistake: sentence 3 calling [abnormal]-tagged lines routine ("the
    terminations alone could fit a routine shutdown", 19 [abnormal] lines). v2 never checked it and passed
    both such gold records on every criterion. -> criteria 3 and 5 fail; example G.
  - Criterion 4, too literal (2 records): the standard reading of a template's wording ("CE" as a
    correctable error) is paraphrase. Narrow counterpart: describing a line as the opposite of its own
    wording ("uncorrectable" for "corrected") fails criterion 4. A wider rule ("a [normal] line called a
    fault fails 4/5") was not added: the labels apply it in only 6 of 32 BGL criterion-1 fails.

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

_TAGGED_CHECK = [
    "Find the discriminating evidence: the lines tagged [abnormal]. For a normal sequence there are none; the "
    "evidence is that nothing is tagged [abnormal].",
    "Take sentence 1 and list every event it names as part of the cause, including events joined to the cause "
    "with words like \"interleaved with\", \"alongside\", \"together with\", \"after\" or \"and\".",
    "Look up each listed event's tag. If the sequence is abnormal and ANY listed event is tagged [normal], "
    "criterion 1 FAILS: a wrong event is blamed together with the real one, even when the real driver is also "
    "named. If the cause is ambiguous, fail. Name the [normal] event in `evidence`.",
    "Sentence 3: list the events it offers as the signal that separates this sequence from the opposite "
    "verdict. If the sequence is abnormal and NONE of them is tagged [abnormal] (it relies on [normal] events "
    "only), criterion 3 FAILS. If it names the real [abnormal] event, mentioning [normal] events next to it "
    "does not fail criterion 3.",
    "The opposite mistake: if any sentence calls an [abnormal]-tagged event routine, expected, harmless or "
    "something that \"could fit\" a normal pattern, criterion 3 FAILS (the distinction it draws is false) and "
    "criterion 5 FAILS (no line supports that claim). Name the [abnormal] lines in `evidence`.",
    "Not a fail: a [normal] event that sentence 1 itself calls routine or not a fault, or that appears only as "
    "background in sentence 2. If the sequence is normal, steps 3 to 5 do not apply.",
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
Correct scoring: all five criteria PASS. Sentence 1 isolates the [abnormal] lines and calls the [normal] polls routine; sentence 3 names the failed resets as the difference, and mentioning the polls next to them does not fail it.

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
    "Wording of a line (criterion 4). Reading a template's abbreviation or wording in its standard technical "
    "sense is paraphrase, not fabrication (\"CE\" as a correctable error, \"detected and corrected\" as a "
    "corrected error). It is fabrication when the explanation states the opposite of what the line says "
    "(\"uncorrectable\" for a line that says \"corrected\", \"failed\" for a line that says \"received\", "
    "\"ok\" or \"succeeded\"), or adds a fact the line does not carry, such as a value hidden behind <*>.",
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
                 + numbered(_TAGGED_CHECK))
        examples = _TAGGED_EXAMPLES

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
