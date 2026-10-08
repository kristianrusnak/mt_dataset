"""
Agreement metrics between a judge's 5-criterion verdicts and the human's.

Convention: the "positive" class is FAIL, because the failure we most want to avoid is the judge
letting a bad explanation through. Verdicts are booleans, True = PASS.

  false_negative_rate  P(judge says PASS | human says FAIL)   -- bad explanation slips through
  false_positive_rate  P(judge says FAIL | human says PASS)   -- good explanation rejected
  kappa                Cohen's kappa: agreement beyond what two raters with these pass rates
                       would reach by chance. None when undefined (e.g. everyone always says PASS).
  youden_j             1 - FNR - FPR: share of human fails the judge catches, minus share of human
                       passes it wrongly rejects. 0 for any judge that ignores the input (always PASS,
                       always FAIL, coin flip), 1 for a perfect one. Computed within each human class,
                       so it does not move with how many fails the pool happens to contain.
"""

from src.help_functions.review_criteria import CRITERIA_KEYS


def _rate(num: int, den: int):
    return num / den if den else None


def criterion_metrics(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs = [(human_pass, judge_pass), ...] for one criterion."""
    n = len(pairs)
    if n == 0:
        return {"n": 0, "agreement": None, "kappa": None, "false_negative_rate": None,
                "false_positive_rate": None, "youden_j": None, "human_fails": 0}

    both_pass = sum(1 for h, j in pairs if h and j)
    both_fail = sum(1 for h, j in pairs if not h and not j)
    human_fails = sum(1 for h, _ in pairs if not h)
    human_passes = n - human_fails
    missed_fails = sum(1 for h, j in pairs if not h and j)
    false_alarms = sum(1 for h, j in pairs if h and not j)

    observed = (both_pass + both_fail) / n
    judge_pass_rate = sum(1 for _, j in pairs if j) / n
    human_pass_rate = human_passes / n
    expected = human_pass_rate * judge_pass_rate + (1 - human_pass_rate) * (1 - judge_pass_rate)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else None

    fnr = _rate(missed_fails, human_fails)
    fpr = _rate(false_alarms, human_passes)
    return {
        "n": n,
        "agreement": observed,
        "kappa": kappa,
        "false_negative_rate": fnr,
        "false_positive_rate": fpr,
        "youden_j": 1 - fnr - fpr if fnr is not None and fpr is not None else None,
        "human_fails": human_fails,
    }


def _mean(values: list):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def score_config(items: list[dict], judge_verdicts: dict) -> dict:
    """
    items: gold items (gold.load_gold). judge_verdicts: item key -> {criterion: bool}; items the
    judge failed to score are simply absent and left out of every number.

    fitness = mean over criteria of Youden's J (1 - FNR - FPR), range [-1, 1], higher is better, 0 =
    no better than a judge that ignores the input. A criterion with no human fail (or no human pass)
    in the scored set has no J and is skipped.
    """
    scored = [it for it in items if it["key"] in judge_verdicts]

    per_criterion = {}
    fitness_terms = []
    for criterion in CRITERIA_KEYS:
        pairs = [(it["human"][criterion], judge_verdicts[it["key"]][criterion]) for it in scored]
        m = criterion_metrics(pairs)
        per_criterion[criterion] = m
        if m["youden_j"] is not None:
            fitness_terms.append(m["youden_j"])

    all_pairs = [(it["human"][c], judge_verdicts[it["key"]][c]) for it in scored for c in CRITERIA_KEYS]
    pooled = criterion_metrics(all_pairs)

    return {
        "n_scored": len(scored),
        "overall": {
            "agreement": pooled["agreement"],
            "kappa": _mean([m["kappa"] for m in per_criterion.values()]),
            "false_negative_rate": pooled["false_negative_rate"],
            "fitness": _mean(fitness_terms),
        },
        "per_criterion": per_criterion,
    }
