"""
log_windowizer.py

Streams a raw .log file line-by-line, parses each line into a Drain3
log template, groups the parsed lines into fixed-size, non-overlapping
windows of WINDOW_SIZE lines, and writes each window out to a JSON
array as soon as it is complete -- without ever holding the full file,
the full parsed dataset, or the full output array in memory.

Pipeline per line (single pass, in order):
    raw line
      -> regex-extract header fields from `log_format` (Content, Node, ...)
      -> feed Content into Drain3 TemplateMiner (st / depth / regex from config)
      -> get back a normalized template, e.g.:
         "<*> <*> <*> BGLERR_IDO_PKT_TIMEOUT connection lost to node/link/service card"
      -> buffer the parsed result -> emit as a window every WINDOW_SIZE lines

Author: (you)
"""

import os
import re
import csv
import json

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.masking import MaskingInstruction

from json_stream import streamable_list

from window_template import build_window_object

# ============================================================
# CONFIGURATION & CONTEXT VARIABLES
# ============================================================
# Single source of config truth for the whole pipeline (header format,
# Drain3 masking/similarity/depth parameters, and template persistence).

log_format = "<Label> <Timestamp> <Date> <Node> <Time> <NodeRepeat> <Type> <Component> <Level> <Content>"
# NOTE on pattern 5: Drain3's built-in parametrize_numeric_tokens only masks
# numbers while routing through INTERMEDIATE tree levels (2+ token content).
# Single-token content (e.g. a line that's just "366") and digits glued onto
# non-whitespace text (e.g. "summary...........................1") never go
# through that path, so they leak through as literal, unmasked templates.
# This catch-all closes that gap.
regex = [
    r"core\.\d+",
    r"((?<=[^A-Za-z0-9])|^)(0x[a-f0-9A-F]+)((?=[^A-Za-z0-9])|$)",
    r"((?<=[^A-Za-z0-9])|^)([0-9a-f]{6,} ?){3,}((?=[^A-Za-z0-9])|$)",
    r"\b(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{6,}\b",
    r"\b\d+\b",
]
st = 0.5
depth = 4
template_path = "/Users/kristian/Desktop/mt_dataset/agentic_ai/bgl/raw_parsing/templates/bgl.csv"

# What every masked token is replaced with inside the mined templates.
# Using "*" reproduces the standard Drain wildcard look: <*>
MASK_WITH = "*"

# ------------------------------------------------------------
# Windowing configuration
# ------------------------------------------------------------
WINDOW_SIZE = 20          # <-- fixed window length (lines per window)
INPUT_LOG_PATH = "/Users/kristian/Desktop/mt_dataset/agentic_ai/bgl/bgl.log"
OUTPUT_JSON_PATH = "/Users/kristian/Desktop/mt_dataset/agentic_ai/bgl/raw_parsing/parsed/bgl_output_windows.json"

# What to do with a trailing partial window (fewer than WINDOW_SIZE lines)
# at the end of the file. Options: "discard" or "pad".
INCOMPLETE_WINDOW_STRATEGY = "discard"   # <-- change to "pad" if desired
PAD_VALUE = ""  # value used to pad missing lines when strategy == "pad"


# ============================================================
# LOG-FORMAT HEADER PARSING (turns log_format into a regex)
# ============================================================
def generate_logformat_regex(logformat):
    """
    Converts a Drain-style format string, e.g.:
        "<Label> <Timestamp> <Date> <Node> <Time> <NodeRepeat> <Type> <Component> <Level> <Content>"
    into a compiled regex with one named group per <Field>, plus the
    ordered list of field names. This is the standard approach used by
    Drain/Drain3 reference parsers to split a raw line into header
    fields (Label, Timestamp, ...) and the free-text "Content" field
    that actually gets mined for templates.
    """
    headers = []
    splitters = re.split(r"(<[^<>]+>)", logformat)
    pattern = ""
    for i, piece in enumerate(splitters):
        if i % 2 == 0:
            # Literal separator text between fields (e.g. spaces) -> made
            # whitespace-flexible so minor spacing differences still match.
            pattern += re.sub(r" +", r"\\s+", piece)
        else:
            header = piece.strip("<>")
            pattern += f"(?P<{header}>.*?)"
            headers.append(header)
    return headers, re.compile("^" + pattern + "$")


LOG_HEADERS, LOG_FORMAT_REGEX = generate_logformat_regex(log_format)


def extract_log_fields(raw_line):
    """
    Splits one raw log line into its header fields using LOG_FORMAT_REGEX.

    Returns a dict of {field_name: value} for every field in `log_format`
    (Label, Timestamp, Date, Node, Time, NodeRepeat, Type, Component,
    Level, Content). If the line doesn't match the expected format
    (corrupt/truncated line), all fields fall back to None and the raw
    line itself is preserved under "Content" so it still flows through
    the pipeline instead of crashing it.
    """
    match = LOG_FORMAT_REGEX.match(raw_line)
    if match:
        return match.groupdict()
    return {header: None for header in LOG_HEADERS} | {"Content": raw_line}


