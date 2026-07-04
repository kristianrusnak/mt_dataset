from src.help_functions.get_all_sequences import get_all_sequences
from src.help_functions.json_deep_convert import deep_convert
from json_stream import streamable_list, load
import json
import random
import argparse

def create_sample_dataset(source_path: str, output_path: str, num_samples: int, seed: int = 42):
    """
    Creates a sampled dataset with an equal number of normal and abnormal sequences.

    :param source_path: Path to the full dataset file.
    :param output_path: Path to save the sampled dataset.
    :param num_samples: The number of samples to take for each classification (normal and abnormal).
    :param seed: The random seed for reproducibility.
    """
    random.seed(seed)
    normal_ids, abnormal_ids = get_all_sequences(source_path)

    if len(normal_ids) < num_samples or len(abnormal_ids) < num_samples:
        raise ValueError("Not enough sequences in the source dataset to create the desired number of samples.")

    sampled_normal_ids = random.sample(normal_ids, num_samples)
    sampled_abnormal_ids = random.sample(abnormal_ids, num_samples)
    
    selected_ids = set(sampled_normal_ids + sampled_abnormal_ids)

    @streamable_list
    def sequence_generator():
        with open(source_path, 'r', encoding="utf-8") as f:
            loaded_data = load(f)
            for item in loaded_data.persistent():
                try:
                    if str(item['metadata']['identity']['id']) in selected_ids:
                        yield deep_convert(item)
                except KeyError:
                    # This will skip items that don't have the expected ID structure
                    continue

    with open(output_path, 'w') as f:
        data = sequence_generator()
        json.dump(data, f, indent=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create a sampled dataset from a larger JSON dataset.")
    parser.add_argument(
        "--source_path",
        type=str,
        default="/Users/kristian/Desktop/mt_dataset/agentic_ai/bgl/full_not_explained.json",
        help="Path to the source JSON dataset.")
    parser.add_argument(
        "--output_path",
        type=str,
        default="/Users/kristian/Desktop/mt_dataset/agentic_ai/bgl/sampled_50_not_explained.json",
        help="Path to save the sampled JSON dataset.")
    parser.add_argument(
        "--num_samples",
        type=int,
        default=50,
        help="Number of normal and abnormal sequences to sample.")
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility.")
    
    args = parser.parse_args()
    
    create_sample_dataset(args.source_path, args.output_path, args.num_samples, args.seed)