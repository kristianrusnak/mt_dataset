import json
import random
from datetime import datetime, timezone

from json_stream import load

from src.help_functions.dedup_pool import build_deduplicated_pool
from src.help_functions.id_ledger import append_used_ids, get_used_ids
from src.help_functions.json_deep_convert import deep_convert
from src.help_functions.manifest_log import append_manifest_entry


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _collect_records(source_path: str, wanted_ids: set[str]) -> dict[str, dict]:
    """
    Streams source_path once (persistent mode, so fields can be read in any order)
    and returns {id: full_record_dict} for every id in wanted_ids, stopping early
    once all of them have been found.
    """
    found: dict[str, dict] = {}
    with open(source_path, "r", encoding="utf-8") as f:
        data = load(f)
        for item in data.persistent():
            try:
                seq_id = str(item["metadata"]["identity"]["id"])
            except KeyError:
                continue
            if seq_id in wanted_ids:
                found[seq_id] = deep_convert(item)
                if len(found) == len(wanted_ids):
                    break
    return found


def _write_records(output_path: str, ids: list[str], records: dict[str, dict]) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([records[seq_id] for seq_id in ids if seq_id in records], f, indent=4)


def _deduped_available_pool(
    source_path: str,
    ledger_path: str,
    abnormal_label: str,
    k: int,
    exclude_cross_class: bool,
) -> tuple[list[str], list[str]]:
    normal_pool, abnormal_pool = build_deduplicated_pool(
        source_path, abnormal_label=abnormal_label, k=k, exclude_cross_class=exclude_cross_class,
    )
    used_ids = get_used_ids(ledger_path)
    normal_pool = [seq_id for seq_id in normal_pool if seq_id not in used_ids]
    abnormal_pool = [seq_id for seq_id in abnormal_pool if seq_id not in used_ids]
    return normal_pool, abnormal_pool


def draw_gold_sample(
    dataset_name: str,
    source_path: str,
    natural_output_path: str,
    supplemental_output_path: str,
    ledger_path: str,
    manifest_path: str,
    natural_core_per_class: int = 15,
    supplemental_per_class: int = 20,
    seed: int = 42,
    abnormal_label: str = "abnormal",
    k: int = 3,
    exclude_cross_class: bool = False,
) -> None:
    """
    Draws the judge-validation gold sample (plan doc step 1): a natural core (evenly
    split normal/abnormal, plain random draw) plus a separate supplemental oversample
    pool drawn from the same deduplicated/filtered population but NOT yet selected
    into the gold set -- that selection depends on human review scores from step 2 and
    is a later follow-up.

    Both strata are drawn from the population after deduplication (capped at k
    representatives per duplicate template-hash cluster) and the HDFS cross-class
    filter (when exclude_cross_class=True), excluding any id already recorded in the
    id ledger, and disjoint from each other. Drawn ids are appended to the ledger
    (purpose "gold_natural" / "gold_supplemental") and logged to the manifest with a
    stratum field, so this run is never repeated over the same windows.
    """
    random.seed(seed)

    normal_pool, abnormal_pool = _deduped_available_pool(
        source_path, ledger_path, abnormal_label, k, exclude_cross_class,
    )

    needed_per_class = natural_core_per_class + supplemental_per_class
    if len(normal_pool) < needed_per_class or len(abnormal_pool) < needed_per_class:
        raise ValueError(
            f"Not enough deduplicated {dataset_name} records to draw the gold sample: "
            f"normal pool={len(normal_pool)}, abnormal pool={len(abnormal_pool)}, "
            f"need {needed_per_class} of each (natural core {natural_core_per_class} "
            f"+ supplemental {supplemental_per_class})."
        )

    normal_draw = random.sample(normal_pool, needed_per_class)
    abnormal_draw = random.sample(abnormal_pool, needed_per_class)

    natural_normal, supplemental_normal = (
        normal_draw[:natural_core_per_class],
        normal_draw[natural_core_per_class:],
    )
    natural_abnormal, supplemental_abnormal = (
        abnormal_draw[:natural_core_per_class],
        abnormal_draw[natural_core_per_class:],
    )

    natural_ids = natural_normal + natural_abnormal
    supplemental_ids = supplemental_normal + supplemental_abnormal

    records = _collect_records(source_path, set(natural_ids) | set(supplemental_ids))
    _write_records(natural_output_path, natural_ids, records)
    _write_records(supplemental_output_path, supplemental_ids, records)

    append_used_ids(ledger_path, natural_ids, purpose="gold_natural")
    append_used_ids(ledger_path, supplemental_ids, purpose="gold_supplemental")

    timestamp = _now_iso()
    shared_params = {
        "seed": seed,
        "k": k,
        "abnormal_label": abnormal_label,
        "exclude_cross_class": exclude_cross_class,
    }

    append_manifest_entry(manifest_path, {
        "step": 1,
        "action": "gold_sample_draw",
        "timestamp": timestamp,
        "dataset": dataset_name,
        "stratum": "natural",
        "params": {**shared_params, "per_class": natural_core_per_class},
        "inputs": [source_path],
        "outputs": [natural_output_path],
        "metrics": {},
        "notes": (
            f"Natural core: {len(natural_normal)} normal / {len(natural_abnormal)} "
            f"abnormal. ids={natural_ids}"
        ),
    })
    append_manifest_entry(manifest_path, {
        "step": 1,
        "action": "gold_sample_draw",
        "timestamp": timestamp,
        "dataset": dataset_name,
        "stratum": "supplemental",
        "params": {**shared_params, "per_class": supplemental_per_class},
        "inputs": [source_path],
        "outputs": [supplemental_output_path],
        "metrics": {},
        "notes": (
            f"Supplemental oversample pool, drawn but NOT yet selected into the gold "
            f"set (topup selection is a follow-up step, pending step 2 human scores): "
            f"{len(supplemental_normal)} normal / {len(supplemental_abnormal)} abnormal. "
            f"ids={supplemental_ids}"
        ),
    })


