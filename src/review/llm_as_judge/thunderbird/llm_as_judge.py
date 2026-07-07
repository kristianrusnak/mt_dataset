import os
import json
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field
from langchain.messages import HumanMessage
# Using ChatOpenAI as a generic placeholder, you can swap it with ChatAnthropic, ChatGoogleGenerativeAI, etc.
from langchain_openai import ChatOpenAI 
from json_stream import streamable_list, load

from src.help_functions.json_deep_convert import deep_convert
from src.prompts.judge_prompt import get_judge_prompt


# 1. Define the Response Template using Pydantic
class HallucinationReview(BaseModel):
    hallucination_flags: List[str] = Field(
        description="List of flags identifying issues. Use ['valid'] if there are no hallucinations and the explanation is perfect."
    )
    corrected_reasoning_text: Optional[str] = Field(
        description="If there are hallucinations, provide the corrected reasoning here.",
        default=None
    )
    review_notes: Optional[str] = Field(
        description="Any additional notes or observations from the review.",
        default=None
    )

def setup_llm(llm_model: str):
    """
    Sets up the Langchain LLM and the prompt.
    Returns a chain that parses the output into the Pydantic model.
    """
    # Initialize the LLM (Replace with your specific provider and model later)
    # e.g., ChatAnthropic(model="claude-3-opus-20240229") or ChatGoogleGenerativeAI
    llm = ChatOpenAI(model=llm_model, 
                     temperature=0, 
                     openai_api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Bind the LLM to output our structured Pydantic model
    structured_llm = llm.with_structured_output(HallucinationReview)
    
    return structured_llm

def prompt_llm_for_review(structured_llm, 
                          logs: list, 
                          classifications: list, 
                          explanation: str,
                          sequence_classification: str) -> dict:
    """
    Calls the Langchain LLM chain to review the given logs and explanation.
    """
    prompt = get_judge_prompt(
        log_sequence=logs,
        classifications=classifications,
        session_based=False,
        sequence_classification=sequence_classification,
        dataset_name="thunderbird",
        explanation=explanation
    )

    message = HumanMessage(content=prompt)
    
    # Invoke the chain
    # The output will be a HallucinationReview Pydantic object
    result = structured_llm.invoke(message)
    
    return {
        "hallucination_flags": result.hallucination_flags,
        "corrected_reasoning_text": result.corrected_reasoning_text,
        "review_notes": result.review_notes
    }

@streamable_list
def review_sequences_with_llm(input_path: str, llm_model: str):
    """
    Iterates through sequences, uses LLM for review, and yields updated sequences.
    """
    # Setup the chain once to reuse it across sequences
    structured_llm = setup_llm(llm_model)
    
    with open(input_path, 'r', encoding='utf-8') as input_file:
        for sequence_data_raw in load(input_file).persistent():
            sequence_data = deep_convert(sequence_data_raw)
            
            # Skip if already marked as "valid"
            hallucination_check = sequence_data.get('metadata', {}).get('hallucination-check', {})
            flags = hallucination_check.get('hallucination_flags') or []
            if "valid" in flags:
                print(f"Skipping sequence_id: {sequence_data.get('metadata', {}).get('identity', {}).get('id')} - already valid.")
                yield sequence_data
                continue

            parsed_logs = sequence_data.get('input')
            sequence_classification = sequence_data.get('classification')
            raw_logs = sequence_data.get('metadata').get('raw_content').get('raw_log_sequence')
            classifications = ["normal" if log.startswith("-") else "abnormal" for log in raw_logs]
            explanation = sequence_data.get('explanation')

            print(f"Reviewing sequence_id: {sequence_data.get('metadata', {}).get('identity', {}).get('id')} with LLM...")

            try:
                # Call the LLM instead of asking a human
                llm_response = prompt_llm_for_review(
                    structured_llm=structured_llm,
                    logs=parsed_logs,
                    classifications=classifications,
                    explanation=explanation,
                    sequence_classification=sequence_classification
                    )
                
                # Update hallucination-check metadata
                sequence_data.setdefault('metadata', {})['hallucination-check'] = {
                    "verification_status": "verified",
                    "verification_method": "llm_as_judge",
                    "verifier_model": "llm_as_judge/thunderbird/llm_as_judge.py", # Can be dynamically populated based on the model used
                    "hallucination_flags": llm_response.get("hallucination_flags"),
                    "corrected_reasoning_text": llm_response.get("corrected_reasoning_text"),
                    "human_reviewed": False,
                    "reviewer_id": llm_model,
                    "review_notes": llm_response.get("review_notes"),
                    "review_timestamp": str(datetime.now())
                }
            except Exception as e:
                print(f"Error reviewing sequence_id: {sequence_data.get('metadata', {}).get('identity', {}).get('id')}. Error: {e}")
                # You might want to decide whether to yield the unchanged sequence or skip it on error. 
                # We yield it unchanged here so we don't lose data in the stream.

            yield sequence_data

def main():
    input_file = "dataset_short/thunderbird/sampled_50_explained.json"
    output_file = "dataset_short/thunderbird/sampled_50_llm_reviewed.json"

    reviewed_data_stream = review_sequences_with_llm(input_file, llm_model="gpt-4")

    with open(output_file, 'w', encoding='utf-8') as f:
        # dump the streamable list
        json.dump(reviewed_data_stream, f, indent=4)
    
    print(f"\\nReview process complete. LLM reviewed data saved to {output_file}")

if __name__ == "__main__":
    main()
