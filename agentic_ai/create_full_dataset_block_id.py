from json_stream.writer import streamable_list
import json
import csv
import argparse
import re
from window_template import build_window_object

def create_fixed_window_dataset(raw_log_path, structured_log_path, anomaly_label_path, output_path, system_component):

    BLOCK_ID_RE = re.compile(r'(blk_-?\d+)')

    @streamable_list
    def block_id_generator():
        try:
            with open(raw_log_path, 'r', encoding='utf-8') as raw_f, \
                    open(structured_log_path, 'r', encoding='utf-8') as structured_f, \
                    open(anomaly_label_path, 'r', encoding='utf-8') as label_f:

                label_csv = csv.reader(label_f)
                next(label_csv, None)  # skip header

                structured_f.readline()  # skip structured header (manual, see note below)

                print("Index reading initiated!")
                # --- Pass 1: build a small index of (raw_offset, structured_offset)
                # per block_id. Only integers are stored here, not text.
                lines_processed = 1
                index = {}
                while True:
                    raw_offset = raw_f.tell()
                    raw_line = raw_f.readline()
                    structured_offset = structured_f.tell()
                    structured_line = structured_f.readline()

                    if not raw_line or not structured_line:
                        break

                    row = next(csv.reader([structured_line]))
                    content = row[1]
                    match = BLOCK_ID_RE.search(content)
                    if match:
                        block_id = match.group(1)
                        index.setdefault(block_id, []).append((raw_offset, structured_offset))

                    if lines_processed % 500_000 == 0:
                        print(f"Line number {lines_processed} has been processed!")
                    lines_processed += 1

                print("Index reading finished!")
                print("Starting saving logs into json file!")

                blocks_processed = 1
                # --- Pass 2: for each label, seek only to the lines that matter
                for label in label_csv:
                    block_id = label[0]
                    classification = label[1]
                    offsets = index.pop(block_id, [])

                    event_templates = []
                    raw_lines = []
                    for raw_offset, structured_offset in offsets:
                        raw_f.seek(raw_offset)
                        raw_lines.append(raw_f.readline())

                        structured_f.seek(structured_offset)
                        row = next(csv.reader([structured_f.readline()]))
                        event_templates.append(row[-1])

                    yield build_window_object(
                        parsed_lines=event_templates,
                        raw_lines=raw_lines,
                        classification=classification.lower(),
                        source_dataset="logpai/loghub",
                        source_file="https://zenodo.org/records/8275861",
                        system_component=system_component
                    )

                    if blocks_processed % 20_000 == 0:
                        print(f"Block number {blocks_processed} has been processed!")
                    blocks_processed += 1

        except FileNotFoundError as e:
            print(f"Error: File not found - {e}")
            raise
        except Exception as e:
            print(f"An error occurred: {e}")
            raise

    try:
        data_generator = block_id_generator()
        with open(output_path, 'w') as f:
            json.dump(data_generator, f, indent=2)
        print(f"Successfully created dataset at '{output_path}'.")
    except (FileNotFoundError, Exception) as e:
        print(f"Dataset creation failed. Please check file paths and content. Error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a fixed-window log dataset from raw and structured log files using streaming.",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        '--raw_log_path',
        default="/Users/kristian/Desktop/mt_dataset/HDFS/HDFS_full.log",
        type=str,
        help="Path to the raw log file (e.g., 'raw_log.log').")
    parser.add_argument(
        '--structured_log_path',
        default="/Users/kristian/Desktop/mt_dataset/HDFS/HDFS_full.log_structured.csv",
        type=str,
        help="Path to the structured log CSV file (e.g., 'log_structured.csv').")
    parser.add_argument(
        '--anomaly_label_path',
        default="/Users/kristian/Desktop/mt_dataset/HDFS_v1/preprocessed/anomaly_label.csv",
        type=str,
        help="Path to the structured log CSV file (e.g., 'log_structured.csv').")
    parser.add_argument(
        '--output_path',
        default="/Users/kristian/Desktop/mt_dataset/agentic_ai/hdfs/full_not_explained.json",
        type=str,
        help="Path for the output JSON file.")
    parser.add_argument(
        '--system_component',
        default="hdfs",
        type=str,
        help="The system component name (e.g: 'bgl').")

    args = parser.parse_args()

    create_fixed_window_dataset(
        args.raw_log_path,
        args.structured_log_path,
        args.anomaly_label_path,
        args.output_path,
        args.system_component
    )
