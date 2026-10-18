"""
`deepseek_v2` with the HDFS cause check split by verdict. Everything for BGL/Thunderbird is unchanged.

What the v2 grid showed (6 runs, gold_all_relabeled.json): the v2 HDFS check says criterion 1 fails if every
event sentence 1 names is common in normal blocks. That is right for an anomalous block, but for a normal block
the correct cause *is* the routine lifecycle, so the rule fails it by construction. The judge failed criterion 1
on 33.5 of the 35 normal HDFS blocks (human: 0 fails) and criterion 3 on 18.3 of 35 (human: 0 fails), reasoning
"these events are common in both classes, so they do not distinguish this normal sequence".
  -> for a normal block, the evidence is what the block lacks (the rare-in-normal events), routine events are a
     valid cause, and criterion 3 is judged on whether its claim is true. Anomalous blocks keep v2's check.
  -> one worked example for a normal block; anomalous blocks keep v2's examples C and D.

Only the verdict-relevant half is rendered, so a normal block never sees the anomalous rule and vice versa.
"""

from src.prompts.judge_criteria import deepseek_v2
from src.prompts.judge_criteria.common import JudgePrompt, PromptInput

PROMPT_ID = "deepseek_v3"

_UNTAGGED_CHECK_NORMAL = [
    "This block is normal. The evidence for a normal verdict is what the block lacks: none of the events that "
    "are rare in normal blocks and common in anomalous ones (REFERENCE TABLE rows found in only a few percent "
    "of normal blocks). Routine events that most normal blocks contain are the correct basis for a normal "
    "verdict, even though anomalous blocks contain them too.",
    "Criterion 1 PASSES when sentence 1 describes the block's routine lifecycle (allocation, receipt, storage "
    "updates, PacketResponder termination, serving, verification, invalidSet/deletion) with events that are "
    "really in the block. Do NOT fail it because the cited events are also common in anomalous blocks: for a "
    "normal verdict that is expected. It FAILS only if the cause rests on an event that is not in the block, "
    "or merely restates the verdict.",
    "Criterion 3 is judged on whether its claim is true. \"No error, failure or retry lines\" passes if no "
    "such line is in the block. Saying the serving exceptions are not a fault because successful serving or "
    "verification follows passes if those lines really follow: \"Got exception while serving\" is in most "
    "normal blocks. It FAILS if it denies an event that is in the block (e.g. \"no exceptions\" when a serving "
    "exception is there), or names as the abnormal sign an event that this block itself contains.",
]

_UNTAGGED_EXAMPLE_NORMAL = """\
Example E (illustrative). Sequence is normal. The block shows allocateBlock, three Receiving block lines, three PacketResponder terminations with Received block, three addStoredBlock updates, two "Got exception while serving" lines followed by a Served block and Verification succeeded, then three invalidSet entries and three Deleting block lines.
Explanation: "This log sequence is normal because the block goes through a routine write, storage and cleanup lifecycle: it is allocated, received and stored on three datanodes, verified, and later deleted. The sequence moves from allocation and receipt through addStoredBlock updates, two serving exceptions followed by a successful serve and verification, and ends with invalidSet and Deleting block entries. The serving exceptions do not make it abnormal because serving succeeds right after them and nothing in the block points to a failed write or replication problem."
Correct scoring: all five criteria PASS. A normal cause is allowed to consist of routine events; sentence 3 is true, since the exceptions are followed by a Served block and Verification succeeded, and no replication request or other rare event is present."""


def _untagged_section(inp: PromptInput) -> tuple[list, str]:
    if inp.sequence_classification == "normal":
        return _UNTAGGED_CHECK_NORMAL, _UNTAGGED_EXAMPLE_NORMAL
    return deepseek_v2._UNTAGGED_CHECK, deepseek_v2._UNTAGGED_EXAMPLES


def build(inp: PromptInput) -> JudgePrompt:
    return deepseek_v2._build(inp, cot=False, untagged_section=_untagged_section)


def fingerprint_extra() -> str:
    """Both HDFS halves, since the cache fingerprint's tagged dummy input never reaches either."""
    return "\n".join(
        deepseek_v2._build(PromptInput("hdfs", ["1. x"], True, verdict, "e"), cot=False,
                           untagged_section=_untagged_section).user
        for verdict in ("abnormal", "normal")
    )
