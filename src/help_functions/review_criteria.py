"""
Shared 5-criterion binary scoring vector used by both the human reviewer
(src/review/human/<dataset>/human_reviewer.py) and, eventually, the
llm_as_judge prompt (src/prompts/judge_prompt.py) -- see
docs/llm_judge_validation_plan.md's "Judging criteria (binary vector)"
section. Wording here is copy-pasted verbatim from that plan; if the
criteria ever change, update them here once rather than per-dataset, since
the validation plan depends on identical wording between the human
reviewer and the judge to make agreement/kappa numbers meaningful.
"""

CRITERIA = [
    {
        "key": "root_cause_correctness",
        "label": "1. Root cause correctness",
        "question": "Sentence 1 -- is the stated cause the thing that actually drove the classification?",
        "pass": "Cited cause is present in the logs and plausibly what made this sequence normal/abnormal.",
        "fail": (
            "Wrong log/event is blamed, or the \"cause\" isn't actually distinguishing (also present in "
            "normal sequences), or the \"cause\" merely restates the verdict/label itself instead of citing "
            "a concrete log-grounded event (circular, e.g. \"abnormal because the sequence is anomalous\"). "
            "Invented causes are criterion 4, not this one -- this is *wrong* (or circular/absent) cause, "
            "not *fabricated* cause."
        ),
    },
    {
        "key": "sequence_summary_correctness",
        "label": "2. Sequence summary correctness",
        "question": "Sentence 2 -- does the brief description of \"what happens across the sequence\" match what the logs show?",
        "pass": "Ordering/flow/pattern described matches the log sequence, even compressed/simplified.",
        "fail": (
            "Describes an order, timing, or pattern that contradicts the actual logs (e.g. \"repeated\" when "
            "it happens once, \"before\" when it's after)."
        ),
    },
    {
        "key": "contrast_correctness",
        "label": "3. Contrast correctness",
        "question": "Sentence 3 -- is the stated reason it's *not* the opposite label actually true and actually discriminating?",
        "pass": "The distinguishing detail is real and genuinely explains why the opposite verdict doesn't apply.",
        "fail": (
            "Contrast is missing, circular (\"not normal because it's abnormal\"), cites a distinction that "
            "doesn't actually separate the two cases, or addresses only one of several conflicting signals "
            "present in the window while ignoring other evidence that would call the verdict into question "
            "(cherry-picked contrast)."
        ),
    },
    {
        "key": "groundedness",
        "label": "4. Groundedness (no fabrication)",
        "question": (
            "Cross-cutting, all 3 sentences -- is every specific claim (event, error code, count, component, "
            "timing) traceable to a line in the given sequence?"
        ),
        "pass": "Every named detail can be pointed to in the input.",
        "fail": (
            "Any specific detail is invented, imported from \"what this kind of error usually looks like,\" "
            "or exaggerated beyond what's shown. Reasonable paraphrase is not a fail -- that's summarizing, "
            "not inventing."
        ),
    },
    {
        "key": "speculation_bounded",
        "label": "5. Speculation bounded (no overreach)",
        "question": (
            "Cross-cutting, all 3 sentences -- are causal/intent claims stated with a confidence the evidence "
            "actually supports?"
        ),
        "pass": "Claims are hedged to the level the logs justify.",
        "fail": (
            "Asserts a mechanism, intent, or downstream consequence the logs never evidence -- even if the "
            "underlying cause (criterion 1) is correct. Stating a well-evidenced cause plainly is not a fail "
            "-- confidence isn't the problem, *unsupported* confidence is."
        ),
    },
]

CRITERIA_KEYS = [c["key"] for c in CRITERIA]