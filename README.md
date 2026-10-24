# mt-dataset

Pipeline code and data for the explanation dataset. See [CLAUDE.md](CLAUDE.md) for the pipeline overview and
[docs/validate_judge_grid_search_guide.md](docs/validate_judge_grid_search_guide.md) for installing and for the
full judge grid-search options.

## Run the deepseek_v7 judge check

`deepseek_v7` is `deepseek_v6` with its "normal lines presented as faults" rule kept for BGL only (Thunderbird
goes back to v5's behaviour). Details and the numbers behind it are in
`src/prompts/judge_criteria/deepseek_v7.py`. Scores from this check are exploratory: the restriction was chosen
after looking at the held-out split.

Run from the repository root, with `LITELLM_API_KEY` and `LITELLM_API_BASE` set (see the guide above).

```bash
# 1. Check the cost first: no network calls. Expect 1 config, 140 judge calls (search) and 70 (held_out).
uv run python -m src.review.validate_judge.search estimate \
  --space src/review/validate_judge/search_space_v7.json --split search --gold_file gold_all_relabeled.json

# 2. Score v7 on the 140-item search split (temperature 0.25, effort high).
uv run python -m src.review.validate_judge.search grid \
  --space src/review/validate_judge/search_space_v7.json --split search --gold_file gold_all_relabeled.json

# 3. Score it on the 70-item held-out split.
uv run python -m src.review.validate_judge.search grid \
  --space src/review/validate_judge/search_space_v7.json --split held_out --gold_file gold_all_relabeled.json
```

- `--gold_file gold_all_relabeled.json` matters: without it the search scores against the original labels.
- Add `--max_workers 4` if the proxy rate-limits you (default 8 parallel calls).
- Each run writes `dataset_short/judge_runs/deepseek-v4.1-flash__t0.25__deepseek_v7__ehigh.json` and appends
  entries to `docs/llm_judge_validation_log.json`. Runs are resumable: re-running picks up the cached verdicts.
- Both split runs write the same run file; the second adds its items to it.

For reference, the earlier results on the same splits (relabeled gold, temperature 0.25, score = mean Youden's J):

| prompt | search (140) | held-out (70) |
|---|---|---|
| v5 | 0.607 | 0.625 |
| v6 | 0.718 | 0.652 |