def draw_production_sample(
    dataset_name: str,
    source_path: str,
    output_path: str,
    ledger_path: str,
    manifest_path: str,
    num_per_class: int,
    seed: int = 42,
    abnormal_label: str = "abnormal",
    k: int = 3,
    exclude_cross_class: bool = False,
) -> None:
    """
    Draws the production set (plan doc step 6): verified by the judge alone, at
    scale, with no per-item human review, from the same deduplicated/filtered
    population as the gold sample but a disjoint ID pool (anything already in the
    ledger -- gold or previously-drawn production -- is excluded). Production-set
    size is deliberately not defaulted here (see the plan doc's Open Questions); the
    caller must pass num_per_class explicitly each run.
    """
    random.seed(seed)

    normal_pool, abnormal_pool = _deduped_available_pool(
        source_path, ledger_path, abnormal_label, k, exclude_cross_class,
    )

    if len(normal_pool) < num_per_class or len(abnormal_pool) < num_per_class:
        raise ValueError(
            f"Not enough deduplicated {dataset_name} records to draw the production "
            f"sample: normal pool={len(normal_pool)}, abnormal pool={len(abnormal_pool)}, "
            f"need {num_per_class} of each."
        )

    normal_draw = random.sample(normal_pool, num_per_class)
    abnormal_draw = random.sample(abnormal_pool, num_per_class)
    drawn_ids = normal_draw + abnormal_draw

    records = _collect_records(source_path, set(drawn_ids))
    _write_records(output_path, drawn_ids, records)

    append_used_ids(ledger_path, drawn_ids, purpose="production")

    append_manifest_entry(manifest_path, {
        "step": 6,
        "action": "production_sample_draw",
        "timestamp": _now_iso(),
        "dataset": dataset_name,
        "params": {
            "seed": seed,
            "k": k,
            "abnormal_label": abnormal_label,
            "exclude_cross_class": exclude_cross_class,
            "num_per_class": num_per_class,
        },
        "inputs": [source_path],
        "outputs": [output_path],
        "metrics": {},
        "notes": f"Production draw: {len(normal_draw)} normal / {len(abnormal_draw)} abnormal. ids={drawn_ids}",
    })