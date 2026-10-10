# Validating `llm_as_judge` against human review

Status: raw idea / draft plan, not implemented yet. Written down for later work.

## Problem

The pipeline generates a causal explanation for each sampled window/block
(`src/explanation_creation/<dataset>/creation1.py`), then verifies it with an
LLM judge (`src/review/llm_as_judge/<dataset>/llm_as_judge.py`) before it's
accepted into the final dataset. Right now nothing establishes that the judge
itself is trustworthy — we'd be using an unvalidated LLM to certify the output
of another LLM. To make an academic/rigorous claim about dataset quality, we
need evidence that `llm_as_judge` verdicts agree with human verdicts closely
enough to stand in for a human reviewer at scale.

## Goal

Before running `llm_as_judge` as the sole verification step over the full
sampled datasets, empirically pick the judge configuration (model, prompt,
temperature) whose verdicts best match human verdicts, and report the
agreement as evidence the automated judge is a valid substitute.

## Documentation practice

Every step below must be logged as it's actually carried out, not just
planned — this is what makes the eventual "the judge agrees with humans"
claim auditable. Log to a single append-only JSON manifest,
`docs/llm_judge_validation_log.json`, rather than scattering per-step
files: one array, one schema, easy to grep/parse in a later session. This
mirrors the provenance pattern the pipeline already uses for
`metadata.llm` / `metadata.hallucination-check` in `window_template.py`, so
it stays consistent with the rest of the repo.

Each entry in the manifest's array = one concrete action taken (a sampling
run, a human-review pass, one judge config's run, one scoring pass, a
final decision), with a schema along these lines:

```jsonc
{
  "step": 3,                     // which of the numbered steps below this belongs to
  "action": "llm_as_judge_run",  // short machine-readable action type
  "timestamp": "2026-08-01T12:00:00Z",
  "dataset": "thunderbird",      // bgl | thunderbird | hdfs | "all"
  "params": {                    // whatever config produced this action
    "model": "...",
    "temperature": 0.0,
    "prompt_id": "...",
    "search_algorithm": "pso"    // null for manual/cartesian runs
  },
  "inputs": ["path/to/input.json"],
  "outputs": ["path/to/output.json"],
  "metrics": {                   // filled in once scored (step 4)
    "agreement": null,
    "kappa": null,
    "false_negative_rate": null
  },
  "notes": ""                    // rationale, anomalies, anything not captured above
}
```

Exact field list can evolve, but keep it append-only and keep every run —
including failed/discarded configs — so the final "why this config won"
writeup can point at the full search trace, not just the winner.

## Explanation template

The generation prompt (`src/prompts/<dataset>/prompt1.py`) is still a
working prototype (see CLAUDE.md) and currently produces a free-form 1-2
sentence explanation. The criteria below assume a revised, fixed
3-sentence template that the generation prompt still needs to be updated
to produce:

> **This sequence is `<normal/abnormal>` because `<root cause>`. `<sequence
> summary>`. `<why not the opposite>`.**

| Sentence | Answers | Content |
|---|---|---|
| 1 — Root cause | "What specifically drove this verdict?" | The concrete log-grounded cause — a specific event/error/pattern, not a category label restated. |
| 2 — Sequence summary | "What actually happens across the window, briefly?" | A short, neutral pass over what the sequence shows as a whole (flow/ordering), so the explanation isn't just about one line in isolation. |
| 3 — Contrast | "Why does this not read as the opposite verdict?" | The discriminating detail that rules out the other label — e.g. why an error-looking line didn't make it abnormal, or why a routine-looking sequence didn't make it normal. |

*Illustrative example (not real dataset content):* "This sequence is
abnormal because a kernel TLB miss handler repeatedly failed to resolve a
page fault on node R04. Across the window, the node logs three consecutive
retry attempts on the same address before halting further scheduling. This
is not a routine retry, unlike the transient retries seen elsewhere in the
log, because the failure recurs on the identical address without ever
succeeding."

**Done.** `src/prompts/bgl/prompt1.py` and `src/prompts/hdfs/prompt1.py` (and
Thunderbird, which imports the BGL one) now enforce this 3-sentence contract,
and CLAUDE.md's prompt contract section reflects it.

