# Production judge run: results report

What the validated LLM judge said about every explanation in the three production sets
(BGL, HDFS, Thunderbird). Numbers come from `dataset_short/<ds>/production_judged.json` and the
step-6 entries of `docs/llm_judge_validation_log.json`.

**Terms used below**

- **Sequence**: one record of the dataset, a window or block of log lines plus the LLM-written
  explanation and the original normal/abnormal label.
- **Judge**: a second LLM (`deepseek-v4.1-flash`, temperature 0.25, reasoning effort `high`, prompt
  `deepseek_v7`) that grades each explanation on 5 yes/no criteria. The explanations themselves were
  written by `azure/gpt-6-luna`.
- **Pass / fail**: for each criterion the judge answers "correct" (pass) or "incorrect" (fail).
  Nothing is accepted or rejected yet; the keep/drop rule is decided later from these verdicts.
- **The 5 criteria**: root cause correctness (sentence 1), sequence summary correctness (sentence 2),
  contrast correctness (sentence 3, why the opposite verdict does not apply), groundedness (nothing
  invented), speculation bounded (no guessing beyond the logs).

## 1. Coverage

| Dataset | Sequences in | Judged | Judge call failures | Normal / abnormal |
|---|---|---|---|---|
| BGL | 2000 | 2000 | 0 | 1000 / 1000 |
| HDFS | 2000 | 2000 | 0 | 1000 / 1000 (label is `anomaly`) |
| Thunderbird | 2000 | 2000 | 0 | 1713 / 287 |

6000 of 6000 sequences have all five verdicts. Every record has status `verified` and none is
`judge_failed`. Thunderbird is not balanced because abnormal windows are rare in the source data.

## 2. Headline: how many explanations passed everything

| Dataset | Passed all 5 criteria | Failed 1 | Failed 2 | Failed 3 |
|---|---|---|---|---|
| BGL | **1939 (97.0%)** | 49 | 12 | 0 |
| HDFS | **987 (49.4%)** | 551 | 428 | 34 |
| Thunderbird | **1856 (92.8%)** | 107 | 35 | 2 |
| **All** | **4782 (79.7%)** | 707 | 475 | 36 |

## 3. Pass rate per criterion

| Criterion | BGL | HDFS | Thunderbird |
|---|---|---|---|
| Root cause correctness | 99.7% | **78.3%** | 97.8% |
| Sequence summary correctness | 99.2% | 97.3% | 96.8% |
| Contrast correctness | 98.1% | **52.7%** | 97.9% |
| Groundedness | 99.5% | 98.0% | 98.4% |
| Speculation bounded | 99.9% | 98.4% | 99.95% |

## 4. Interesting facts

### HDFS is the outlier, and the problem is mostly one criterion

- 947 of the 1013 HDFS failures involve **contrast correctness** (sentence 3). The most common failure
  is contrast alone (485), then root cause + contrast together (396).
- The split by label is large: **65.2%** of normal HDFS blocks pass everything, but only **33.5%** of
  anomalous ones do. For anomalous blocks, contrast fails 628 times and root cause 426 times (out of 1000).
- BGL and Thunderbird sit at 93-97%, so this is specific to HDFS, not to the pipeline in general.

### Why HDFS is judged harder (likely, not proven)

- The HDFS judge prompt includes a **frequency table**: for each log template, the share of normal blocks
  and of anomalous blocks that contain it (`src/prompts/judge_criteria/hdfs_profile.json`).
- The judge's fail reasons often say the explanation blames an event that is common in normal blocks.
  Example (`36a88551-...`): the explanation names deletions and invalidations as the cause of the
  anomaly, but the judge notes "Deleting block" and "NameSystem.delete" occur in 95% / 93% of normal
  blocks, so they cannot be what distinguishes this block. The real discriminating event, a
  replication request, was not named.
