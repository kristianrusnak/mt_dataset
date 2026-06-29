import uuid

from typing import Optional
from datetime import datetime

# ============================================================
# PLACEHOLDER: JSON OBJECT STRUCTURE FOR A SINGLE WINDOW
# ============================================================
def build_window_object(
        parsed_lines: list,
        raw_lines: list,
        classification: str,
        source_dataset: str,
        source_file: str,
        system_component: str,
        explanation: str = "",
        start_timestamp: Optional[str] = None,
        end_timestamp: Optional[str] = None,
        log_template_id: Optional[str] = None,
        session_id: Optional[str] = None,
        augmentation_method: Optional[str] = None,
        augmentation_model: Optional[str] = None,
        augmentation_model_version: Optional[str] = None,
        augmentation_prompt_id: Optional[str] = None,
        model: Optional[str] = None,
        generation_timestamp: Optional[str] = None,
        prompt_template_id: Optional[str] = None,
        generation_params: Optional[dict] = None,
        verification_status: Optional[str] = None,
        verification_method: Optional[str] = None,
        verifier_model: Optional[str] = None,
        hallucination_flags: Optional[dict] = None,
        corrected_reasoning_text: Optional[str] = None,
        human_reviewed: Optional[bool] = None,
        reviewer_id: Optional[str] = None,
        review_notes: Optional[str] = None,
        dataset_split: Optional[str] = None
) -> dict:
    """
    Builds the JSON-serializable object representing ONE window of logs.

    `window_items` is a list of the small per-line dicts produced by
    parse_line() (NOT raw strings anymore) -- each already carries the
    mined Drain3 template alongside the raw line. This is still a
    placeholder: adjust freely once you've settled on your final schema
    (e.g. you may want to collapse to just an "event_sequence" of
    cluster_ids, drop "raw", etc).

    Parameters
    ----------
    window_items : list[dict]
        Exactly WINDOW_SIZE parsed-line dicts, in original file order.
        May contain PAD_VALUE-derived placeholder entries if the "pad"
        strategy was used on the final window.
    window_index : int
        0-based index of this window in the overall sequence.

    Returns
    -------
    dict
        A JSON-serializable dictionary representing this window.
    """
    return {
        "input": parsed_lines,
        "classification": classification,
        "explanation": explanation,
        "metadata": {
            "identity": {
                "id": str(uuid.uuid4()),
                "source_dataset": source_dataset,
                "source_file": source_file,
                "system_component": system_component,
                "collection_date": str(datetime.now())
            },
            "raw_content": {
                "raw_log_sequence": raw_lines,
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
                "log_template_id": log_template_id,
                "session_id": session_id
            },
            "augmentation": {
                "is_synthetic": False if augmentation_method is None else True,
                "augmentation_method": augmentation_method,
                "original_sample_id": [],
                "augmentation_model": augmentation_model,
                "augmentation_model_version": augmentation_model_version,
                "augmentation_prompt_id": augmentation_prompt_id
            },
            "llm": {
                "model": model,
                "generation_timestamp": generation_timestamp,
                "prompt_template_id": prompt_template_id,
                "generation_params": generation_params
            },
            "hallucination-check": {
                "verification_status": verification_status,
                "verification_method": verification_method,
                "verifier_model": verifier_model,
                "hallucination_flags": hallucination_flags,
                "corrected_reasoning_text": corrected_reasoning_text,
                "human_reviewed": human_reviewed,
                "reviewer_id": reviewer_id,
                "review_notes": review_notes
            },
            "dataset_split": dataset_split
        }
    }