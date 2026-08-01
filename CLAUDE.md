# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

This repo builds a labeled dataset for training/evaluating an LLM that explains *why* a
sequence of system log lines was classified as normal or abnormal. Source data is raw log
anomaly-detection datasets from [loghub](https://zenodo.org/records/8275861) (HDFS, BGL,
Thunderbird). The pipeline turns raw logs into windows/blocks of logs, asks an LLM to write a
short causal explanation for each window's existing classification, then verifies those
explanations (human or LLM-as-judge) for hallucinations before they're accepted into the
final dataset.

## Setup & commands

- Package manager is `uv` (see `uv.lock`); Python 3.13 (`.python-version`).
- Install deps: `uv sync`
- Run any script: `uv run python -m src.<module.path>` or `uv run python src/.../script.py`
- Scripts read `OPENAI_API_KEY` from the environment (via a local `.env`, gitignored) for any
  step that calls an LLM.
- **Run scripts from the repo root**, not from inside `src/`. Most modules import via the
  `src.` package path (e.g. `from src.help_functions.json_deep_convert import deep_convert`),
  which requires the repo root on `PYTHONPATH`/CWD. Note `src/creations/create_full_dataset_fixed_window.py`
  is the one exception — it imports its sibling `window_template.py` with a bare
  `from window_template import build_window_object`, so it must be run with `src/creations/`
  itself on the path (or invoked from within that directory).
- There is no test suite, linter, or formatter configured in this repo (`test.py` at the root
  is a scratch script for exploring the `json_stream` API, not a test). `a.json` is scratch
  data for that same script.
- Every stage script is a standalone CLI built with `argparse` and is run directly
  (`if __name__ == "__main__"`), with the current dev's local file paths as `--*` defaults —
  override them with real paths rather than editing the defaults in place.

## Pipeline architecture

Each dataset family (`bgl`, `hdfs`, `thunderbird`) flows through the same stages, but each
stage currently has a **separate, near-duplicated implementation per dataset** under
`src/<stage>/<dataset>/...` rather than one shared parameterized implementation. When fixing a
bug or changing behavior, check whether the same fix is needed in the sibling per-dataset
copies (this has already caused drift — e.g. `bgl/creation1.py`'s LLM call is commented out
and hardcoded to a placeholder string, while `thunderbird/creation1.py`'s is live).

1. **Window/block creation** (`src/creations/`) — turns raw log files + structured (Drain3-parsed)
   CSVs into fixed-size JSON "window" records.
   - `create_full_dataset_fixed_window.py`: slides a fixed-size window (`--window_size`,
     `--step`) over a raw log file + its structured CSV counterpart, used for BGL/Thunderbird
     (timestamp/line-based logs). A window is anomalous if any raw line's first column isn't `-`.
   - `create_full_dataset_block_id.py`: groups log lines by HDFS `blk_-?\d+` block ID instead
     of a sliding window, and labels each block using `anomaly_label.csv`. Uses a two-pass,
     offset-indexed read (byte offsets stored per block, then seeked) so it never loads the
     full raw/structured logs into memory — the log files are large.
   - `window_template.py`: `build_window_object(...)` is the **single canonical schema** for a
     dataset record — every later stage reads/writes this shape. Top-level: `input` (parsed
     log templates), `classification`, `explanation`, `metadata`. `metadata` has nested
     `identity` (uuid, source dataset/file, component), `raw_content` (raw log lines,
     timestamps, session id), `augmentation`, `llm` (generation model/params), and
     `hallucination-check` (verification status/method/flags — filled in by the review stage).
   - Both creation scripts write output by streaming with `json_stream.writer.streamable_list`
     (a generator decorated to look like a list to `json.dump`) so multi-GB datasets can be
     written without holding the whole thing in memory.

2. **Explanation generation** (`src/explanation_creation/<dataset>/creation1.py`) — for each
   window/block, calls an OpenAI chat model (via `langchain_openai.ChatOpenAI`) with a prompt
   from `src/prompts/<dataset>/prompt1.py` and writes the model's explanation into the
   `explanation` field, stamping `metadata.llm` and resetting `metadata.hallucination-check`
   to `unverified`. Input is read with `json_stream.load(...).persistent()` (streaming read of
   a large JSON array) and converted per-item to plain dicts via
   `src/help_functions/json_deep_convert.py::deep_convert` before mutation — `json_stream`
   objects aren't directly JSON-serializable. Records that already have a non-empty
   `explanation` are passed through unchanged (resumable/idempotent runs).

3. **Sampling** (`src/sampling/explanation_creation/<dataset>/sampling_1.py`) — draws an equal
   number of `normal`/abnormal sequences from a full dataset for cheaper downstream LLM calls
   and human review. Uses `src/help_functions/get_all_sequences.py` to collect sequence IDs by
   classification (note: the abnormal label string differs per dataset — `"abnormal"` for
   BGL/Thunderbird vs `"anomaly"` for HDFS, passed via `abnormal_label`), then
   `random.sample` with a fixed `--seed` for reproducibility.

4. **Review / hallucination-checking** (`src/review/`) — validates each generated explanation
   against the log sequence and fills in `metadata.hallucination-check`.
   - `llm_as_judge/<dataset>/llm_as_judge.py`: sends the sequence + explanation to an LLM
     (prompt in `src/prompts/judge_prompt.py`) with `.with_structured_output(HallucinationReview)`
     (a Pydantic model) to get back typed `hallucination_flags` / `corrected_reasoning_text` /
     `review_notes`. Records already flagged `"valid"` are skipped.
   - `human/<dataset>/human_reviewer.py`: same shape of output, filled in interactively via
     `input()` prompts in the terminal instead of an LLM call.
   - Both stamp `verification_method` (`"llm_as_judge"` vs `"human"`) and `reviewer_id`
     accordingly so provenance is traceable in the final dataset.

Supporting one-off maintenance scripts live in `src/help_functions/`
(`create_id.py`, `create_metadata.py`, `remove_augmented_key.py`, `split_output.py`) — small
CLI tools for backfilling/migrating fields on already-generated JSON dataset files.

## Prompts

`src/prompts/<dataset>/prompt1.py::get_prompt(...)` and `src/prompts/judge_prompt.py::get_judge_prompt(...)`
build the LLM prompts as plain formatted strings (no template engine). Both enforce a strict
output contract the rest of the pipeline depends on:
- Explanations must start with exactly `"This log sequence is normal because ..."` or
  `"...is abnormal because ..."`.
- The judge only checks for hallucination categories listed in its prompt
  (`contradiction_with_label`, `fabricated_detail`, `misattributed_cause`,
  `factual_inconsistency`, `unsupported_speculation`, `format_violation`) or emits `["valid"]`
  — it must not flag brevity/incompleteness, and must not re-classify the sequence.

If you add a prompt for a new dataset or stage, keep this contract identical, since downstream
code parses/depends on the fixed opening phrase and flag vocabulary.

## Data layout

- `dataset_short/<dataset>/` — small, checked-in dataset snapshots per pipeline stage
  (`full_not_explained.json`, `sampled_50_not_explained.json`, `sampled_50_explained.json`,
  `sampled_50_reviewed.json` / `sampled_50_llm_reviewed.json`, `llm-lade_base_seed.json` — a
  seed set imported from the external LLM-LADE project). Full raw datasets (multi-GB loghub
  files) are not checked in and are expected as local paths passed via `--*` CLI args.
- `build/` is a stale packaging artifact (from an old `setup.py`/`python -m build` run) — not
  part of the source of truth; prefer editing `src/`.