- The explanations for HDFS were generated without per-line normal/abnormal tags (`hdfs/prompt1.py`),
  while BGL/Thunderbird used `bgl/prompt2.py`, which shows each line's tag. So for HDFS the writer had
  to guess which line mattered, and the judge, which has the frequency table, can check that guess.
  This is the most plausible explanation for the gap, but it was not tested by an experiment.

### Different datasets fail in different ways

- **BGL**: almost all failures are contrast on *normal* windows (38 of 61 failing records). Typical
  complaint: sentence 3 only restates the tags ("no [abnormal] event; every entry is tagged [normal]")
  instead of pointing at something concrete in the logs, so the judge calls it circular.
  Abnormal BGL windows pass 98.9% of the time versus 95.0% for normal ones.
- **Thunderbird**: failures are spread out, and the biggest single group is the **sequence summary**
  (64): wrong counts. Example (`e45770df-...`): the explanation says "two pairs" of SSH session
  openings and key acceptances, but the logs show three (lines 4-5, 6-7, 19-20).
- **Speculation bounded** is nearly always fine: 1 failure in Thunderbird, 2 in BGL, 32 in HDFS.

### Failures usually come alone, except in HDFS

- BGL: 49 of 61 failing records (80%) fail a single criterion. Thunderbird: 107 of 144 (74%).
- HDFS: 428 of 1013 failing records fail two criteria, and 396 of those are the root cause + contrast
  pair. That makes sense, because if the stated cause is wrong, the contrast sentence usually builds
  on the same mistake.

### Sequence length

BGL and Thunderbird windows are always exactly 20 lines. HDFS blocks vary: mean 27.3, median 26, max 268.

## 5. How far to trust these verdicts

The judge was checked against human labels on 70 held-out records (`step 5` in the validation log):

| Measure | Value | Meaning |
|---|---|---|
| Overall agreement with humans | 88.9% | share of individual verdicts that match |
| Cohen's kappa (overall) | 0.55 | agreement beyond what chance would give; 0 = chance, 1 = perfect |
| Missed fails (false negative rate) | 15% | humans said fail, judge said pass |

Per criterion on that held-out set:

| Criterion | Agreement | Kappa | Fails the judge missed |
|---|---|---|---|
| Root cause | 97.1% | 0.93 | 2 of 23 |
| Contrast | 85.7% | 0.66 | 2 of 18 |
| Speculation bounded | 88.6% | 0.63 | 0 of 9 |
| Groundedness | 85.7% | 0.30 | 3 of 6 |
| Sequence summary | 87.1% | 0.25 | 2 of 4 |

What this means for the numbers above:

- Root cause and contrast are the two criteria the dataset is built around, and the judge is reliable on
  them. The HDFS finding (low contrast and root cause pass rates) therefore rests on the strongest part
  of the judge.
- Groundedness and sequence summary are weak (kappa 0.25 to 0.30), so their high pass rates probably hide
  some real errors. Humans failed these rarely, so the impact is small but the true pass rate is likely a
  little lower than shown.
- The held-out set is only 70 records, so these agreement figures are rough.
- By dataset on that set, agreement was 91.7% (BGL), 85.2% (HDFS) and 89.6% (Thunderbird).
- The judge could be over-strict on HDFS. Its contrast and root cause failures lean on the frequency
  table, and that check has not been validated separately.

## 6. Suggested next steps

1. Decide the accept/reject rule. A rule based on root cause + contrast alone would match the
   dataset's purpose and the judge's reliability.
2. For HDFS, look at a sample of judge failures by hand to confirm the strictness is justified, then
   either regenerate those explanations (for example with a prompt that shows the frequency table or
   per-line tags) or drop them.
3. Check how many HDFS records remain per class once failures are removed, so the final HDFS set
   stays balanced.

## Reproduce

```bash
uv run python -m src.review.llm_as_judge.production_judge --dataset <bgl|hdfs|thunderbird> --max_workers 8
```

Full setup steps are in [production_judge_guide.md](production_judge_guide.md).
