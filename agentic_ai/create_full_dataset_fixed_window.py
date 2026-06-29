from json_stream.writer import streamable_list
import json
import csv
import argparse
from window_template import build_window_object

def create_fixed_window_dataset(raw_log_path, structured_log_path, output_path, system_component, window_size=20, step=1):
    """
    Creates a JSON dataset of fixed-size log windows from raw and structured log files.

    Args:
        raw_log_path (str): Path to the raw log file (e.g., 'raw_log.log').
        structured_log_path (str): Path to the structured log file (CSV).
        output_path (str): Path to the output JSON file.
        system_component (str): The system component name (e.g., 'bgl').
        window_size (int): The number of log entries in each window.
        step (int): The step size to move the window.
    """

    @streamable_list
    def window_generator():
        try:
            with open(raw_log_path, 'r', encoding='utf-8') as raw_f, \
            open(structured_log_path, 'r', encoding='utf-8') as structured_f:
                # 1. Initialize the CSV reader for the structured file
                structured_csv = csv.reader(structured_f)

                # Skip header of structured log file safely
                next(structured_csv, None)

                window_id = 0

                # Helper function to read N lines from both files simultaneously
                def read_n_items(n):
                    r_lines, s_rows = [], []
                    for _ in range(n):
                        r_line = raw_f.readline()
                        s_row = next(structured_csv, None)  # Get parsed CSV row (list of strings)

                        if not r_line or s_row is None:
                            break  # EOF reached on one or both files

                        r_lines.append(r_line.strip())
                        s_rows.append(s_row)
                    return r_lines, s_rows

                # 2. Read initial window
                raw_lines, structured_rows = read_n_items(window_size)

                while len(raw_lines) == window_size and len(structured_rows) == window_size:
                    # 3. Process structured rows using proper CSV parsing
                    # s_row is already a list (e.g. ['date', 'time', ..., 'template']), so we just grab the last item
                    event_templates = [row[-1] for row in structured_rows]
                    is_anomalous = any(log[0] != '-' for log in raw_lines)

                    # Yield the structured object
                    yield build_window_object(
                        parsed_lines=event_templates,
                        raw_lines=raw_lines,
                        classification="abnormal" if is_anomalous else "normal",
                        source_dataset="logpai/loghub",
                        source_file="https://zenodo.org/records/8275861",
                        system_component=system_component
                    )
                    window_id += 1

                    raw_lines = raw_lines[step:]
                    structured_rows = structured_rows[step:]

                    # 2. Calculate if there is a gap we need to fast-forward through
                    lines_to_skip = max(0, step - window_size)

                    if lines_to_skip > 0:
                        # Read and discard the lines in the gap
                        skipped_raw, _ = read_n_items(lines_to_skip)
                        # If we hit EOF while trying to skip, we are done
                        if len(skipped_raw) < lines_to_skip:
                            break

                    # 3. Calculate how many lines we need to get back to a full window
                    lines_to_read = window_size - len(raw_lines)

                    # Read the exact number of lines needed
                    new_raw, new_structured = read_n_items(lines_to_read)

                    # If we couldn't fetch enough lines to complete the window, EOF is reached
                    if len(new_raw) < lines_to_read:
                        break

                    # Refill the window
                    raw_lines.extend(new_raw)
                    structured_rows.extend(new_structured)

        except FileNotFoundError as e:
            print(f"Error: File not found - {e}")
            raise
        except Exception as e:
            print(f"An error occurred: {e}")
            raise

    try:
        data_generator = window_generator()
        with open(output_path, 'w') as f:
            json.dump(data_generator, f, indent=2)
        print(f"Successfully created dataset at '{output_path}'.")
    except (FileNotFoundError, Exception):
        print("Dataset creation failed. Please check file paths and content.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a fixed-window log dataset from raw and structured log files using streaming.",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        '--raw_log_path',
        #default="/Users/kristian/Desktop/mt_dataset/BGL_2/BGL_full.log",
        default="/Users/kristian/Desktop/mt_dataset/Thunderbird/Thunderbird_full.log",
        type=str,
        help="Path to the raw log file (e.g., 'raw_log.log').")
    parser.add_argument(
        '--structured_log_path',
        #default="/Users/kristian/Desktop/mt_dataset/BGL_2/BGL_full.log_structured.csv",
        default="/Users/kristian/Desktop/mt_dataset/Thunderbird/Thunderbird_full.log_structured.csv",
        type=str,
        help="Path to the structured log CSV file (e.g., 'log_structured.csv').")
    parser.add_argument(
        '--output_path',
        #default="/Users/kristian/Desktop/mt_dataset/agentic_ai/bgl/full_not_explained.json",
        default="/Users/kristian/Desktop/mt_dataset/agentic_ai/thunderbird/full_not_explained.json",
        type=str,
        help="Path for the output JSON file.")
    parser.add_argument(
        '--system_component',
        #default="bgl",
        default="thunderbird",
        type=str,
        help="The system component name (e.g: 'bgl').")
    parser.add_argument('--window_size', type=int, default=20, help="The number of log entries in each window (default: 20).")
    #TODO bug can't be larger than --window_size
    parser.add_argument('--step', type=int, default=20, help="The step size to move the window (default: 20).")

    args = parser.parse_args()

    create_fixed_window_dataset(
        args.raw_log_path,
        args.structured_log_path,
        args.output_path,
        args.system_component,
        window_size=args.window_size,
        step=args.step
    )
