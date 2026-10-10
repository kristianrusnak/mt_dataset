"""
One judge call: a (model, prompt, temperature, effort) config scoring one gold item on the 5 criteria.

Models are open-source ones served behind one LiteLLM proxy (LITELLM_API_BASE / LITELLM_API_KEY),
the same setup the llm_as_judge scripts use. The reply is requested with LangChain's
with_structured_output(CriteriaReview, include_raw=True), so the schema travels with the request and
the raw reply is kept when parsing fails.

Two kinds of failure, handled differently on purpose:
  - InvalidJudgeOutput: the model answered but not in the required shape, even after one corrective
    retry. That is the model's fault, so the evaluator scores the item as wrong on every criterion.
  - any other exception (timeout, 5xx, proxy down): transport trouble, not evidence about the model.
    Retried with backoff here, and if it still fails the item is left unscored and retried next run.
"""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError, create_model

from src.help_functions.review_criteria import CRITERIA_KEYS
from src.prompts.judge_criteria import JudgePrompt, get_criteria_judge_prompt

TRANSPORT_ATTEMPTS = 3
REQUEST_TIMEOUT_S = 180
MAX_OUTPUT_TOKENS = 4096  # headroom for models that think out loud before answering


@dataclass(frozen=True)
class JudgeConfig:
    model: str
    temperature: float
    prompt_id: str
    effort: str  # reasoning effort, sent to the model as `reasoning_effort`

    @property
    def key(self) -> str:
        model = re.sub(r"[^A-Za-z0-9._-]+", "-", self.model)
        effort = re.sub(r"[^A-Za-z0-9._-]+", "-", self.effort)
        return f"{model}__t{self.temperature:.2f}__{self.prompt_id}__e{effort}"

    def as_params(self) -> dict:
        return {"model": self.model, "temperature": self.temperature, "prompt_id": self.prompt_id,
                "effort": self.effort}


class InvalidJudgeOutput(Exception):
    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


class CriterionVerdict(BaseModel):
    evidence: str = Field(description="Justification for this criterion, written before the verdict.")
    passed: bool = Field(description="true if the criterion PASSES, false if it FAILS.")


# One field per rubric criterion, generated from CRITERIA_KEYS so the schema can't drift from the rubric.
CriteriaReview = create_model(
    "CriteriaReview",
    scratchpad=(str, Field(default="", description="Claim-to-log-line audit; empty unless the task asks for it.")),
    **{key: (CriterionVerdict, ...) for key in CRITERIA_KEYS},
)

def build_prompt(config: JudgeConfig, item: dict) -> JudgePrompt:
    return get_criteria_judge_prompt(
        prompt_id=config.prompt_id,
        log_lines=item["log_lines"],
        session_based=item["session_based"],
        sequence_classification=item["sequence_classification"],
        dataset_name=item["dataset"],
        explanation=item["explanation"],
    )


def build_messages(config: JudgeConfig, item: dict) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    prompt = build_prompt(config, item)
    messages = [SystemMessage(prompt.system)] if prompt.system else []
    return messages + [HumanMessage(prompt.user)]


def prompt_fingerprint(prompt_id: str) -> str:
    """Hash of the prompt template (system + user text, with dummy input) and the output schema. Stored
    with each run file so edited wording invalidates cached verdicts instead of silently reusing them."""
    dummy = {"log_lines": ["1. x"], "session_based": False, "sequence_classification": "normal",
             "dataset": "d", "explanation": "e"}
    prompt = build_prompt(JudgeConfig("m", 0.0, prompt_id, "low"), dummy)
    text = f"{prompt.system}\n---\n{prompt.user}" + json.dumps(CriteriaReview.model_json_schema())
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def item_fingerprint(item: dict) -> str:
    """Hash of everything the judge is shown for this item (not the human verdicts)."""
    payload = json.dumps([item["log_lines"], item["sequence_classification"], item["explanation"]])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def parse_review(raw: str):
    """Fallback for when the model ignored the tool call and put JSON in its text: extracts the first
    JSON object (ignoring <think> blocks and code fences) and validates it. Raises InvalidJudgeOutput."""
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start == -1:
        raise InvalidJudgeOutput("no JSON object in reply", raw)
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return CriteriaReview.model_validate(obj)
    except (json.JSONDecodeError, ValidationError) as e:
        raise InvalidJudgeOutput(f"{type(e).__name__}: {str(e)[:300]}", raw) from e


_llm_cache: dict = {}


def _structured_llm(model: str, temperature: float, effort: str):
    key = (model, temperature, effort)
    if key not in _llm_cache:
        from langchain_litellm import ChatLiteLLM  # lazy: tests that mock the judge need no LLM stack

        llm = ChatLiteLLM(
            model=model,
            temperature=temperature,
            api_key=os.environ.get("LITELLM_API_KEY"),
            api_base=os.environ.get("LITELLM_API_BASE"),
            custom_llm_provider="openai",
            request_timeout=REQUEST_TIMEOUT_S,
            max_tokens=MAX_OUTPUT_TOKENS,
            model_kwargs={"reasoning_effort": effort},
            max_retries=0,  # retries are handled in _invoke so transport and format failures stay separate
        )
        _llm_cache[key] = llm.with_structured_output(CriteriaReview, include_raw=True)
    return _llm_cache[key]


def _invoke(structured_llm, messages) -> dict:
    for attempt in range(TRANSPORT_ATTEMPTS):
        try:
            return structured_llm.invoke(messages)
        except Exception:
            if attempt == TRANSPORT_ATTEMPTS - 1:
                raise
            time.sleep(2 ** attempt * 2)


def _review_from(result: dict):
    """result = {"raw": AIMessage, "parsed": CriteriaReview | None, "parsing_error": Exception | None}"""
    if result.get("parsed") is not None:
        return result["parsed"]
    raw_text = result["raw"].content if isinstance(result["raw"].content, str) else str(result["raw"].content)
    try:
        return parse_review(raw_text)
    except InvalidJudgeOutput as e:
        error = result.get("parsing_error")
        raise InvalidJudgeOutput(f"structured output failed ({error}); text fallback: {e}", raw_text) from e


def call_judge(config: JudgeConfig, item: dict) -> dict:
    """Returns {"scores", "evidence", "scratchpad"}. Raises InvalidJudgeOutput or a transport exception."""
    from langchain_core.messages import HumanMessage

    llm = _structured_llm(config.model, config.temperature, config.effort)
    messages = build_messages(config, item)

    result = _invoke(llm, messages)
    try:
        review = _review_from(result)
    except InvalidJudgeOutput as first_error:
        messages += [result["raw"], HumanMessage(
            f"That reply could not be parsed ({str(first_error)[:300]}). Answer again, filling in the required output schema.")]
        review = _review_from(_invoke(llm, messages))  # a second failure propagates

    return {
        "scores": {k: bool(getattr(review, k).passed) for k in CRITERIA_KEYS},
        "evidence": {k: getattr(review, k).evidence for k in CRITERIA_KEYS},
        "scratchpad": review.scratchpad,
    }
