import hashlib
from collections import defaultdict

import json_stream


def build_deduplicated_pool(
    dataset_path: str,
    abnormal_label: str = "abnormal",
    k: int = 3,
    exclude_cross_class: bool = False,
) -> tuple[list[str], list[str]]:
    """
    Streams dataset_path once and returns a (normal_ids, abnormal_ids) pool suitable
    for random.sample, deduplicated by parsed-log-template pattern.

    The duplicate signal is a hash of the ordered `input` field (parsed Drain3
    templates), not the raw log text -- raw lines carry per-line timestamps (and for
    BGL, node IDs) that make exact-text hashing useless as a duplicate signal even for
    windows that are behaviorally identical repeats of the same event. Within each
    (classification, template_hash) group, at most `k` representative ids are kept, so
    a single mega-cluster of repeated templates can't dominate a later random draw.

    If exclude_cross_class is True (HDFS only), any template_hash whose group spans
    both classes is dropped entirely from both classes before capping -- these windows
    aren't usable for either class, since the identical parsed-template sequence is
    labeled both ways elsewhere in the dataset, meaning the cause isn't recoverable
    from the window's own content.
    """
    groups: dict[str, dict[str, list[str]]] = {
        "normal": defaultdict(list),
        abnormal_label: defaultdict(list),
    }
    hash_classes: dict[str, set[str]] = defaultdict(set)

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json_stream.load(f)
        for item in data:
            try:
                # Read `input` before `classification`/`metadata`: json_stream items
                # here are forward-only, single-pass streams that follow the source's
                # key order (input, classification, explanation, metadata). Reading
                # out of order silently drops the skipped fields.
                template_hash = hashlib.md5("\n".join(item["input"]).encode("utf-8")).hexdigest()
                classification = item["classification"]
                seq_id = str(item["metadata"]["identity"]["id"])
            except KeyError as e:
                print(f"Warning: Missing key {e} in item, skipping")
                continue

            if classification not in groups:
                continue

            groups[classification][template_hash].append(seq_id)
            hash_classes[template_hash].add(classification)

    if exclude_cross_class:
        cross_class_hashes = [h for h, classes in hash_classes.items() if len(classes) > 1]
        for classification in groups:
            for template_hash in cross_class_hashes:
                groups[classification].pop(template_hash, None)

    normal_ids = [seq_id for ids in groups["normal"].values() for seq_id in ids[:k]]
    abnormal_ids = [seq_id for ids in groups[abnormal_label].values() for seq_id in ids[:k]]

    return normal_ids, abnormal_ids