import json
import argparse
import uuid

def remove_augmented_key(file_path):
    """
    Loads a JSON file containing a list of dictionaries, create default metadata for dataset familly then
    writes the updated data back to the same file.

    Args:
        file_path (str): The path to the JSON file.
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: The file '{file_path}' is not a valid JSON file.")
        return

    if not isinstance(data, list):
        print(f"Error: The JSON file '{file_path}' does not contain a list of dictionaries.")
        return

    updated = False
    for item in data:
        if isinstance(item, dict) and 'metadata' not in item:
            metadata = {
                "identity": {
                    "id": str(uuid.uuid4()),
                    "source_dataset": "LLM-LADE github seed_data",
                    "source_file": "https://github.com/sleep-zzw-bot/LLM-LADE/blob/master/seed_data/seed_Thunderbird.json",
                    "system_component": "thunderbird",
                    "collection_date": None
                },
                "raw_content": {
                    "raw_log_sequence": [],
                    "start_timestamp": None,
                    "end_timestamp": None,
                    "log_template_id": None,
                    "session_id": None
                },
                "augmentation": {
                    "is_synthetic": False,
                    "augmentation_method": None,
                    "original_sample_id": [],
                    "augmentation_model": None,
                    "augmentation_model_version": None,
                    "augmentation_prompt_id": None,
                },
                "llm": {
                    "model": None,
                    "generation_timestamp": None,
                    "prompt_template_id": None,
                    "generation_params": {}
                },
                "hallucination-check": {
                    "verification_status": "verified",
                    "verification_method": "human",
                    "verifier_model": None,
                    "hallucination_flags": None,
                    "corrected_reasoning_text": None,
                    "human_reviewed": True,
                    "reviewer_id": "LLM-LADE",
                    "review_notes": None
                },
                "dataset_split": None
            }
            item['metadata'] = metadata
            updated = True

    if updated:
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Successfully created metadata for '{file_path}'")
        except IOError:
            print(f"Error: Could not write to the file '{file_path}'.")
    else:
        print(f"Metadata already exists in '{file_path}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create default metadata for dataset familly ")
    parser.add_argument("file_path", type=str, help="The path to the JSON file.")
    args = parser.parse_args()

    remove_augmented_key(args.file_path)
