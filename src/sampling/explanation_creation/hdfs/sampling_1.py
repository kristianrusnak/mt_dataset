import argparse

from src.help_functions.gold_sampling import draw_gold_sample, draw_production_sample

DATASET_NAME = "hdfs"
ABNORMAL_LABEL = "anomaly"  # HDFS's abnormal class is labeled "anomaly", not "abnormal"
EXCLUDE_CROSS_CLASS = True  # drop the 231 template-hash groups whose blocks span both classes


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source_path",
        type=str,
        default="dataset_short/hdfs/full_not_explained.json",
        help="Path to the full (not-yet-explained) dataset to draw from.")
    parser.add_argument(
        "--ledger_path",
        type=str,
        default="dataset_short/hdfs/used_ids.json",
        help="Path to this dataset's id ledger, checked/updated on every draw.")
    parser.add_argument(
        "--manifest_path",
        type=str,
        default="docs/llm_judge_validation_log.json",
        help="Path to the append-only sampling/validation manifest.")
    parser.add_argument(
        "--k",
        type=int,
        default=3,
        help="Max representative records kept per duplicate template-hash cluster.")
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Draw gold/production samples for the HDFS dataset.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    gold_parser = subparsers.add_parser("gold", help="Draw the judge-validation gold sample (natural core + supplemental oversample pool).")
    _add_common_args(gold_parser)
    gold_parser.add_argument(
        "--natural_output_path",
        type=str,
        default="dataset_short/hdfs/gold_natural_not_explained.json",
        help="Output path for the natural-core stratum (15 normal / 15 abnormal).")
    gold_parser.add_argument(
        "--supplemental_output_path",
        type=str,
        default="dataset_short/hdfs/gold_supplemental_not_explained.json",
        help="Output path for the supplemental oversample pool (not yet selected into the gold set).")
    gold_parser.add_argument(
        "--natural_core_per_class",
        type=int,
        default=15,
        help="Natural-core samples per classification.")
    gold_parser.add_argument(
        "--supplemental_per_class",
        type=int,
        default=20,
        help="Supplemental oversample-pool samples per classification.")

    production_parser = subparsers.add_parser("production", help="Draw the production set (judge-only verification, no human review).")
    _add_common_args(production_parser)
    production_parser.add_argument(
        "--output_path",
        type=str,
        default="dataset_short/hdfs/production_not_explained.json",
        help="Output path for the production draw.")
    production_parser.add_argument(
        "--num_per_class",
        type=int,
        required=True,
        help="Number of records to draw per classification. Production-set size is "
             "not yet decided (see docs/llm_judge_validation_plan.md Open Questions) "
             "so there is no default -- pass it explicitly.")

    args = parser.parse_args()

    if args.mode == "gold":
        draw_gold_sample(
            dataset_name=DATASET_NAME,
            source_path=args.source_path,
            natural_output_path=args.natural_output_path,
            supplemental_output_path=args.supplemental_output_path,
            ledger_path=args.ledger_path,
            manifest_path=args.manifest_path,
            natural_core_per_class=args.natural_core_per_class,
            supplemental_per_class=args.supplemental_per_class,
            seed=args.seed,
            abnormal_label=ABNORMAL_LABEL,
            k=args.k,
            exclude_cross_class=EXCLUDE_CROSS_CLASS,
        )
    else:
        draw_production_sample(
            dataset_name=DATASET_NAME,
            source_path=args.source_path,
            output_path=args.output_path,
            ledger_path=args.ledger_path,
            manifest_path=args.manifest_path,
            num_per_class=args.num_per_class,
            seed=args.seed,
            abnormal_label=ABNORMAL_LABEL,
            k=args.k,
            exclude_cross_class=EXCLUDE_CROSS_CLASS,
        )