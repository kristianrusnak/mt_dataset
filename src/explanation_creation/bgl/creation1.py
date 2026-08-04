from src.help_functions.json_deep_convert import deep_convert
from src.help_functions.manifest_log import append_manifest_entry
from src.prompts.bgl.prompt1 import get_prompt

from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage
from json_stream import streamable_list, load
from dotenv import load_dotenv
import json
import argparse
import os
from datetime import datetime, timezone

load_dotenv()

DATASET_NAME = "bgl"

@streamable_list
def create_explanation(input_path: str, output_path: str, prompt_template_path: str, llm_model: str, stats: dict, limit: int = -1):
    """
    Generates explanations for log sequences using an OpenAI model and streams the output.
    """
    llm = ChatOpenAI(model_name=llm_model, openai_api_key=os.environ.get("OPENAI_API_KEY"))

    def sequence_reader():
        with open(input_path, 'r', encoding="utf-8") as f:
            loaded_data = load(f)
            for item in loaded_data.persistent():
                sequence_data = deep_convert(item)
                yield sequence_data

    loop_counter = 0
    for sequence_data in sequence_reader():
        stats["total"] += 1
        if loop_counter >= limit > 0 or sequence_data['explanation']:
            stats["skipped"] += 1
            yield sequence_data
            continue
        loop_counter += 1
        stats["generated"] += 1

        sequence_data['metadata']['llm'] = {
                    "model": llm.model_name,
                    "generation_timestamp": str(datetime.now()),
                    "prompt_template_id": prompt_template_path,
                    "generation_params": {}
                }
        sequence_data['metadata']['hallucination-check'] = {
            "verification_status": "unverified",
            "verification_method": None,
            "verifier_model": None,
            "hallucination_flags": None,
            "corrected_reasoning_text": None,
            "human_reviewed": False,
            "reviewer_id": None,
            "review_notes": None
        }

        classification = sequence_data.get('classification', "")
        template_sequence = sequence_data.get('input', [])
        log_sequence = list(template_sequence)

        prompt = get_prompt(log_sequence=log_sequence,
                            sequence_classification=classification,
                            dataset_name=DATASET_NAME)

        message = [HumanMessage(content=prompt)]
        llm_response = llm.invoke(message)
        explanation = llm_response.content.strip()

        sequence_data['explanation'] = explanation
        yield sequence_data

def main(input_path: str,
         output_path: str,
         prompt_template_path: str,
         llm_model: str,
         manifest_path: str,
         stratum: str = None,
         limit: int = -1):
    stats = {"total": 0, "generated": 0, "skipped": 0}
    with open(output_path, "w", encoding='utf-8') as f:
        explanation = create_explanation(
            input_path=input_path,
            output_path=output_path,
            prompt_template_path=prompt_template_path,
            llm_model=llm_model,
            stats=stats,
            limit=limit
        )
        json.dump(explanation, f, indent=4)

    append_manifest_entry(manifest_path, {
        "step": 2,
        "action": "explanation_generation_run",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": DATASET_NAME,
        "stratum": stratum,
        "params": {
            "model": llm_model,
            "prompt_template_id": prompt_template_path,
        },
        "inputs": [input_path],
        "outputs": [output_path],
        "metrics": {},
        "notes": (
            f"{stats['generated']} explanations generated, {stats['skipped']} skipped "
            f"(already had an explanation, or past --limit) out of {stats['total']} "
            f"records read. Feeds step 2 human review."
        ),
    })

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate explanations for log sequences using an LLM.")
    parser.add_argument(
        "--input_path",
        type=str,
        default="dataset_short/bgl/sampled_50_not_explained.json",
        help="Path to the input JSON dataset containing log sequences."
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default="dataset_short/bgl/sampled_50_explained.json",
        help="Path to save the output JSON dataset with explanations."
    )
    parser.add_argument(
        "--prompt_template_path",
        type=str,
        default="bgl/prompt1",
        help="Identifier for the prompt template used to generate explanations."
    )
    parser.add_argument(
        "--llm_model",
        type=str,
        default="gpt-5.4-mini",
        help="Name of the LLM model to use for generating explanations (e.g., 'gpt-5.4-mini')."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=-1,
        help="Limit the number of sequences to process. Use -1 for all sequences."
    )
    parser.add_argument(
        "--manifest_path",
        type=str,
        default="docs/llm_judge_validation_log.json",
        help="Path to the append-only sampling/validation manifest."
    )
    parser.add_argument(
        "--stratum",
        type=str,
        default=None,
        choices=[None, "natural", "supplemental", "production"],
        help="Which gold stratum (or 'production') this input file is, logged to the manifest."
    )

    args = parser.parse_args()

    main(
        input_path=args.input_path,
        output_path=args.output_path,
        prompt_template_path=args.prompt_template_path,
        llm_model=args.llm_model,
        manifest_path=args.manifest_path,
        stratum=args.stratum,
        limit=args.limit
    )