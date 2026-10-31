<!--
Generated/modified by AI Kilo Code 7.8.17-gratex-023, used model gti-litellm/mimo-2.6-flash.
-->

# Production Judge — Run Guide (Windows / macOS / Ubuntu)

**Generated/modified by AI Kilo Code 7.8.17-gratex-023, used model gti-litellm/mimo-2.6-flash.**

This guide takes you from a clean machine to a finished production judging run of all three
datasets (`bgl`, `hdfs`, `thunderbird`), one after another, each with **8 parallel judge calls**
and **only one dataset running at a time**.

The script it runs is `src/review/llm_as_judge/production_judge.py`. It applies the already-chosen
final judge config — `deepseek-v4.1-flash`, temperature `0.25`, prompt `deepseek_v7`, effort
`high` — to every record of `dataset_short/<dataset>/production_explained.json` and stores the 5
per-criterion verdicts (+ evidence) in `metadata.hallucination-check`. It only records verdicts;
the accept/reject rule is decided later.

It is **resumable**: every finished verdict is appended to `<output>.verdicts.jsonl` right away,
so a crash, a `Ctrl-C`, or a network outage costs at most a few calls — re-running the same
command continues from the cache.

**Related docs:** [README.md](../README.md) (pipeline overview),
[validate_judge_grid_search_guide.md](validate_judge_grid_search_guide.md) (how the judge config
was chosen and how to install `uv` in more detail).

---

## 1. Everything that must be installed and set before you start

Work through this checklist first; the later sections show the exact commands.

| # | Requirement | Why it is needed | How you verify it |
|---|-------------|------------------|-------------------|
| 1 | `git` | to clone the repository | `git --version` |
| 2 | `uv` | package runner; it also downloads Python automatically | `uv --version` |
| 3 | Python 3.12 | pinned in `.python-version` — **you do not install it yourself**, `uv sync` pulls it | `uv run python --version` prints `3.12.x` |
| 4 | Network access to the LiteLLM proxy (`https://litellm.gratex.ai/`) | every judge call goes through it | you can open the URL in a browser |
| 5 | `LITELLM_API_KEY` + `LITELLM_API_BASE` in the environment | the script exits with `... is not set` otherwise | preflight check in §6 prints `env_ok = True` |
| 6 | The model `deepseek-v4.1-flash` available on that proxy, with enough credit | it is the final judge model; ~6000 calls for a full run | a successful smoke test (§7) |
| 7 | Input files `dataset_short/bgl/production_explained.json`, `.../hdfs/...`, `.../thunderbird/...` | default input of the script (2000 records each) | preflight check in §6 prints `inputs_ok = True` |
| 8 | You run every command **from the repository root** | modules are imported via the `src.` package path | your prompt is in `mt_dataset/`, not in `src/` |
| 9 | Only **one** judge run at a time | keeps the parallelism at exactly 8 calls and avoids two processes appending to the same manifest | close extra terminals running the judge |
| 10 | A few hundred MB of free disk | output JSON + growing verdict caches | `df -h` / Explorer |

Notes:

- `OPENAI_API_KEY` is **not** needed for the judge — it talks only to the LiteLLM proxy.
- The default config flags (`--model`, `--temperature`, `--prompt_id`, `--effort`) are already the
  final chosen ones. **Do not override them** unless you are deliberately re-running an experiment.
- If `dataset_short/<dataset>/production_explained.json` is missing for a dataset, generate it
  first with the creation step described in [README.md](../README.md) (`production_creation`).

---

## 2. Get the code

All three operating systems:

```bash
git clone https://github.com/kristianrusnak/mt_dataset.git
cd mt_dataset
```

If you already have the repository, just `cd` into its root. Every later command assumes the
current directory is the repository root.

---

## 3. Install `uv` (skip if already installed)

Check first:

```bash
uv --version
```

If that prints a version, skip to §4.

### Windows (PowerShell)

