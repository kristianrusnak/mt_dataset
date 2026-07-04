import json_stream

def get_all_sequences(dataset_path: str, number: int = -1, abnormal_label = "abnormal") -> tuple[list[str], list[str]]:
    """
    Opens dataset file by provided 'dataset_path' parameter and
    returns a list of all sequence id according to it's classification

    :param dataset_path: path to dataset file
    :param number: number of first n sequences that will be returned.
    Default to -1 which means all sequences are returned.
    :return tuple: list of id
    """
    normal_sequences = []
    abnormal_sequences = []
    
    with open(dataset_path, 'r') as f:
        data = json_stream.load(f)

        count = 0
        for item in data:
            if number != -1 and count >= number:
                break
            
            try:
                classification = item['classification']
                seq_id = item['metadata']['identity']['id']
                
                if classification == 'normal':
                    normal_sequences.append(seq_id)
                elif classification == abnormal_label:
                    abnormal_sequences.append(seq_id)
            except KeyError as e:
                print(f"Warning: Missing key {e} in item: {item}")

            count += 1
            
    return normal_sequences, abnormal_sequences
