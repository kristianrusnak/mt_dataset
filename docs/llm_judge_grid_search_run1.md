# Judge-config grid search, run 1 (2026-10-12): results and interpretation

Written for: whoever needs the evidence trail behind the `llm_as_judge` validation (thesis write-up, supervisor
review). Plan context: step 3 and 4 of [llm_judge_validation_plan.md](llm_judge_validation_plan.md). Raw
numbers: `docs/llm_judge_validation_log.json` (83 `llm_as_judge_run` entries and one `grid_search` entry) and
`dataset_short/judge_runs/` (one file per config). Everything below was recomputed from those run files and the
gold labels; the winner's score matches the manifest exactly (0.2746).

## Setup

- **80 configurations**: 6 models (deepseek-v4.1-flash, qwen3.8-flash-next, qwen3.8-27b, glm-5.3-flash,
  minimax-m2.5, laguna-s-2.1) x 5 temperatures (0, 0.25, 0.5, 0.75, 1.0) x reasoning effort none/low/medium
  (minimax: none only). Each model has its own prompt; the rubric, rules and brevity note are identical in
  all six (about 85-90% of each prompt's sentences are shared word for word).
- **Gold pool**: 210 records (70 per dataset: 30 natural + 40 supplemental; 105 normal, 105 abnormal), scored
  on the 5 binary criteria. 90 are the natural core, the stratum the plan names as the headline.
- **Metric**: fitness = mean over the 5 criteria of Youden's J = (share of human fails the judge catches) -
  (share of human passes the judge wrongly fails). 0 means no better than ignoring the input, 1 is perfect.
  FNR (false-negative rate) = share of human fails the judge passes.
- **Caveat on the headline metric**: the search ranks on all 210 records. The plan says natural-only is the
  headline. The winner's natural-only fitness is 0.243 and the order shifts slightly (see ranking).

## Headline

**No configuration is good enough to stand in for the human reviewer.** The best catches about a third of what
was marked as a failure.

| Rank | Config | Fitness | Natural-only | Agreement | Mean kappa | FNR |
|---|---|---|---|---|---|---|
| 1 | deepseek, t=0.25, medium | 0.275 | 0.243 | 0.849 | 0.308 | 0.659 |
| 2 | deepseek, t=0.50, low | 0.264 | 0.224 | 0.847 | 0.294 | 0.682 |
| 3 | deepseek, t=0.75, medium | 0.255 | 0.226 | 0.839 | 0.278 | 0.700 |
| 4 | deepseek, t=1.00, medium | 0.252 | 0.215 | 0.835 | 0.268 | 0.700 |
| 5 | deepseek, t=0.50, medium | 0.247 | 0.203 | 0.841 | 0.277 | 0.694 |
| 11 | qwen3.8-flash-next, t=0.25, medium (best non-deepseek) | 0.201 | 0.175 | 0.863 | 0.261 | 0.759 |

- **Agreement is misleading here.** Humans pass 83.8% of all ratings, so a judge that always says PASS already
  agrees 84%. Laguna does nearly that (agreement 84%, 98-99% of fails missed). Best configs beat it by about one
  point.
- **Precision is high, recall is low.** The winner wrongly fails only 2-8% of human passes per criterion, but
  misses 54-77% of human fails. At record level it flags 45 of the 88 records with at least one human fail and
  wrongly rejects 22 of 122 clean ones. Use: its FAIL is informative, its PASS is not evidence of quality.

## What drives the ranking

| Axis | Finding |
|---|---|
| Model | Mean fitness: deepseek 0.200, qwen-flash-next 0.146, qwen-27b 0.100, glm 0.078, minimax 0.022, laguna 0.018. Bootstrap (300 resamples) puts the winner's interval at 0.20-0.38; it beats the best non-deepseek config in 100% of resamples. Prompt and model are confounded by design. |
| Reasoning effort | none 0.057, low 0.130, medium 0.132 (means over all models). For deepseek: none 0.111, low 0.236, medium 0.254. Reasoning roughly doubles the score; low and medium are indistinguishable. Laguna is the exception (no effect, since it never discriminates). |
| Temperature | No effect. Mean fitness at 0 / 0.25 / 0.5 / 0.75 / 1.0 is 0.102 / 0.105 / 0.106 / 0.099 / 0.103; the spread across temperatures within one model and effort is 0.01-0.03. The winning t=0.25 is noise: the winner beats other deepseek low/medium configs in only 67-99% of resamples. |
| Reliability | glm at effort none returned unusable output on 4-10 of 210 records per config. Two glm runs lost records to transport errors (t=0.5 medium 18, t=0.0 low 10); the evaluator's rule discards a config above 5% missing, which would discard the first. Neither is competitive. |

Defensible conclusion: **deepseek, effort low or medium, any temperature**, not "t=0.25".

## Where the judge fails

Winner, per criterion (human fails among the 210 in brackets):

| Criterion | Human fails | Judge misses them | J |
|---|---|---|---|
| 1 Root cause | 60 | 73% | 0.25 |
| 2 Sequence summary | 13 | 77% | 0.15 (small sample) |
| 3 Contrast | 50 | 54% | 0.41 |
| 4 Groundedness | 19 | 68% | 0.24 |
| 5 Speculation | 28 | 64% | 0.32 |

Per dataset (mean of the 10 deepseek low/medium runs): Thunderbird fitness 0.39 (miss rate 53%), HDFS 0.22
(76%), BGL 0.08 (83%). Root-cause fails sit almost entirely in abnormal sequences (59 of 60).

Causes found by reading cases:

1. **Tagged datasets (BGL, Thunderbird): the judge tests only "is the cited line tagged [abnormal]?"** It passes
   explanations whose sentence 1 names the real driver together with a [normal]-tagged line ("data storage
   interrupt interleaved with instruction address"). Where sentence 1 mentions a [normal] line, criterion 1 was
   failed in 24 of 28 BGL and 15 of 18 Thunderbird records; where it does not, 0 of 17 on Thunderbird (BGL has
   only 4 such records). The judge's mean fail rate on those same records was 14% (BGL) and 38% (Thunderbird).
2. **Untagged dataset (HDFS): the judge cannot see what normal looks like.** The reviewer failed 16 abnormal
   blocks for blaming events that most normal blocks also contain. Checked on the gold data: `invalidSet` is in
   30 of 35 normal blocks, `Deleting block` in 31, `Got exception while serving` in 25, while the replication
   request is in 1 of 35 normal and 17 of 35 abnormal; all 16 criterion-1 fails contain it, against 1 of 19
   passes. These labels are correct; the information needed to apply them is not in the judge's prompt. Measured
   on the full dataset (duplicates capped, gold records excluded): `Deleting block` 95% of normal blocks,
   `invalidSet` 93%, `Got exception while serving` 78%, replication request 3%.
3. **Criteria 1 and 3 fail together.** 43 of 60 human criterion-1 fails are also criterion-3 fails (phi 0.71; HDFS
   0.89), because sentence 3 usually repeats sentence 1's cause. When the judge flags criterion 1, 18 of 19 are
   also human criterion-3 fails. The shared prompt rule "score every criterion independently" ignores this.
4. **The prompts lean lenient.** Each has 7 "do not fail for..." cues (brevity, paraphrase, omissions) and 0-1
   strictness cues, no tie-break instruction, and criterion 1's PASS says only "plausibly". No prompt has a worked
   example. The scratchpad field in the output schema is never used.
5. **More sampling does not fix it.** Combining the 10 deepseek low/medium runs and failing a criterion if any run
   fails lifts fitness only from 0.275 to 0.349 (FNR still 54%; tested on the same data, so optimistic). The misses
   are systematic.

## Audit of the human labels (found while interpreting)

The gold "human" labels are largely Claude's pre-review scores, confirmed by the reviewer. This is not recorded in
the manifest.

- `dataset_short/<dataset>/gold_*_prescored.json` hold a `claude_pre_review` score vector (Claude Sonnet 5 for
  BGL, Sonnet 5.5 for HDFS and Thunderbird) with a note per record; the reviewer's tool shows these as defaults.
  The final labels equal the pre-scores in every criterion for HDFS (350/350, all 70 records), 345/350 for
  Thunderbird and 333/350 for BGL. All 22 changes are PASS -> FAIL, none FAIL -> PASS. Median gap between
  submitted reviews: 31 s (Thunderbird), 41 s (HDFS), 57 s (BGL).
- **BGL criterion 1**: 14 labels went from pre-score PASS to FAIL; 8 notes say "Criterion-1 mixing audit (agreed
  in chat discussion, applied by Claude)", some beside a note that still reads "Clean". This applies a rule that is
  not in the rubric text.
- **The rule is applied consistently** (see cause 1 above), so it is a de facto standard, not noise.
- **The labels also contain misses.** For BGL 8da27e65, a69f79cf and a459858d the explanation says the lines
  "alternate"; the real order has runs of 4-6 identical lines (or two separate blocks). The judge flagged these,
  the label passed them (criterion 2).
- **Effect on the result is small.** Scoring against the raw pre-scores gives the winner 0.290; reverting only the
  14 BGL flips gives 0.291 (from 0.275). Label noise does not explain the low recall.
- Consequence for the thesis claim: "the judge agrees with the human" must be stated as agreement with a
  Claude-seeded, human-confirmed label set, or re-measured on a blind re-review (about 30 records, no defaults).

## Decision on ambiguous criterion-1 cases (confirmed 2026-10-16: FAIL)

Ambiguous = sentence 1 names the real abnormal line and also a [normal]-tagged line. **Rule: FAIL.** Criterion 1
asks what drove the classification, and a [normal] line did not; this matches 39 existing labels and changes 8,
against about 39 changes for the opposite choice. The reviewer confirmed the rule rather than re-reviewing.

- **Applied to a new file**, `dataset_short/<dataset>/gold_all_relabeled.json`, by
  `src/help_functions/relabel_gold.py`; `gold_all_human_reviewed.json` is untouched. Eight criterion-1 labels
  changed PASS -> FAIL: BGL 10d9fc41, a9933c38, 57355eea, 6551600f; Thunderbird 3163b498, 1258081d, dcd69dc0,
  de635f21. HDFS is copied unchanged. Each changed record carries a `label_revisions` entry stating the rule, date
  and who applied it, so the file shows which labels are no longer the reviewer's original click.
- Found by matching sentence 1 against the [normal]-tagged templates (a strict and then a looser matcher), then
  reading every hit. The looser pass added dcd69dc0 and de635f21; its other hit was a false match. A few mentions
  could still be missed by word matching, so the count is a floor.
- **Effect on run 1 is negligible**: human criterion-1 fails 60 -> 68; the winner's fitness 0.275 -> 0.277; model
  order unchanged (deepseek 0.245, qwen-flash-next 0.179, qwen-27b 0.118, glm 0.092, laguna 0.015; low and medium
  effort means). Cached judge runs stay valid, because their fingerprint covers what the judge saw, not the labels.
- **Not written into the shared rubric** (`review_criteria.py`): that text is part of every prompt's cache
  fingerprint, and editing it would invalidate all 80 saved runs. It lives in the v2 prompt as judge-side wording.
- Use it with `search ... --gold_file gold_all_relabeled.json`.

## Changes made after this run (not yet evaluated)

- `src/prompts/judge_criteria/deepseek_v2.py` and `deepseek_v2_cot.py`: attribution check using the tags,
  a reference table for HDFS, criteria 1/3 handled from one shared piece of evidence, two worked examples per
  dataset type (synthetic), and for `_cot` a scratchpad audit before the verdicts. Rubric text unchanged.
- `src/help_functions/build_hdfs_profile.py` -> `src/prompts/judge_criteria/hdfs_profile.json`: per-event share
  of normal and anomalous HDFS blocks (29,262 blocks counted, 231 cross-class sequences dropped, gold excluded).
- `gold.py` / `search.py`: new `--gold_file` option (default unchanged) so the search can score against
  `gold_all_relabeled.json`.
- `judge.py`: the prompt fingerprint now also covers HDFS-only prompt text; the six original prompts keep
  identical fingerprints, so the 80 cached runs are still valid.
- `search_space.json`: added `deepseek_v2` and `deepseek_v2_cot` with efforts low and medium only. A `grid` run now
  covers 100 configs but only the 20 new ones need calls (about 4,200 judge calls).

Caveat: the v2 rules and examples were written after reading the failures in this same gold pool, so a good v2
score on it will be optimistic; a fresh sample is needed for an honest estimate.

## Open items

1. ~~Confirm the fail rule and apply the label changes~~ done, see above.
2. Decide whether to disclose the Claude pre-review as is, or re-measure the human baseline blind on about 30
   records (a random draw from the natural core, about 10 per dataset, scored without the pre-score defaults).
3. Run the 20 new configs with `--gold_file gold_all_relabeled.json`, then report natural-only first.
4. Disclose in the write-up: criterion 1/3 results are validated mostly against the BGL/Thunderbird mixing
   pattern and the HDFS common-event pattern, not every way a cause can be wrong.
