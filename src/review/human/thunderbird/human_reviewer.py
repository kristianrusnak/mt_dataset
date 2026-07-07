
import json
from src.help_functions.json_deep_convert import deep_convert
from json_stream import streamable_list, load
from datetime import datetime

def get_user_input(prompt, default_value):
    """
    Prompts the user for input with a default value.
    """
    if default_value:
        return input(f"{prompt} [default: {default_value}]: ") or default_value
    else:
        return input(f"{prompt}: ")

def get_logs(parsed_logs: list, raw_logs: list):
    result = []
    for parsed_log, raw_log in zip(parsed_logs, raw_logs):
        clsf = 'normal' if raw_log.startswith("-") else "anomalous"
        result.append(f"classification: {clsf}; log: {parsed_log}")
    return result

@streamable_list
def review_sequences(input_path: str):
    """
    Iterates through sequences, prompts for review, and yields updated sequences.
    """
    with open(input_path, 'r', encoding='utf-8') as input_file:
        for sequence_data_raw in load(input_file).persistent():
            sequence_data = deep_convert(sequence_data_raw)
            parsed_logs = sequence_data.get('input')
            raw_logs = sequence_data.get('metadata').get('raw_content').get('raw_log_sequence')
            logs = get_logs(parsed_logs, raw_logs)

            print("\\n" + "="*50)
            print(f"Reviewing sequence_id: {sequence_data.get('metadata').get('identity').get('id')}")
            print(f"Input: \n{'\n'.join(logs)}")
            print(f"Explanation: {sequence_data.get('explanation')}")
            print("="*50 + "\\n")

            hallucination_check = sequence_data.get('metadata', {}).get('hallucination-check', {})

            hallucination_flags = get_user_input(
                "Enter hallucination_flags (comma-separated)",
                hallucination_check.get('hallucination_flags')
            )
            corrected_reasoning_text = get_user_input(
                "Enter corrected_reasoning_text",
                hallucination_check.get('corrected_reasoning_text')
            )
            review_notes = get_user_input(
                "Enter review_notes",
                hallucination_check.get('review_notes')
            )

            sequence_data['metadata']['hallucination-check'] = {
                "verification_status": "verified",
                "verification_method": "human",
                "verifier_model": "thunderbird/human/human_reviewer.py",
                "hallucination_flags": hallucination_flags.split(',') if hallucination_flags else None,
                "corrected_reasoning_text": corrected_reasoning_text or None,
                "human_reviewed": True,
                "reviewer_id": "Kristian Rusnak",
                "review_notes": review_notes or None,
                "review_timestamp": str(datetime.now())
            }

            yield sequence_data

def main():
    input_file = "dataset_short/thunderbird/sampled_50_explained.json"
    output_file = "dataset_short/thunderbird/sampled_50_reviewed.json"

    reviewed_data_stream = review_sequences(input_file)

    with open(output_file, 'w', encoding='utf-8') as f:
        # Use a lambda to handle the generator from streamable_list
        json.dump(reviewed_data_stream, f, indent=4)
    
    print(f"\\nReview process complete. Reviewed data saved to {output_file}")


if __name__ == "__main__":
    main()
