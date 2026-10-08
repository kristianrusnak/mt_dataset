"""
Judge prompt for the 5-criterion binary rubric (src/help_functions/review_criteria.py).

Separate from judge_prompt.py on purpose: that one emits the older hallucination-flag vocabulary
that the existing per-dataset llm_as_judge.py scripts still depend on. This one scores the same
5 criteria the human reviewer scored, with the PASS/FAIL text rendered from CRITERIA so the judge
and the human can never be given different wording.

The judge sees what the human saw (see human_review_io.format_logs_for_review): the parsed log
templates, and for BGL/Thunderbird each line's ground-truth normal/abnormal tag.

Three prompt variants exist so the prompt can be one dimension of the config search. They differ
only in how the judge is told to work, never in the rubric itself:
  - direct:         score each criterion with a one-sentence justification.
  - evidence_first: for each criterion, cite log line numbers before giving the verdict.
  - claim_audit:    first list every specific claim in the explanation and the log line backing it,
                    then score. Also tells the judge that an unbacked claim fails.
"""

from src.help_functions.review_criteria import CRITERIA

PROMPT_IDS = ["direct", "evidence_first", "claim_audit"]

_PERSONA = """\
## PERSONA
You are a strict but fair fact-checker. An AI wrote a short explanation of why a log sequence from \
**{dataset_name}** was classified the way it was. You score that explanation against five independent \
pass/fail criteria. You do not re-classify the sequence, you do not rewrite the explanation, and you do \
not judge style."""

_CONTEXT = """\
## CONTEXT
You are given:
1. The ordered log lines (parsed templates).{label_note}
2. The overall classification of the sequence. Treat it as ground truth, even if you would have chosen differently.
3. The explanation to score. It is meant to have exactly three sentences: (1) the root cause, \
(2) a brief summary of what the sequence shows, (3) a contrast explaining why the opposite verdict does not apply.

The explanation is deliberately short and does not mention every log line. Brevity and omissions are expected \
and are never a reason to fail a criterion."""

_LABEL_NOTE_PER_LINE = " Each line carries its own ground-truth tag, [normal] or [abnormal]."
_LABEL_NOTE_SESSION = " This dataset is session-based: there are no per-line tags, only the overall classification."

_RULES = """\
## RULES
- Score every criterion independently. A fail on one says nothing about the others.
- Keep "wrong cause" (criterion 1) and "invented detail" (criterion 4) apart, exactly as the rubric defines them.
- Judge only what the rubric asks. Do not fail an explanation for being short, generic, or for leaving log lines out.
- Reasonable paraphrase and summarising are not fabrication."""

_VARIANT_INSTRUCTIONS = {
    "direct": """\
## TASK
Score the five criteria. For each one give a one-sentence justification, then the verdict.""",
    "evidence_first": """\
## TASK
Score the five criteria. For each one, first write the evidence: name the log line numbers that support or \
contradict the relevant part of the explanation, and say what they show. Only then give the verdict, and \
make it follow from that evidence.""",
    "claim_audit": """\
## TASK
Work in two stages.
Stage 1 (scratchpad): go through the explanation sentence by sentence. For every specific claim (an event, \
error, component, count, ordering, or cause) write the claim and the log line number(s) that back it, or \
write NONE if no line backs it.
Stage 2: score the five criteria using the scratchpad. A specific claim marked NONE cannot pass criterion 4. \
A cause, mechanism or consequence the logs never evidence cannot pass criterion 5. For each criterion write a \
one-sentence justification, then the verdict.""",
}


def _render_rubric() -> str:
    lines = ["## RUBRIC (five binary criteria)"]
    for criterion in CRITERIA:
        lines.append(f"\n### {criterion['label']}")
        lines.append(f"Checks: {criterion['question']}")
        lines.append(f"PASS: {criterion['pass']}")
        lines.append(f"FAIL: {criterion['fail']}")
    return "\n".join(lines)


def get_criteria_judge_prompt(
        prompt_id: str,
        log_lines: list,
        session_based: bool,
        sequence_classification: str,
        dataset_name: str,
        explanation: str,
) -> str:
    """
    log_lines is the already-numbered display from human_review_io.format_logs_for_review
    ("1. [abnormal] text" or "1. text"), so the judge reads the same thing the human did.
    """
    if prompt_id not in _VARIANT_INSTRUCTIONS:
        raise ValueError(f"Unknown prompt_id {prompt_id!r}; expected one of {PROMPT_IDS}")

    label_note = _LABEL_NOTE_SESSION if session_based else _LABEL_NOTE_PER_LINE

    sections = [
        _PERSONA.format(dataset_name=dataset_name),
        _CONTEXT.format(label_note=label_note),
        _render_rubric(),
        _RULES,
        _VARIANT_INSTRUCTIONS[prompt_id],
        "## INPUT\n"
        f"Dataset: {dataset_name}\n"
        f"Overall classification: {sequence_classification}\n\n"
        "Log sequence:\n" + "\n".join(log_lines),
        "## EXPLANATION TO SCORE\n" + explanation,
    ]
    return "\n\n".join(sections)
