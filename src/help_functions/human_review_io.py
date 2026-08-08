"""
Shared interactive-review helpers for src/review/human/<dataset>/human_reviewer.py.
Kept here (rather than duplicated per-dataset) so the 5-criterion prompt text and
scoring loop can't drift between BGL/Thunderbird/HDFS -- see
docs/llm_judge_validation_plan.md's "Judging criteria (binary vector)" section.
"""

from src.help_functions.review_criteria import CRITERIA


def get_user_input(prompt: str, default_value=None) -> str:
    """Prompts for free-text input with an optional default."""
    if default_value:
        return input(f"{prompt} [default: {default_value}]: ") or default_value
    return input(f"{prompt}: ")


def format_logs_for_review(parsed_logs: list, raw_logs: list = None, session_based: bool = False) -> list:
    """
    Builds the per-line display shown to the human reviewer.

    For non-session-based datasets (BGL, Thunderbird), each parsed log line is
    tagged with its own ground-truth normal/abnormal label -- derived the same
    way the judge prompt derives it (raw line's leading column is "-" for
    normal, anything else for abnormal) -- so the reviewer can see exactly
    which line(s) actually drove the sequence's classification instead of
    having to infer it from the raw text alone.

    HDFS is session-based: there is no per-line ground truth, only the
    block-level label (matches session_based=True in judge_prompt.py), so
    lines are shown enumerated without a per-line tag.
    """
    if session_based or not raw_logs:
        return [f"{i}. {log}" for i, log in enumerate(parsed_logs, start=1)]

    result = []
    for i, (parsed_log, raw_log) in enumerate(zip(parsed_logs, raw_logs), start=1):
        per_log_label = "normal" if raw_log.startswith("-") else "abnormal"
        result.append(f"{i}. [{per_log_label}] {parsed_log}")
    return result


def prompt_pass_fail(prompt_text: str, default: bool = None) -> bool:
    """Prompts until the reviewer enters p(ass) or f(ail); returns a bool."""
    default_str = None
    if default is True:
        default_str = "p"
    elif default is False:
        default_str = "f"

    while True:
        suffix = f" [p/f, default: {default_str}]" if default_str else " [p/f]"
        raw = input(f"{prompt_text}{suffix}: ").strip().lower()
        if not raw and default_str:
            raw = default_str
        if raw in ("p", "pass"):
            return True
        if raw in ("f", "fail"):
            return False
        print("Please enter 'p' (pass) or 'f' (fail).")


def prompt_criteria_scores(existing_scores: dict = None) -> dict:
    """
    Walks the reviewer through all 5 criteria, printing the same PASS/FAIL
    definitions used in the validation plan, and returns {criterion_key: bool}.
    """
    existing_scores = existing_scores or {}
    scores = {}
    for criterion in CRITERIA:
        print(f"\n--- {criterion['label']} ---")
        print(criterion["question"])
        print(f"  PASS: {criterion['pass']}")
        print(f"  FAIL: {criterion['fail']}")
        scores[criterion["key"]] = prompt_pass_fail(
            f"Score for '{criterion['label']}'",
            default=existing_scores.get(criterion["key"]),
        )
    return scores


def failed_criteria_flags(criteria_scores: dict) -> list:
    """Derives a hallucination_flags-shaped list from the criteria vector: failed
    criterion keys, or ["valid"] if every criterion passed -- kept so downstream
    code that already reads hallucination_flags/verification_status stays working."""
    failed = [key for key, passed in criteria_scores.items() if not passed]
    return failed if failed else ["valid"]