At the same time, BGL/Thunderbird generation stopped receiving per-log
ground-truth classifications (previously fed in alongside the final verdict,
derived from the raw line's `-`/non-`-` first column) — the model had been
handed the exact anomalous line, which made explaining "why" closer to
transcription than reasoning and risked near-zero natural errors for judge
calibration (no fail cases to test the judge against). HDFS already worked
this way (block-level classification only). The judge prompt
(`judge_prompt.py`) is unchanged in this respect — it still gets full per-log
labels, since its job is fact-checking against ground truth, not reasoning
about the sequence.

**Clarification (2026-08-08): this blind-generation choice is scoped to
gold-set generation only, not the eventual delivered dataset.** It exists
purely to maximize the diversity of naturally-occurring failures available
for judge calibration in this doc (see "Sampling population" below) — it is
not a requirement that the final large-scale dataset's generation must also
be blind. That dataset (step 6's "production set") is never read by whatever
it's used to evaluate — it's ground-truth explanation text used to score an
agentic AI's own output, not an input the agentic AI reasons over — so there
is no realism/parity constraint on how it's generated. Feeding per-log
ground-truth labels into *that* generation step is expected, and intended:
it directly attacks this project's dominant observed failure mode
(root_cause_correctness) and produces a more accurate answer key. See the
terminology note under step 6 and the new Open Question on judge-calibration
transfer for the one consequence this has on how step 4/5's agreement
numbers should be read.

## Judging criteria (binary vector)

Both the human reviewer (step 2) and `llm_as_judge` (step 3) score every
explanation against the same fixed set of **5 binary criteria** — each one
independently pass/fail, not a single valid/invalid flip and not a
collapsed score. How the 5-dim vector gets aggregated into an overall
accept/reject or a single number is deliberately left open (see Open
questions) — the point of scoring per-criterion is to keep that decision
separate from, and downstream of, the raw agreement data.

Criteria 1-3 each check one sentence of the template above (does that
sentence say the right thing); criteria 4-5 are cross-cutting — checked
against all 3 sentences at once (does the explanation say it the right
way, regardless of which sentence it's in). Format compliance (the
opening-phrase check) is dropped from this list entirely: it's a
mechanical string/regex check, not a judgment call, so it's enforced
outside the judge instead of consuming human/LLM calibration budget.
On-topic/non-generic — judged in an earlier draft of this plan — is
deferred to a later, separate qualitative pass rather than scored here
(see Open questions). Non-circularity and engages-with-conflicting-
evidence, by contrast, are folded directly into criteria 1 and 3's FAIL
definitions below rather than kept as separate dimensions.

| # | Criterion | Checks | PASS | FAIL |
|---|---|---|---|---|
| 1 | Root cause correctness | Sentence 1 — is the stated cause the thing that actually drove the classification? | Cited cause is present in the logs and plausibly what made this sequence normal/abnormal. | Wrong log/event is blamed, or the "cause" isn't actually distinguishing (also present in normal sequences), or the "cause" merely restates the verdict/label itself instead of citing a concrete log-grounded event (circular, e.g. "abnormal because the sequence is anomalous"). Invented causes are criterion 4, not this one — this is *wrong* (or circular/absent) cause, not *fabricated* cause. |
| 2 | Sequence summary correctness | Sentence 2 — does the brief description of "what happens across the sequence" match what the logs show? | Ordering/flow/pattern described matches the log sequence, even compressed/simplified. | Describes an order, timing, or pattern that contradicts the actual logs (e.g. "repeated" when it happens once, "before" when it's after). |
| 3 | Contrast correctness | Sentence 3 — is the stated reason it's *not* the opposite label actually true and actually discriminating? | The distinguishing detail is real and genuinely explains why the opposite verdict doesn't apply. | Contrast is missing, circular ("not normal because it's abnormal"), cites a distinction that doesn't actually separate the two cases, or addresses only one of several conflicting signals present in the window while ignoring other evidence that would call the verdict into question (cherry-picked contrast). |
| 4 | Groundedness (no fabrication) | *Cross-cutting, all 3 sentences* — is every specific claim (event, error code, count, component, timing) traceable to a line in the given sequence? | Every named detail can be pointed to in the input. | Any specific detail is invented, imported from "what this kind of error usually looks like," or exaggerated beyond what's shown. Reasonable paraphrase is not a fail — that's summarizing, not inventing. |
| 5 | Speculation bounded (no overreach) | *Cross-cutting, all 3 sentences* — are causal/intent claims stated with a confidence the evidence actually supports? | Claims are hedged to the level the logs justify. | Asserts a mechanism, intent, or downstream consequence the logs never evidence — even if the underlying cause (criterion 1) is correct. Stating a well-evidenced cause plainly is not a fail — confidence isn't the problem, *unsupported* confidence is. |

Use identical wording for the human reviewer and the `llm_as_judge` prompt
(`src/prompts/judge_prompt.py`) for each criterion — the PASS/FAIL
definitions above are meant to be copy-pasted into both, not paraphrased
separately, so there's no ambiguity between what a human scores and what
the judge scores.

## Sampling population & deduplication strategy

**Status: design decided 2026-08-04, implemented 2026-08-04** (see Open questions for the
follow-up sizing/decision items this still leaves open -- production-set size, the
supplemental-topup selection logic, and which criteria-rollup/search-algorithm choices remain
undecided).

Implementation lives in `src/help_functions/`:
- `dedup_pool.py::build_deduplicated_pool(...)` -- the template-hash dedup/cap/HDFS-filter pool
  builder described below.
- `id_ledger.py::get_used_ids(...)` / `append_used_ids(...)` -- reads/appends
  `dataset_short/<dataset>/used_ids.json`.
- `manifest_log.py::append_manifest_entry(...)` -- append-only writer for
  `docs/llm_judge_validation_log.json`.
- `gold_sampling.py::draw_gold_sample(...)` / `draw_production_sample(...)` -- shared draw
  orchestration used by all three datasets' `sampling_1.py` CLIs (see step 1/6 below).

Before any of the sampling in step 1 below can be trusted to actually produce a diverse,
balanced gold set, two population properties needed to be measured directly rather than
assumed: how imbalanced normal/abnormal actually is per dataset, and how much of each
population is duplicate/near-duplicate content. Both were measured with a one-off streaming
scan (`json_stream`, same approach `get_all_sequences.py` already uses) over each dataset's
`full_not_explained.json` on 2026-08-04 — not yet a checked-in script, should become one
(e.g. `src/help_functions/`) when this is implemented.

**Why raw-text hashing doesn't work as a duplicate signal:** every BGL/HDFS raw log line
embeds a per-line microsecond timestamp (and for BGL, a node ID) directly in the text, so
exact-raw-text duplicates are ~0% even for windows that are behaviorally identical bursts of
the same repeated event. The signal that actually finds duplicates is a hash of the **ordered
sequence of parsed Drain3 templates** (the `input` field) — that's what's stripped of the
timestamp/node-ID noise and exposes a genuinely repeated pattern.

Measured population (per dataset, from `full_not_explained.json`):

| Dataset | Total windows | Normal / Abnormal | Ratio | Unique templates — normal | Unique templates — abnormal | Largest duplicate cluster | Cross-class template collisions |
|---|---|---|---|---|---|---|---|
| BGL | 231,563 | 212,826 / 18,737 | 11.4:1 | 34,781 (16.3%) | 2,640 (14.1%) | 83,405 records (36% of dataset) | 0 |
| HDFS | 575,061 | 558,223 / 16,838 | 33.1:1 | 14,155 (2.5%) | 3,703 (22.0%) | 94,972 records (16.5%) | **231 groups** |
| Thunderbird | 830,087 | 829,665 / 422 | 1966:1 | 78.8% unique overall (not split by class) | (422 total — scarcity, not duplication, is the binding constraint) | 13,109 records | 0 |

Takeaways:
- BGL/HDFS's problem is **duplication**: a uniform-random draw is dominated by a handful of
  mega-clusters (e.g. a BGL normal draw has a ~39% chance of landing in one single repeated
  "generating core.\<\*\>" burst — visible verbatim as the first record in
  `dataset_short/bgl/llm-lade_base_seed.json`).
- Thunderbird's problem is **scarcity**: only 422 abnormal windows exist in the entire
  830k-window dataset, so it constrains sample size directly rather than through duplication.
- HDFS additionally has 231 template-hash groups where the *identical* parsed-template
  sequence is labeled `normal` in some blocks and `anomaly` in others — meaning the cause
  isn't recoverable from the window's own content for those cases at all.

**Deduplication method (decided):** hash the ordered `input` template list per record; within
each class's pool, cap each duplicate cluster (same hash) at **K=3** representative records
before any random sampling happens — softer than full collapse-to-one, so a pattern's
relative commonness isn't erased entirely, but no single cluster can dominate a draw the way
the raw population does. This capping applies to both the judge-validation gold pool (step 1
below) and the larger production pool (see Open questions).

**HDFS cross-class filter (decided):** the 231 template-hash groups that contain *both*
classes are dropped from the sampling pool entirely, on both sides, before capping/sampling —
not a diversity fix but a label-recoverability filter: if the generation model is handed a
window whose cause isn't distinguishable from its own content, criterion 4 (groundedness) is
guaranteed to fail, so these windows can't productively be used for either class.

**Feasibility check against step 1's existing gold-set numbers (30 core, 15/15, + up to 20
supplemental topup, worst case 35/class):** comfortably met everywhere. BGL has 2,640 unique
abnormal templates before capping; HDFS has 3,703 unique anomaly templates before capping and
losing some to the 231-group exclusion still leaves far more than 35 needed; Thunderbird's
raw 422 abnormal total, even before accounting for its 78.8%-unique overall dedup rate, is
still >10x the worst-case 35 needed. The tight case is Thunderbird's *overall* abnormal
budget across every draw this project ever makes from it (see Open questions) — not any
single draw's feasibility.

## Proposed steps

1. **Draw a gold-standard sample.**
   Draw directly from each dataset's full population
   (`dataset_short/<dataset>/full_not_explained.json`), not the old
   `sampled_50_*` files — those predate the dedup/HDFS-filter design above
   and were drawn with plain unfiltered `random.sample`. The draw pool is
   the population **after** applying the sampling & deduplication strategy
   above (HDFS's 231 cross-class groups excluded; each duplicate
   template-hash cluster capped at K=3 representatives). This gold set is
   dedicated purely to judge validation and is drawn from a disjoint ID
   pool from the larger production set (see Open questions) — an ID-ledger
   recording every ID drawn for either purpose is required so the same
   window is never reused across the two. **Implemented**: every draw (gold
   or production) checks `dataset_short/<dataset>/used_ids.json` before
   sampling and appends to it after — see `src/help_functions/id_ledger.py`.

   Two strata, drawn and logged separately so they're never conflated in
   scoring:
   - **Natural core — 30 samples per dataset (BGL, Thunderbird, HDFS),
     split evenly 15 normal / 15 abnormal.** Plain random draw (fixed
     seed) from the deduplicated/filtered population above. This is the set step 4's
     headline agreement/kappa/false-negative numbers are computed over —
     it preserves the real base rate of pass/fail per criterion, which
     those metrics depend on to mean anything.
   - **Supplemental fail-topup — bounded oversample, capped at +20 per
     dataset.** Draw an additional pool (~30-50 per dataset) from the same
     population and human-score it in the same pass as the core (step 2
     covers both, no separate review round). After scoring, check each of
     the 5 criteria against a floor (e.g. at least 5 observed fails in the
     core); for any criterion under the floor, pull already-scored fail
     examples for *that* criterion from the oversample pool into the gold
     set until the floor is met. Every added case is a real,
     naturally-occurring failure found by casting a wider net — nothing
     synthetic or hand-edited. This is also why a full 2^5-combination
     design was dropped: the 5 criteria are ratings assigned *after* the
     fact by a human looking at an explanation, not factors you can dial
     in beforehand, so guaranteeing all 32 cells would mean discarding
     most of a much larger draw to hit rare/possibly-nonexistent
     combinations — the topup only targets the one axis (per-criterion
     fail coverage) that actually risked leaving a criterion's kappa
     undefined.

   Log both strata to the manifest with a `stratum: natural | supplemental`
   field per sample (and, for supplemental entries, which criterion they
   were pulled in to satisfy), plus the sampling action itself (seed,
   source file, resulting IDs).

   **Implemented**: `src/sampling/explanation_creation/<dataset>/sampling_1.py gold`
   draws both strata in one run via `draw_gold_sample(...)`
   (`src/help_functions/gold_sampling.py`) — natural core defaults to 15/15,
   supplemental oversample pool defaults to 20 per class (40 total, within the
   ~30-50 range above; overridable via `--supplemental_per_class`). Only the natural-
   core and oversample-pool *draw* is implemented here; the per-criterion fail-floor
   topup-selection logic (pulling supplemental cases into the gold set once step 2's
   human scores exist) is intentionally left as a follow-up, since implementing it now
   would mean coding against fake review data.

2. **Human-review that sample — scored against the 5-criterion binary
   vector, not a plain valid/invalid flip.**
   Run `src/review/human/<dataset>/human_reviewer.py` over it, but have the
   reviewer score each of the 5 criteria above pass/fail individually
   (rather than one overall valid/invalid decision), so agreement in step 4
   can be measured per-criterion instead of "did the binary label flip."
   These become the ground-truth verdicts (`verification_method: "human"`).
   Log the review pass itself (reviewer, dataset, timestamp, output file)
   to the manifest.

3. **Search the `llm_as_judge` configuration space against the human sample.**
   Rather than a manual sweep, search the space of (mode, temperature,
   effort) — a mode is a model and prompt tied together, and each mode has its
   own list of reasoning efforts to try — using a swarm/colony-style metaheuristic optimizer — candidate:
   PSO, or another ant/particle-colony-style algorithm (not chosen yet).
   Fitness of a candidate configuration = its similarity to the step-2
   human verdicts on the same 30-per-dataset sample, compared per-criterion
   over the 5-criterion binary vector from step 2 (not a single collapsed
   agreement number).

   Run this search:
   - once per candidate algorithm, separately,
   - once with all candidate algorithms combined,
   - and separately, run the full **Cartesian product** of every
     (mode × temperature × effort) combination as a brute-force baseline
     to sanity-check the metaheuristic search against.

   Each run/config's judge output must be kept separate (distinct output
   file per config) rather than overwriting, since scoring needs all of
   them alongside the human labels. Log every single run (its params,
   input/output paths) to the manifest as it happens — this is the search
   trace referenced above.

4. **Score each configuration against the human labels.**
   For each config — whether found via metaheuristic search or the
   Cartesian sweep — compute similarity between its verdicts and the human
   reviewer's verdicts on the same windows, per criterion from the
   5-criterion binary vector (step 2), then also rolled up:
   - per-criterion agreement (e.g. criterion 4 "groundedness":
     judge pass/fail vs. human pass/fail across the sample),
   - per-criterion Cohen's kappa as the chance-corrected metric (each
     criterion is binary, so plain kappa applies — no ordinal/weighted
     variant needed now that the scale isn't multi-point),
   - false-negative rate specifically (judge marks a criterion "pass" but
     human marked it "fail") as the metric that matters most, both
     per-criterion and overall — that's the failure mode that lets bad
     explanations into the dataset unchecked. All 5 criteria are
     hallucination-derived, so treat them as equally high-stakes here
     unless step 5's rollup decision says otherwise.
   How the 5 per-criterion scores roll up into one config-level number for
   ranking configs in step 5 is still open — see Open questions.

   Report agreement/kappa on the natural-core stratum alone as the
   headline number (it's the one with a realistic base rate); the
   natural+supplemental set is only used to check that a criterion's
   kappa isn't degenerate for lack of fail examples, not as a substitute
   headline metric.

   Write each config's computed metrics back into its manifest entry
   (the `metrics` block) rather than only in a separate report, so the
   run and its score stay attached to each other.

5. **Pick the best configuration.**
   Choose the (model, prompt, temperature) combination — from whichever
   search method found it — with the highest similarity to human
   judgments / lowest false-negative rate. Log a final `"action":
   "decision"` manifest entry naming the winning config, which search
   method found it, its agreement numbers, and why it was chosen over the
   runner-up(s) — this is the evidence used to justify trusting
   `llm_as_judge` unsupervised afterward.

6. **Only then run the full pipeline unsupervised.**
   Use the winning judge configuration to verify explanations for a
   separately-sampled **production set** (drawn from the same
   deduplicated/filtered population as step 1, but from a disjoint ID pool
   — see the ID-ledger note in step 1), at scale, without per-item human
   review, citing step 4/5's agreement numbers (and the manifest entries
   backing them) as justification. Production-set size is not yet decided
   — see Open questions.

   **Implemented (mechanism only, size still open)**:
   `src/sampling/explanation_creation/<dataset>/sampling_1.py production
   --num_per_class N` draws N normal + N abnormal records per run via
   `draw_production_sample(...)` (`src/help_functions/gold_sampling.py`) — same
   dedup/cap/HDFS-filter pool and ledger-exclusion as the gold draw, ids tagged
   `purpose: "production"` in the ledger, no natural/supplemental split and no human
   review. `--num_per_class` has no default on purpose (see Open questions) so it must
   be passed explicitly each run.

   **Terminology note (2026-08-08):** "production set" here means the
   larger-scale, human-review-free deliverable dataset — concretely, the
   ground-truth explanations used downstream to score an agentic AI's own
   output, not a live deployed system, and not something the agentic AI
   itself ever reads. Because of that, its generation is **not** bound by
   the gold set's blind, no-per-log-label constraint (see "Explanation
   template" above) — that constraint exists only to keep the gold set's
   failure distribution rich enough for judge calibration. For this set,
   feeding per-log ground-truth classification into
   `src/explanation_creation/<dataset>/creation1.py` is the intended
   approach: since these explanations are an answer key rather than a
   test of blind reasoning, minimizing hallucination matters more than
   matching the difficulty of the gold-set task. Watch the generation
   prompt in this mode for a new failure shape: the model restating the
   per-line label itself ("line N is marked abnormal") instead of writing
   a causal sentence, which would trip criterion 1's circular-restatement
   FAIL condition at the line level instead of the sequence level.

## Open questions / things to decide later

- **Production-set size.** The 30-40/dataset gold set (step 1) is only the
  human-reviewed calibration/seed portion — bounded by realistic human
  review capacity (confirmed: ~30-40/dataset max). Once the judge is
  validated (step 5), a separate, larger **production set** gets verified
  by the judge alone (step 6), with no human-capacity ceiling — but its
  target size is still undecided and needs to come from downstream
  training/eval needs, not from this doc. Every dataset has ample
  deduplicated population left to support a production set well beyond
  the gold set's 30-40 (BGL: 34,781 unique normal / 2,640 unique abnormal
  templates before capping; HDFS: 14,155 / 3,703; Thunderbird: 422 raw
  abnormal total is the binding ceiling there — whatever production-set
  size is picked, Thunderbird's abnormal side should be checked against
  422 minus whatever the gold set + topup already consumed). The *draw
  mechanism* is implemented (`sampling_1.py production --num_per_class N`,
  see step 6) with no default for `N` — only the actual number to pass is
  still an open decision.
