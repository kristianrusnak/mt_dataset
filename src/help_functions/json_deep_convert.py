def deep_convert(obj):
    """
    Recursively converts json_stream persistent objects into
    standard Python dicts and lists so json.dump can serialize them.
    """
    if hasattr(obj, 'items'):
        # It's a dict-like object
        return {k: deep_convert(v) for k, v in obj.items()}
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
        # It's a list-like object
        return [deep_convert(v) for v in obj]
    else:
        # It's a primitive type (int, float, str, bool, None)
        return obj