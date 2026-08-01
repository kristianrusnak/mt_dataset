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

## Proposed steps

1. **Draw a gold-standard sample.**
   From the already-sampled, already-explained datasets
   (`dataset_short/<dataset>/sampled_50_explained.json` and equivalents),
   take a subset dedicated purely to judge validation — separate from
   whatever sample ends up human-reviewed for the final dataset itself, so
   the same human labels aren't reused for both dataset ground-truth and
   judge calibration. Fixed size: **30 samples per dataset (BGL,
   Thunderbird, HDFS), split evenly 15 normal / 15 abnormal.** Log the
   sampling action (seed, source file, resulting IDs) to the manifest.

2. **Human-review that sample — on a richer scale than binary.**
   Run `src/review/human/<dataset>/human_reviewer.py` over it, but move the
   validation tactic away from a plain valid/invalid flip toward a scale
   with more judging points (e.g. a graded/multi-point score rather than a
   single pass/fail), so agreement in step 4 can be measured with more
   resolution than "did the binary label flip." Exact scale (how many
   points, what each point means) still to be defined — see open
   questions. These become the ground-truth verdicts
   (`verification_method: "human"`). Log the review pass itself
   (reviewer, dataset, timestamp, output file) to the manifest.

3. **Search the `llm_as_judge` configuration space against the human sample.**
   Rather than a manual sweep, search the space of (model, temperature,
   prompt) using a swarm/colony-style metaheuristic optimizer — candidate:
   PSO, or another ant/particle-colony-style algorithm (not chosen yet).
   Fitness of a candidate configuration = its similarity to the step-2
   human graded verdicts on the same 30-per-dataset sample (using the
   multi-point scale from step 2, not a single binary agreement number).

   Run this search:
   - once per candidate algorithm, separately,
   - once with all candidate algorithms combined,
   - and separately, run the full **Cartesian product** of every
     (model × temperature × prompt) combination as a brute-force baseline
     to sanity-check the metaheuristic search against.

   Each run/config's judge output must be kept separate (distinct output
   file per config) rather than overwriting, since scoring needs all of
   them alongside the human labels. Log every single run (its params,
   input/output paths) to the manifest as it happens — this is the search
   trace referenced above.

4. **Score each configuration against the human labels.**
   For each config — whether found via metaheuristic search or the
   Cartesian sweep — compute similarity between its verdicts and the human
   reviewer's graded verdicts on the same windows:
   - agreement on the graded/multi-point scale from step 2 (not just
     binary valid/flagged),
   - Cohen's kappa (or a weighted-kappa variant appropriate for an ordinal
     multi-point scale) as the chance-corrected rigorous metric,
   - false-negative rate specifically (judge says "valid"/low-severity but
     human flagged a real hallucination) as the metric that matters most —
     that's the failure mode that lets bad explanations into the dataset
     unchecked.

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
   Use the winning judge configuration to verify the remaining generated
   explanations at scale, without per-item human review, citing step 4/5's
   agreement numbers (and the manifest entries backing them) as
   justification.

## Open questions / things to decide later

- Exact shape of the "more judging points" scale from step 2 — how many
  points, what each point means, and whether it's a single overall score
  or per-hallucination-category grades.
- Which swarm/colony metaheuristic to use (PSO vs. ant-colony vs.
  something else), and how to define its search space bounds (which
  models are candidates, temperature range/step, which prompt variants).
- Whether to test prompt variants at all, or hold the prompt fixed (per the
  CLAUDE.md contract that the judge prompt's flag vocabulary/output shape
  must stay stable) and only search over model + temperature.
- Compute/cost budget: the full Cartesian product baseline plus multiple
  metaheuristic runs (per-algorithm and combined) over 30×3 datasets could
  get expensive — worth estimating call counts before running.
- Whether kappa/weighted-kappa should be computed on the graded scale
  per-category, on an overall collapsed score, or both.
- Where the search/scoring code and the manifest itself should live —
  likely a new `src/review/validate_judge/` stage, following the existing
  per-stage CLI convention, writing to
  `docs/llm_judge_validation_log.json`.
- Whether the same calibration sample and winning config get reused across
  all three datasets (BGL, Thunderbird, HDFS), or each dataset needs its
  own calibration since log structure/vocabulary differs a lot (especially
  HDFS's session-based sampling vs. the other two's fixed windows).