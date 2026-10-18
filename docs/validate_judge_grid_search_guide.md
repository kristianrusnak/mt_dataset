<!--
Generated/modified by AI Kilo Code 7.5.6-gratex-017, used model gti-litellm/deepseek-v4.1-flash.
-->

# Installation & Usage Guide: Judge-Config Grid Search

This guide walks you through installing the project and running the judge-config grid search:

```bash
uv run python -m src.review.validate_judge.search grid
```

The grid search scores every judge configuration (model x prompt x temperature x reasoning effort)
from `src/review/validate_judge/search_space.json` against the human-reviewed gold pool, and appends
the winning config to the manifest at `docs/llm_judge_validation_log.json`.

**Generated/modified by AI Kilo Code 7.5.6-gratex-017, used model gti-litellm/deepseek-v4.1-flash.**

- **Requirements:** Python 3.12+, `uv`, `git`, network access to the LiteLLM proxy.
- **Outputs written by the run:** `dataset_short/judge_runs/<config>.json` (per-config cache/resume files)
  and new entries in `docs/llm_judge_validation_log.json`.
- **Cost note:** grid mode makes one judge call per gold item per config — thousands of LLM calls.
  Run `estimate` first to see the count before spending credits.

---

## 1. Clone the repository

All three operating systems:

```bash
git clone https://github.com/kristianrusnak/mt_dataset.git
cd mt_dataset
```

The run must be started from the repository root (`mt_dataset/`), because every module is imported
via the `src.` package path.

---

## 2. Install `uv` (skip if already installed)

Check first:

```bash
uv --version
```

If that prints a version, skip to step 3. Otherwise install `uv`:

### Linux and macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then reload your shell so `~/.local/bin` is on `PATH`:

```bash
source "$HOME/.local/bin/env"
uv --version
```

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv --version
```

Open a new terminal if `uv` is not found after installation.

---

## 3. Create `.venv` and install dependencies

`uv` reads `pyproject.toml` and the pinned `uv.lock`; `uv sync` creates `.venv` and installs exactly
the locked dependencies.

```bash
uv sync
```

Verify the environment and the CLI wiring without spending any LLM calls:

```bash
uv run python -m src.review.validate_judge.search estimate
```

`estimate` makes no network calls and prints the gold-pool size and the number of judge calls the
grid would make. If this works, the install is complete.

---

## 4. Set the required environment variables

The judge calls open-source models behind one LiteLLM proxy and reads two variables from the
environment (see `src/review/validate_judge/judge.py`):

| Variable | Purpose |
|----------|---------|
| `LITELLM_API_KEY` | API key for the LiteLLM proxy |
| `LITELLM_API_BASE` | Base URL of the LiteLLM proxy, e.g. `https://litellm.gratex.ai/` |

The script also calls `load_dotenv()` at startup, so you can either export the variables in your
shell profile (recommended below) **or** drop a `.env` file in the repo root (it is gitignored):

```dotenv
LITELLM_API_KEY="sk-your-key-here"
LITELLM_API_BASE="https://litellm.gratex.ai/"
```

Do not commit the key. `.env` is already in `.gitignore`.

### Linux (bash)

Append to `~/.bashrc`, then reload it:

```bash
echo 'export LITELLM_API_KEY="sk-your-key-here"' >> ~/.bashrc
echo 'export LITELLM_API_BASE="https://litellm.gratex.ai/"' >> ~/.bashrc
source ~/.bashrc
```

### macOS

The default shell is zsh, so use `~/.zshrc` (if you use bash, use `~/.bash_profile` instead):

```bash
echo 'export LITELLM_API_KEY="sk-your-key-here"' >> ~/.zshrc
echo 'export LITELLM_API_BASE="https://litellm.gratex.ai/"' >> ~/.zshrc
source ~/.zshrc
```

### Windows (PowerShell)

Persist the variables for your user account, then open a new terminal so they take effect:

```powershell
setx LITELLM_API_KEY "sk-your-key-here"
setx LITELLM_API_BASE "https://litellm.gratex.ai/"
```

For the current session only (no new terminal needed), use instead:

```powershell
$env:LITELLM_API_KEY = "sk-your-key-here"
$env:LITELLM_API_BASE = "https://litellm.gratex.ai/"
```

Confirm the variables are visible again on every OS:

```bash
uv run python -c "import os; print(bool(os.environ.get('LITELLM_API_KEY')), bool(os.environ.get('LITELLM_API_BASE')))"
```

This should print `True True`.

---

## 5. Run the grid search

From the repository root:

```bash
uv run python -m src.review.validate_judge.search grid
```

Useful options (all optional; defaults target the checked-in `dataset_short` snapshots):

- `--max_workers 8` — parallel judge calls per config (lower it if the proxy rate-limits you).
- `--datasets bgl hdfs thunderbird` — restrict the gold pool to a subset.
- `--root dataset_short` — directory holding the per-dataset gold files.
- `--gold_file gold_all_relabeled.json` — the final gold file (with the criterion-1 relabeling applied).
- `--split search|held_out|all` — which part of the gold split to score (default `all`). Rank configs with
  `--split search` (140 records, 2/3), then check the winner with `--split held_out` (70 records, 1/3).
  The split lives in `dataset_short/judge_split.json`; recreate it with
  `uv run python -m src.sampling.split_gold --gold_file gold_all_relabeled.json`. It is balanced on
  dataset x classification, with the human-fail counts per criterion spread evenly across both parts.

The search is resumable: it caches every config's judge output under `dataset_short/judge_runs/`
and continues where it left off, so a crash or `Ctrl-C` loses at most a few calls. Re-running the
same command picks up the cache instead of re-calling the models.

Example (restrict to two datasets and fewer workers):

```bash
uv run python -m src.review.validate_judge.search grid --datasets bgl hdfs --max_workers 4
```

---

## 6. Commit the changes after the script finishes

When the run terminates, it writes new/modified files that you should commit:

- `docs/llm_judge_validation_log.json` — new manifest entries (the best config and per-config scores).
- `dataset_short/judge_runs/` — the per-config run files. These are currently **not** gitignored, so
  decide whether you want to track them; if not, add the directory to `.gitignore` before committing.

Inspect and commit from the repository root:

```bash
git status
git add docs/llm_judge_validation_log.json dataset_short/judge_runs
git commit -m "Add judge-config grid search results"
```

If you would rather not commit the run cache, add it to `.gitignore` first:

```bash
echo 'dataset_short/judge_runs/' >> .gitignore
git add .gitignore docs/llm_judge_validation_log.json
git commit -m "Add judge-config grid search results"
```