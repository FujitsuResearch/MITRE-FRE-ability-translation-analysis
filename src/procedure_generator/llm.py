"""LLM client utilities."""

import json
import os

from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel

from procedure_generator.logger import ProcedureLogger

logger = ProcedureLogger(__name__)


def _get_client(model: str) -> ChatOpenAI:
    """Get configured LangChain ChatOpenAI client."""
    api_key = os.environ["OPENAI_API_KEY"]
    api_base = os.getenv("OPENAI_API_BASE")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=api_base,
    )


def call_llm_vllm(
    system_prompt: str, user_content: str, model: str, output_format: BaseModel | None = None
) -> tuple[str, dict]:
    """Call the LLM API (for LLMs using vLLM as inference provider) and return the response text and token usage."""

    api_key = os.environ["OPENAI_API_KEY"]
    api_base = os.getenv("OPENAI_API_BASE")

    client = OpenAI(api_key=api_key, base_url=api_base)

    response = None

    if output_format:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            extra_body={"guided_json": json.dumps(output_format.model_json_schema())},
        )
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )

    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }

    logger.info(f"Tokens - Input: {usage['prompt_tokens']}, Output: {usage['completion_tokens']}")

    return response.choices[0].message.content, usage


def call_llm_structured[T: BaseModel](
    system_prompt: str,
    user_content: str,
    model: str,
    response_format: type[T],
) -> tuple[T, dict]:
    """Call the LLM API with structured output and return parsed Pydantic model."""
    client = _get_client(model)
    structured_client = client.with_structured_output(response_format, include_raw=True)

    response = structured_client.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    )

    parsed_model = response["parsed"]
    raw_message = response["raw"]

    usage = {
        "prompt_tokens": raw_message.usage_metadata["input_tokens"],
        "completion_tokens": raw_message.usage_metadata["output_tokens"],
        "total_tokens": raw_message.usage_metadata["total_tokens"],
    }

    logger.info(f"[structured] Received {type(response).__name__}")

    return parsed_model, usage