- **ID-ledger mechanism. Implemented 2026-08-04.** `dataset_short/<dataset>/used_ids.json`
  (array of `{id, purpose, drawn_at}`, `purpose` one of `gold_natural` /
  `gold_supplemental` / `production`), read/written via
  `src/help_functions/id_ledger.py`. Every gold and production draw checks it before
  sampling and appends to it after, so the same window can't be reused across gold
  natural-core / gold supplemental / production draws.
- How the 5-criterion binary vector rolls up into a single config-level
  score for ranking/choosing a winner in step 5 — e.g. pass-all, weighted
  sum, worst-criterion-wins, or something else. Deliberately deferred
  rather than baked into the criteria definitions themselves.
- Non-circularity (now covered by criterion 1's and criterion 3's FAIL
  definitions, for label-restating root causes and cherry-picked
  contrasts respectively) and engages-with-conflicting-evidence (folded
  into criterion 3) are no longer separate open items. On-topic/non-generic
  remains genuinely deferred: it's a style/quality axis distinct from
  correctness or hallucination, and folding it into this calibration would
  muddy what the per-criterion kappa/false-negative numbers are measuring.
  Still open whether it's deferred indefinitely or scheduled as a
  fast-follow qualitative pass, and if revived, whether it factors into
  acceptance into the *final* dataset or only evaluates/compares judge
  configs.
