"""
One place that builds the chat agents' LLM calls.

Groq is the default provider. A second API key (GROQ_API_KEY_2) is tried once
if the first call fails, because Groq limits requests per key. The model name
is configurable through CHAT_MODEL so a different model can be tried without a
code change.
"""
from __future__ import annotations

import os
from typing import TypeVar

from langchain_groq import ChatGroq
from pydantic import BaseModel

CHAT_MODEL = os.environ.get("CHAT_MODEL", "openai/gpt-oss-120b")

T = TypeVar("T", bound=BaseModel)


def _keys() -> list[str]:
    return [k for k in (os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_API_KEY_2")) if k]


def invoke_structured(schema: type[T], prompt: str, temperature: float = 0.0, reasoning_effort: str | None = None) -> T:
    last_error: Exception | None = None
    for key in _keys():
        try:
            extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
            llm = ChatGroq(model=CHAT_MODEL, temperature=temperature, api_key=key, timeout=30, max_retries=1, **extra)
            # json_schema, not the default tool-calling: gpt-oss on Groq sometimes writes the JSON as plain
            # text instead of calling the tool ("Tool choice is required"), which failed 7 of 12 test calls.
            return llm.with_structured_output(schema, method="json_schema").invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - try the next key, then surface the last error
            last_error = exc
    raise last_error or RuntimeError("No GROQ_API_KEY configured")
