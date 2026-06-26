import json
import argparse

def remove_augmented_key(file_path):
    """
    Loads a JSON file containing a list of dictionaries, removes the 'augmented' key from each
    dictionary if it exists, and writes the updated data back to the same file.

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
        if isinstance(item, dict) and 'augmented' in item:
            del item['augmented']
            updated = True

    if updated:
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Successfully removed 'augmented' key from '{file_path}'.")
        except IOError:
            print(f"Error: Could not write to the file '{file_path}'.")
    else:
        print(f"No 'augmented' key found in '{file_path}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove the 'augmented' key from a JSON file.")
    parser.add_argument("file_path", type=str, help="The path to the JSON file.")
    args = parser.parse_args()

    remove_augmented_key(args.file_path)
