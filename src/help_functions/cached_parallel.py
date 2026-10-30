"""
Streaming, parallel, resumable per-record processing for the LLM stages that run over big datasets
(production explanation generation, production judge).

`process_records` takes an iterator of records and yields them back in the same order with each one
updated, calling the LLM for up to `max_workers` records at once. Records are handled in chunks, so a
multi-GB input is never held in memory.

Resuming: every finished result is appended to a JSONL side file (`cache_path`) the moment it exists.
On the next run a record whose key is in that file is not sent to the LLM again, so a crash or Ctrl-C
costs at most the calls that were in flight. Results are keyed by `key_fn(record)`, which should cover
everything the result depends on (record id, the text the LLM is shown, the prompt/config), so a changed
input or prompt is recomputed instead of silently reusing an old answer.

Failures are not cached: a record whose call raised goes through `on_failure` and is retried next run.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor


def load_cache(cache_path: str) -> dict:
    cache = {}
    if not os.path.exists(cache_path):
        return cache
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # a line cut off by a crash; that record is simply recomputed
            cache[entry["key"]] = entry["payload"]
    return cache


def process_records(records, key_fn, compute, apply, on_failure, cache_path: str, stats: dict,
                    max_workers: int = 8, chunk_size: int = None, skip=None):
    """
    records:    iterator of dicts.
    key_fn:     record -> str cache key.
    compute:    record -> JSON-serializable payload (runs in a worker thread; may raise).
    apply:      (record, payload) -> record.
    on_failure: (record, exception) -> record, for records whose compute raised.
    stats:      dict updated in place: total, skipped, from_cache, computed, failed.
    skip:       optional record -> bool; True records are yielded unchanged and never sent to the LLM.
    """
    chunk_size = chunk_size or max_workers * 4
    cache = load_cache(cache_path)
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)

    def chunks():
        chunk = []
        for record in records:
            chunk.append(record)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    with open(cache_path, "a", encoding="utf-8") as cache_file, ThreadPoolExecutor(max_workers=max_workers) as pool:
        for chunk in chunks():
            skipped = [bool(skip and skip(r)) for r in chunk]
            keys = [None if s else key_fn(r) for r, s in zip(chunk, skipped)]
            pending = {i: pool.submit(compute, r) for i, (r, k) in enumerate(zip(chunk, keys))
                       if k is not None and k not in cache}
            for i, (record, key) in enumerate(zip(chunk, keys)):
                stats["total"] += 1
                if key is None:
                    stats["skipped"] += 1
                    yield record
                    continue
                if i in pending:
                    try:
                        cache[key] = pending[i].result()
                        cache_file.write(json.dumps({"key": key, "payload": cache[key]}) + "\n")
                        cache_file.flush()
                        stats["computed"] += 1
                    except Exception as e:
                        stats["failed"] += 1
                        yield on_failure(record, e)
                        continue
                else:
                    stats["from_cache"] += 1
                yield apply(record, cache[key])
