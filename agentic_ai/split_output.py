import json
import argparse

def remove_augmented_key(file_path):
    """
    Loads a JSON file containing a list of dictionaries, removes the 'output' key from each
    dictionary if it exists, and splits output into 'classification' and 'explanation' then
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
        if isinstance(item, dict) and 'output' in item:
            output = item['output']
            del item['output']
            split_idx = output.index("-")
            classification = output[:split_idx]
            explanation = output[split_idx+1:]
            item['classification'] = classification
            item['explanation'] = explanation
            updated = True

    if updated:
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Successfully split 'output' key from '{file_path}' to 'classification' and 'explanation'.")
        except IOError:
            print(f"Error: Could not write to the file '{file_path}'.")
    else:
        print(f"No 'output' key found in '{file_path}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Splits output from the dataset into classification and explanation")
    parser.add_argument("file_path", type=str, help="The path to the JSON file.")
    args = parser.parse_args()

    remove_augmented_key(args.file_path)
