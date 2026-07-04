from src.help_functions.json_deep_convert import deep_convert
from src.prompts.bgl.prompt1 import get_prompt

from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage
from json_stream import streamable_list, load
import json
import argparse
import os
from datetime import datetime

@streamable_list
def create_explanation(input_path: str, output_path: str, prompt_template_path: str, llm_model: str, limit: int = -1):
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
        if loop_counter >= limit > 0 or sequence_data['explanation']:
            yield sequence_data
            continue
        loop_counter += 1

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
        raw_sequence = (sequence_data.get('metadata', {})
                        .get('raw_content', {})
                        .get('raw_log_sequence', []))
        
        log_sequence = []
        classifications = []
        for template_log, raw_log in zip(template_sequence, raw_sequence):
            log_sequence.append(template_log)
            classifications.append('normal' if raw_log.startswith('-') else 'anomalous')
        
        prompt = get_prompt(log_sequence=log_sequence, 
                            classifications=classifications,
                            session_based=False,
                            sequence_classification=classification,
                            dataset_name="bgl")
        print(prompt)
        
        # message = [HumanMessage(content=prompt)]
        # llm_response = llm.invoke(message)
        # explanation = llm_response.content.strip()
        explanation = "explained - testing"

        sequence_data['explanation'] = explanation
        yield sequence_data

def main(input_path: str, 
         output_path: str, 
         prompt_template_path: str, 
         llm_model: str,
         limit: int = -1):
    with open(output_path, "w", encoding='utf-8') as f:
        explanation = create_explanation(
            input_path=input_path,
            output_path=output_path,
            prompt_template_path=prompt_template_path,
            llm_model=llm_model,
            limit=limit
        )
        json.dump(explanation, f, indent=4)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate explanations for log sequences using an LLM.")
    parser.add_argument(
        "--input_path",
        type=str,
        default="/Users/kristian/Desktop/mt_dataset/agentic_ai/bgl/explained_50.json",
        help="Path to the input JSON dataset containing log sequences."
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default="/Users/kristian/Desktop/mt_dataset/agentic_ai/bgl/explained_50_32.json",
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
        default="gpt-4o",
        help="Name of the LLM model to use for generating explanations (e.g., 'gpt-4o', 'gpt-3.5-turbo')."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=16,
        help="Limit the number of sequences to process. Use -1 for all sequences."
    )
    
    args = parser.parse_args()
    
    main(
        input_path=args.input_path,
        output_path=args.output_path,
        prompt_template_path=args.prompt_template_path,
        llm_model=args.llm_model,
        limit=args.limit
    )