Paste this into **PowerShell** and press Enter:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv --version
```

Then **open a brand-new terminal** (the installer updates `PATH` for new sessions only). If the
second line still says `'uv' is not recognized`, close and reopen Windows Terminal, then run
`uv --version` again.

### macOS

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

### Ubuntu

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

---

## 4. Install the Python dependencies

Identical on all three systems, run from the repository root:

```bash
uv sync
```

This creates `.venv` and installs exactly the locked dependencies from `uv.lock` (it also downloads
Python 3.12 on the first run). Verify the wiring without spending any LLM calls:

```bash
uv run python -m src.review.llm_as_judge.production_judge --help
```

If that prints the usage/option list, the installation is complete.

---

## 5. Set the two environment variables

The script needs exactly two variables:

| Variable | Value |
|----------|-------|
| `LITELLM_API_KEY` | your proxy API key, e.g. `sk-...` |
| `LITELLM_API_BASE` | `https://litellm.gratex.ai/` |

### 5a. Recommended for everyone: a `.env` file (works identically on Windows, macOS, Ubuntu)

Create a file named `.env` **in the repository root** (it is gitignored — never commit it):

```dotenv
LITELLM_API_KEY="sk-your-key-here"
LITELLM_API_BASE="https://litellm.gratex.ai/"
```

The script calls `load_dotenv()` at startup, so no shell setup and no terminal restart is needed.
If you use this file, you can skip 5b–5d.

### 5b. Windows — persist for the current user (PowerShell)

```powershell
setx LITELLM_API_KEY "sk-your-key-here"
setx LITELLM_API_BASE "https://litellm.gratex.ai/"
```

`setx` affects **new** processes only: open a new terminal before continuing. Do not use `setx`
for very long values (it truncates at 1024 characters).

### 5c. Windows — current session only (PowerShell, no restart needed)

```powershell
$env:LITELLM_API_KEY = "sk-your-key-here"
$env:LITELLM_API_BASE = "https://litellm.gratex.ai/"
```

### 5d. macOS (zsh by default; use `~/.bashrc` instead if your shell is bash)

```bash
echo 'export LITELLM_API_KEY="sk-your-key-here"' >> ~/.zshrc
echo 'export LITELLM_API_BASE="https://litellm.gratex.ai/"' >> ~/.zshrc
source ~/.zshrc
```

### 5e. Ubuntu (bash)

```bash
echo 'export LITELLM_API_KEY="sk-your-key-here"' >> ~/.bashrc
echo 'export LITELLM_API_BASE="https://litellm.gratex.ai/"' >> ~/.bashrc
source ~/.bashrc
```

---

## 6. Preflight check (paste on any OS)

This single line checks both environment variables **and** all three input files. It must print
`env_ok = True` and `inputs_ok = True`:

```bash
uv run python -c "import os, pathlib; print('env_ok =', bool(os.environ.get('LITELLM_API_KEY')) and bool(os.environ.get('LITELLM_API_BASE'))); print('inputs_ok =', all(pathlib.Path('dataset_short', d, 'production_explained.json').exists() for d in ('bgl', 'hdfs', 'thunderbird')))"
```

- `env_ok = False` → go back to §5 (and open a **new** terminal if you used `setx`).
- `inputs_ok = False` → you are in the wrong directory, or that dataset still has to be generated
  (see [README.md](../README.md)).

---

## 7. Smoke test (5 records, cheap) **Skippable**

Run this once before the full run. It judges only the first 5 records of `bgl` and writes to its
own file, so it cannot damage any real output:

```bash
uv run python -m src.review.llm_as_judge.production_judge --dataset bgl --max_workers 8 --limit 5 --output_path dataset_short/bgl/production_judged.smoke.json
```

Expected ending: a `Done: {...}` line with `failed: 0` and the file
`dataset_short/bgl/production_judged.smoke.json`. If that works, the key, the proxy, the model and
the inputs are all good.

(The smoke run keeps its own cache file, `production_judged.smoke.json.verdicts.jsonl`, so its 5
calls are paid again during the full run.)

---

## 8. The full production run — 8 workers, one dataset at a time

What the commands below do:

- `--max_workers 8` — exactly **8 judge calls in parallel**, never more (8 is also the default).
- **One dataset runs at a time**: `bgl` first, then `hdfs`, then `thunderbird`, each started
  **immediately** when the previous one finishes — no waiting, no manual restart in between.
- Each dataset has its own input, output and cache file, so the three runs cannot collide.
- Expect ~2000 judge calls per dataset (~6000 total, minus whatever is already cached).

> Tip: re-running the *same* command after an interruption is always safe — it resumes from the
> verdict cache instead of re-judging finished records.

### Windows (PowerShell) — copy-paste block