- Which swarm/colony metaheuristic to use (PSO vs. ant-colony vs.
  something else), and how to define its search space bounds (which
  models are candidates, temperature range/step, which prompt variants).
- Whether to test prompt variants at all, or hold the prompt fixed (per the
  CLAUDE.md contract that the judge prompt's flag vocabulary/output shape
  must stay stable) and only search over model + temperature.
  *Resolved (2026-10-10):* the rubric, scoring rules and output shape are held
  fixed in `src/prompts/judge_criteria/common.py`; only the wording around them
  varies, one prompt per model, each in its own file in that package. Prompt
  and model are therefore confounded in the search by design.
- Compute/cost budget: the full Cartesian product baseline plus multiple
  metaheuristic runs (per-algorithm and combined) over 30×3 datasets could
  get expensive — worth estimating call counts before running.
- Where the search/scoring code and the manifest itself should live —
  likely a new `src/review/validate_judge/` stage, following the existing
  per-stage CLI convention, writing to
  `docs/llm_judge_validation_log.json`.
- Whether the same calibration sample and winning config get reused across
  all three datasets (BGL, Thunderbird, HDFS), or each dataset needs its
  own calibration since log structure/vocabulary differs a lot (especially
  HDFS's session-based sampling vs. the other two's fixed windows).
