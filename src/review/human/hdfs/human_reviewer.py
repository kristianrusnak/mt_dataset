import json
import random
from datetime import datetime
from src.help_functions.json_deep_convert import deep_convert
from json_stream import streamable_list, load


def get_user_input(prompt, default_value):
    """
    Prompts the user for input with a default value.
    """
    if default_value:
        return input(f"{prompt} [default: {default_value}]: ") or default_value
    else:
        return input(f"{prompt}: ")


def get_logs(parsed_logs: list):
    result = []
    for i, parsed_log in enumerate(parsed_logs):
        result.append(f"{i}. log: {parsed_log}")
    return result


def sample_entries(data, sample_ratio, seed=42):
    """
    Randomly sample entries with 50/50 split by classification.
    """
    random.seed(seed)
    
    normal_entries = [entry for entry in data if entry.get('classification') == 'normal']
    anomaly_entries = [entry for entry in data if entry.get('classification') == 'anomaly']
    
    total_samples = int(len(data) * sample_ratio)
    samples_per_class = total_samples // 2
    
    sampled_normal = random.sample(normal_entries, min(samples_per_class, len(normal_entries)))
    sampled_anomaly = random.sample(anomaly_entries, min(samples_per_class, len(anomaly_entries)))
    
    sampled = sampled_normal + sampled_anomaly
    random.shuffle(sampled)
    
    return sampled


@streamable_list
def review_sequences(input_path: str, sample_ratio: float = 0.1):
    """
    Iterates through sampled sequences, prompts for review, and yields updated sequences.
    """
    with open(input_path, 'r', encoding='utf-8') as input_file:
        all_data = list(load(input_file).persistent())
        all_data = [deep_convert(entry) for entry in all_data]
    
    sampled_entries = sample_entries(all_data, sample_ratio)
    sampled_ids = {entry['metadata']['identity']['id'] for entry in sampled_entries}
    
    print(f"Total entries: {len(all_data)}")
    print(f"Sampled for review: {len(sampled_entries)} ({sample_ratio*100}%)")
    print(f"  Normal: {sum(1 for e in sampled_entries if e.get('classification') == 'normal')}")
    print(f"  Anomaly: {sum(1 for e in sampled_entries if e.get('classification') == 'anomaly')}")
    print()
    
    for i, sequence_data_raw in enumerate(all_data):
        sequence_data = deep_convert(sequence_data_raw)
        seq_id = sequence_data.get('metadata', {}).get('identity', {}).get('id')
        
        if seq_id not in sampled_ids:
            yield sequence_data
            continue
        
        parsed_logs = sequence_data.get('input')
        logs = get_logs(parsed_logs)
        
        hallucination_check = sequence_data.get('metadata', {}).get('hallucination-check', {})
        
        print("\n" + "="*50)
        print(f"Reviewing sequence {i+1}/{len(sampled_entries)} (ID: {seq_id})")
        print(f"Classification: {sequence_data.get('classification')}")
        print(f"Input:\n{'\n'.join(logs)}")
        print(f"Explanation: {sequence_data.get('explanation')}")
        print("="*50 + "\n")
        
        hallucination_flags = get_user_input(
            "Enter hallucination_flags (comma-separated)",
            hallucination_check.get('hallucination_flags') or ""
        )
        corrected_reasoning_text = get_user_input(
            "Enter corrected_reasoning_text",
            hallucination_check.get('corrected_reasoning_text') or ""
        )
        review_notes = get_user_input(
            "Enter review_notes",
            hallucination_check.get('review_notes') or ""
        )
        
        sequence_data['metadata']['hallucination-check'] = {
            "verification_status": "verified",
            "verification_method": "human",
            "verifier_model": "hdfs/human/human_reviewer.py",
            "hallucination_flags": hallucination_flags.split(',') if hallucination_flags else None,
            "corrected_reasoning_text": corrected_reasoning_text or None,
            "human_reviewed": True,
            "reviewer_id": "Kristian Rusnak",
            "review_notes": review_notes or None,
            "review_timestamp": str(datetime.now())
        }
        
        yield sequence_data


def main():
    input_file = "dataset_short/hdfs/sampled_50_explained.json"
    output_file = "dataset_short/hdfs/sampled_50_human_reviewed.json"
    sample_ratio = 0.2
    
    reviewed_data_stream = review_sequences(input_file, sample_ratio)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(reviewed_data_stream, f, indent=4)
    
    print(f"\nReview process complete. Reviewed data saved to {output_file}")


if __name__ == "__main__":
    main()