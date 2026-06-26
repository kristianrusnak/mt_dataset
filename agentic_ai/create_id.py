import json
import uuid
import argparse

def add_missing_ids(file_path):
    """
    Loads a JSON file containing a list of dictionaries, adds a unique UUID to each dictionary
    that is missing an "id" key, and writes the updated data back to the same file.

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
        if isinstance(item, dict) and 'id' not in item:
            item['id'] = str(uuid.uuid4())
            updated = True

    if updated:
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Successfully added missing IDs to '{file_path}'.")
        except IOError:
            print(f"Error: Could not write to the file '{file_path}'.")
    else:
        print(f"No missing IDs found in '{file_path}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add missing 'id' keys with unique UUIDs to a JSON file.")
    parser.add_argument("file_path", type=str, help="The path to the JSON file.")
    args = parser.parse_args()

    add_missing_ids(args.file_path)