- **Judge-calibration transfer once production generation adds per-log
  labels (raised 2026-08-08).** Step 5 picks a judge config validated
  against the gold set's *blind*-generation failure distribution, which in
  the BGL natural-core pilot (2026-08-08, 15/15 abnormal) is dominated by
  root_cause_correctness (12/15 fails) vs. contrast_correctness (5),
  groundedness (5), and speculation_bounded (8). Once the production set's
  generation step is given per-log ground-truth labels (see step 6's
  terminology note), root_cause_correctness fails there should largely
  disappear, so the judge's real workload on the delivered dataset will
  skew toward the criteria that made up a smaller share of the gold set's
  calibration evidence. Not a flaw in the plan, but the eventual writeup
  should say this explicitly rather than let the single headline
  agreement number imply equal confidence across all 5 criteria for the
  dataset actually being shipped.
- **Gold-set fail concentration / limited spread (raised 2026-08-09).**
  Counted over the full BGL gold set (natural + supplemental, 70 records):
  71% of abnormal-class records (25/35) are windows with only 2 unique
  Drain3 templates — one ground-truth-normal template interleaved with one
  ground-truth-abnormal template — where the generator tends to fold both
  into the stated cause instead of isolating the abnormal one (the
  "mixing" pattern noted throughout the human review). Of the 21
  root_cause_correctness fails coming from that pattern, only 7 distinct
  template-pairs are responsible, and two pairs alone (`instruction
  address` / `data storage interrupt`, and `ciod ... Link has been
  severed` / `ciod: Received signal ...`) account for 62% of them. This
  isn't a sampling bug — BGL genuinely has few distinct abnormal templates
  overall (2,640 total, see the population table above) — so it can't be
  fixed by redrawing, and the existing template-hash dedup cap (K=3 in
  `dedup_pool.py`) doesn't catch it either, since that hashes the full
  ordered window, not the unique-template-pair "shape" this pattern
  depends on. Feeding per-log ground-truth labels into *gold-set*
  generation would suppress this failure mode rather than diversify it,
  which would work against the gold set's purpose (see "Explanation
  template" above) — that fix is scoped to production-set generation
  (step 6) only, and is orthogonal to this issue. **Decision: not fixing
  this via a targeted/stratified resampling pass — out of scope for this
  project's size.** Instead, disclose it directly in the final writeup:
  agreement/kappa on root_cause_correctness and contrast_correctness
  should be read as validated mainly against this repeating mixing
  pattern, not as evidence the judge generalizes to every possible way a
  root cause or contrast can be wrong.