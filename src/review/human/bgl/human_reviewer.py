
import json
import random
import argparse
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

def sample_sequences(input_path: str, review_percentage: float, seed: int = 42):
    """
    Loads all sequences, separates into normal/anomalous, shuffles, and samples
    equal percentage from each class.
    Returns a list of sequences to review.
    """
    random.seed(seed)
    
    normal_sequences = []
    anomalous_sequences = []
    
    with open(input_path, 'r', encoding='utf-8') as input_file:
        for sequence_data_raw in load(input_file).persistent():
            sequence_data = deep_convert(sequence_data_raw)
            classification = sequence_data.get('classification', '').lower()
            if classification == 'normal':
                normal_sequences.append(sequence_data.get("metadata").get("identity").get("id"))
            elif classification == 'anomalous' or classification == 'abnormal':
                anomalous_sequences.append(sequence_data.get("metadata").get("identity").get("id"))
    
    random.shuffle(normal_sequences)
    random.shuffle(anomalous_sequences)
    
    normal_sample_size = int(len(normal_sequences) * review_percentage / 100)
    anomalous_sample_size = int(len(anomalous_sequences) * review_percentage / 100)
    
    sampled_normal = normal_sequences[:normal_sample_size]
    sampled_anomalous = anomalous_sequences[:anomalous_sample_size]
    
    combined = sampled_normal + sampled_anomalous
    random.shuffle(combined)
    
    print(f"Total sequences: {len(normal_sequences) + len(anomalous_sequences)}")
    print(f"  Normal: {len(normal_sequences)} -> sampled: {len(sampled_normal)}")
    print(f"  Anomalous: {len(anomalous_sequences)} -> sampled: {len(sampled_anomalous)}")
    print(f"  Total to review: {len(combined)} ({review_percentage}% each class)")
    
    return combined

@streamable_list
def review_sequences(input_path: str, review_percentage: float = 100.0, seed: int = 42):
    """
    Iterates through sampled sequences, prompts for review, and yields updated sequences.
    """
    sequences_to_review = sample_sequences(input_path, review_percentage, seed)
    
    with open(input_path, 'r', encoding='utf-8') as input_file:

        for sequence_data in load(input_file).persistent():
            sequence_data = deep_convert(sequence_data)

            sequence_id = sequence_data.get("metadata", {}).get("identity", {}).get("id")
            hallucination_flags = sequence_data.get("metadata", {}).get("hallucination-check", {}).get("hallucination_flags") or []
            
            if sequence_id not in sequences_to_review and "valid" not in hallucination_flags:
                yield sequence_data
                continue

            parsed_logs = sequence_data.get('input')
            raw_logs = sequence_data.get('metadata').get('raw_content').get('raw_log_sequence')
            logs = get_logs(parsed_logs, raw_logs)

            print("\n" + "="*50)
            print(f"Reviewing sequence_id: {sequence_id}")
            print(f"Classification: {sequence_data.get('classification')}")
            print(f"Input: \n{'\n'.join(logs)}")
            print(f"Explanation: {sequence_data.get('explanation')}")
            print("="*50 + "\n")

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
                "verifier_model": "review/human/bgl/human_reviewer.py",
                "hallucination_flags": hallucination_flags.split(',') if hallucination_flags else None,
                "corrected_reasoning_text": corrected_reasoning_text or None,
                "human_reviewed": True,
                "reviewer_id": "Kristian Rusnak",
                "review_notes": review_notes or None,
                "review_timestamp": str(datetime.now())
            }

            yield sequence_data

def main():
    parser = argparse.ArgumentParser(description="Human review of log sequences with configurable sampling")
    parser.add_argument("--input", default="dataset_short/bgl/sampled_50_explained.json", help="Input JSON file path")
    parser.add_argument("--output", default="dataset_short/bgl/sampled_50_human_reviewed.json", help="Output JSON file path")
    parser.add_argument("--percentage", type=float, default=20.0, help="Percentage of sequences to review (split equally between normal/anomalous)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    
    args = parser.parse_args()
    
    reviewed_data_stream = review_sequences(args.input, args.percentage, args.seed)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(reviewed_data_stream, f, indent=4)
    
    print(f"\nReview process complete. Reviewed data saved to {args.output}")


if __name__ == "__main__":
    main()
