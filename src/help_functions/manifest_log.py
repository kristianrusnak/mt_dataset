import json
import os


def append_manifest_entry(manifest_path: str, entry: dict) -> None:
    """
    Appends one entry to the append-only JSON array manifest at manifest_path
    (docs/llm_judge_validation_log.json's schema), creating it as an empty array
    first if it doesn't exist yet. Never overwrites existing entries.
    """
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = []

    manifest.append(entry)

    os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)