Paste the whole block below into PowerShell and press Enter. The three lines run back-to-back:
when `bgl` finishes, `hdfs` starts immediately, and when `hdfs` finishes, `thunderbird` starts
immediately. Nothing else needs to be typed.

```powershell
uv run python -m src.review.llm_as_judge.production_judge --dataset bgl --max_workers 8
uv run python -m src.review.llm_as_judge.production_judge --dataset hdfs --max_workers 8
uv run python -m src.review.llm_as_judge.production_judge --dataset thunderbird --max_workers 8
```

This plain form is valid in **Windows PowerShell 5.1, PowerShell 7, and Command Prompt (cmd.exe)**
— it deliberately avoids `&&`, which Windows PowerShell 5.1 does **not** support.

Equivalent one-liner (PowerShell only, same order, same 8 workers):

```powershell
foreach ($ds in "bgl", "hdfs", "thunderbird") { uv run python -m src.review.llm_as_judge.production_judge --dataset $ds --max_workers 8 }
```

### macOS (bash/zsh) — copy-paste block

```bash
uv run python -m src.review.llm_as_judge.production_judge --dataset bgl --max_workers 8
uv run python -m src.review.llm_as_judge.production_judge --dataset hdfs --max_workers 8
uv run python -m src.review.llm_as_judge.production_judge --dataset thunderbird --max_workers 8
```

Equivalent loop (runs the three datasets strictly one after another):

```bash
for ds in bgl hdfs thunderbird; do
  uv run python -m src.review.llm_as_judge.production_judge --dataset "$ds" --max_workers 8
done
```

### Ubuntu (bash) — copy-paste block

```bash
uv run python -m src.review.llm_as_judge.production_judge --dataset bgl --max_workers 8
uv run python -m src.review.llm_as_judge.production_judge --dataset hdfs --max_workers 8
uv run python -m src.review.llm_as_judge.production_judge --dataset thunderbird --max_workers 8
```

Equivalent loop:

```bash
for ds in bgl hdfs thunderbird; do
  uv run python -m src.review.llm_as_judge.production_judge --dataset "$ds" --max_workers 8
done
```

Want only some datasets? Delete the lines you do not want, or edit the list in the loop
(`bgl hdfs thunderbird`) — the order is yours to choose.

Stop a run with `Ctrl-C`; restart it with the same command to resume.

---

## 9. What the run writes

For each dataset:

| File | Meaning |
|------|---------|
| `dataset_short/<ds>/production_judged.json` | the final judged dataset (written atomically at the end) |
| `dataset_short/<ds>/production_judged.json.verdicts.jsonl` | verdict cache; grows during the run, enables resume |
| `dataset_short/<ds>/production_judged.json.tmp` | half-written output; disappears on success (`os.replace` swaps it in) |

Plus one manifest entry appended to `docs/llm_judge_validation_log.json` per run (step 6,
`llm_as_judge_production_run`) with per-criterion pass rates.

Progress you will see:

- `judge failed for <id>: ...` — a single call failed; the record gets
  `verification_status: "judge_failed"` and is retried automatically on the next run.
- a final `Done: {'total': ..., 'computed': ..., 'from_cache': ..., 'failed': ...}. Wrote ...`
  line when a dataset is finished — that is the moment the next dataset in the block starts.

---

## 10. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `'uv' is not recognized` (Windows) | open a **new** terminal after installing; check `%USERPROFILE%\.local\bin` is on `PATH` |
| `LITELLM_API_KEY is not set (put it in .env or export it).` | §5 — `.env` in the repo root, or a new terminal after `setx` |
| `ModuleNotFoundError: No module named 'src'` | you are not in the repository root — `cd` into it and rerun |
| `FileNotFoundError: .../production_explained.json` | wrong directory, or the explanations were not generated yet (§1 note) |
| Proxy timeouts / `429` / repeated `judge failed` | the proxy is rate-limiting or overloaded: rerun the **same** command (it resumes), or lower `--max_workers` to `4` |
| Output file is missing after a crash | normal — the output is swapped in only at the end; the cache `.verdicts.jsonl` keeps the finished verdicts, so a rerun continues |
| Two runs were started in two terminals | stop the extra one; only one judge process should run at a time (§1 item 9) |
| PowerShell pasted the block but only the first line ran | press Enter once to flush a partial paste, then paste again; or use the `foreach` one-liner |