# ============================================================
# DRAIN3 TEMPLATE MINER (configured from st / depth / regex)
# ============================================================
def build_template_miner():
    """
    Builds a Drain3 TemplateMiner using the module-level config variables:
      - st     -> drain_sim_th    (similarity threshold for clustering)
      - depth  -> drain_depth     (parse-tree depth)
      - regex  -> masking_instructions (pre-mask known variable patterns,
                  e.g. r"core\\.\\d+", before Drain's own clustering runs)

    No persistence handler is attached here -- this script runs as a
    single streaming pass and exports the learned templates to
    `template_path` itself at the end (see export_templates_to_csv).
    Swap in a drain3 FilePersistence/RedisPersistence handler if you
    need the miner's internal state to survive across separate runs.
    """
    config = TemplateMinerConfig()
    config.drain_sim_th = st
    config.drain_depth = depth
    config.masking_instructions = [
        MaskingInstruction(pattern, MASK_WITH) for pattern in regex
    ]
    return TemplateMiner(config=config)


# Drain3 clustering is inherently SEQUENTIAL (each new line is compared
# against clusters built from all previous lines), so this miner must be
# fed lines in original file order, in a single pass. That lines up
# perfectly with the strict line-by-line streaming read below -- we
# parse each line exactly once, right when we read it.
template_miner = build_template_miner()


def parse_line(raw_line):
    fields = extract_log_fields(raw_line)
    content = fields.get("Content") or raw_line

    result = template_miner.add_log_message(content)

    return {
        "raw": raw_line,
        "content": content,
        "template": result["template_mined"],
        "cluster_id": result["cluster_id"],
    }


@streamable_list
def generate_windows(input_path, window_size=WINDOW_SIZE):
    raw_lines = []
    parsed_lines = []
    is_anomalous = False

    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        for log_index, raw_line in enumerate(f):
            if log_index % 200_000 == 0:
                print(f"Processed {log_index} lines...")

            line = raw_line.rstrip("\n")
            if not line:
                continue

            raw_lines.append(raw_line)
            parsed_item = parse_line(line)
            parsed_lines.append(parsed_item)

            if raw_line[0] != '-':
                is_anomalous = True

            if len(parsed_lines) == window_size:
                yield build_window_object(
                    parsed_lines=parsed_lines,
                    raw_lines=raw_lines,
                    classification="abnormal" if is_anomalous else "normal",
                    source_dataset="LogHub bgl",
                    source_file="https://zenodo.org/records/8196385/files/BGL.zip?download=1",
                    system_component="bgl"
                )
                parsed_lines.clear()
                raw_lines.clear()
                is_anomalous = False


def write_windows_to_json(input_path, output_path, window_size=WINDOW_SIZE):
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(
            generate_windows(input_path, window_size=window_size),
            out_f,
            ensure_ascii=False
        )


def export_templates_to_csv(miner, output_csv_path):
    """
    DEDUPLICATION NOTE: Drain3 can emit several DIFFERENT cluster_ids that
    all render to the exact same template text (e.g. many clusters that
    each show up as "<*> <*>"). This isn't a masking bug -- Drain3 computes
    match similarity with include_params=False, so once a template position
    is already "<*>", it contributes nothing to the similarity score. A
    fully-wildcard template can therefore never be re-matched, so every
    later short/numeric line spawns a brand-new cluster_id instead of
    incrementing the existing one. cluster_id is NOT a reliable identity
    for "same event type" -- the template TEXT is -- so we group by text
    and sum occurrences instead of writing one row per raw cluster_id.
    """
    out_dir = os.path.dirname(output_csv_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    merged = {}  # template text -> total occurrences across all cluster_ids sharing it
    for cluster in miner.drain.clusters:
        template_text = cluster.get_template()
        merged[template_text] = merged.get(template_text, 0) + cluster.size

    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["EventId", "EventTemplate", "Occurrences"])
        for event_id, (template_text, occurrences) in enumerate(merged.items(), start=1):
            writer.writerow([event_id, template_text, occurrences])


if __name__ == "__main__":
    if not os.path.exists(INPUT_LOG_PATH):
        raise FileNotFoundError(
            f"Input log file not found: {INPUT_LOG_PATH!r}. "
            f"Update INPUT_LOG_PATH at the top of the script."
        )

    write_windows_to_json(INPUT_LOG_PATH, OUTPUT_JSON_PATH, window_size=WINDOW_SIZE)
    print(f"Done. Streamed windows of size {WINDOW_SIZE} -> {OUTPUT_JSON_PATH}")

    export_templates_to_csv(template_miner, template_path)
    print(f"Learned {len(template_miner.drain.clusters)} templates -> {template_path}")