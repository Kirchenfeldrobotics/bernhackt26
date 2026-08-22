"""LLM access for the API routes, over any OpenAI-compatible provider.

One lazily created client, shared by every request. Which provider answers is
purely configuration -- three environment variables, no code change:

    LLM_API_KEY    key for that provider
    LLM_BASE_URL   defaults to https://api.openai.com/v1
    LLM_MODEL      defaults to gpt-4o

OpenAI as-is; Google models via an OpenRouter base_url; onprem.ai by pointing
LLM_BASE_URL at the local gateway.
"""
import base64
import copy
import json
import os
from functools import lru_cache
from typing import Any, Sequence

import openai
from openai import AsyncOpenAI

DEFAULT_MODEL = "gpt-4o"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

# The VR app sends JPEG captures, and /send-to-gemini takes them the same way:
# raw base64, no data-URL prefix.
IMAGE_MIME_TYPE = "image/jpeg"


class LLMError(RuntimeError):
    """The provider could not be reached, or returned nothing we can pass on."""


class LLMNotConfigured(LLMError):
    """No API key, so no request can be made at all."""


@lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise LLMNotConfigured("LLM_API_KEY is not set")
    # `or` rather than a getenv default: a variable that is set but empty
    # (LLM_BASE_URL="") must fall back too.
    return AsyncOpenAI(api_key=api_key, base_url=os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL)


def decode_images(images: Sequence[str]) -> list[dict]:
    """Turn base64 strings into image content parts. Raises ValueError on bad input."""
    parts = []
    for i, b64 in enumerate(images):
        try:
            # Whitespace is stripped first so line-wrapped base64 still decodes.
            raw = base64.b64decode("".join(b64.split()), validate=True)
        except ValueError as exc:  # binascii.Error subclasses ValueError
            raise ValueError(f"image {i} is not valid base64") from exc
        if not raw:
            raise ValueError(f"image {i} is empty")
        # Re-encoded from the decoded bytes, so padding and line breaks are
        # normalised before the data: URL goes over the wire.
        clean = base64.b64encode(raw).decode()
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{IMAGE_MIME_TYPE};base64,{clean}"},
        })
    return parts


def strict_json_schema(schema: Any) -> dict:
    """Build an OpenAI `json_schema` response_format from a pydantic model.

    Strict structured output requires every object to list all its properties in
    `required` and to forbid extras, which is not what pydantic emits by default.
    """
    root = schema.model_json_schema()
    _tighten(root, root)
    return {
        "type": "json_schema",
        "json_schema": {"name": schema.__name__, "schema": root, "strict": True},
    }


# Maps of name -> schema, whose keys are field names rather than JSON Schema
# keywords, so they must be recursed into rather than treated as schema nodes.
_SCHEMA_MAPS = ("properties", "$defs", "definitions")


def _tighten(node: Any, root: dict) -> None:
    """Recursively mark every object node required-in-full and closed."""
    if isinstance(node, list):
        for item in node:
            _tighten(item, root)
        return
    if not isinstance(node, dict):
        return

    # A $ref carrying sibling keys (pydantic emits one per described nested
    # model) is ambiguous, so inline the target and let the siblings win.
    if "$ref" in node and len(node) > 1:
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        target = copy.deepcopy(_resolve(node["$ref"], root))
        node.clear()
        node.update(target)
        node.update(siblings)

    # `default` is not part of the strict structured-output keyword subset, and
    # pydantic emits it for every Optional field. Left in, the provider rejects
    # the whole schema.
    node.pop("default", None)

    properties = node.get("properties")
    if node.get("type") == "object" and isinstance(properties, dict):
        node["required"] = list(properties)
        node["additionalProperties"] = False

    for key, value in node.items():
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            for sub_schema in value.values():
                _tighten(sub_schema, root)
        else:
            _tighten(value, root)


def _resolve(ref: str, root: dict) -> dict:
    """Look up a local "#/$defs/Name" pointer in the schema it came from."""
    node: Any = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


async def generate(
    prompt: str,
    images: Sequence[str] = (),
    model: str | None = None,
    response_schema: Any = None,
) -> str:
    """Send a prompt plus optional base64 images to the model, return its text.

    With a response_schema (a pydantic model) the answer is constrained to JSON
    matching it. Providers that do not implement strict `json_schema` fall back
    to plain JSON mode, which is checked against the schema by the caller.

    Raises ValueError if an image is not decodable, LLMError if the call fails
    or comes back without any text.
    """
    # Images first, prompt last: models follow the instruction better when they
    # already have the pictures in context. Text-only stays a plain string,
    # which the stricter gateways are happier with than a one-item list.
    content: Any = [*decode_images(images), {"type": "text", "text": prompt}] if images else prompt
    messages = [{"role": "user", "content": content}]

    model_name = model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
    response_format = strict_json_schema(response_schema) if response_schema is not None else None

    try:
        response = await _create(messages, model_name, response_format)
    except openai.BadRequestError as exc:
        if response_format is None:
            raise LLMError(f"LLM request failed: {exc}") from exc
        # The provider does not do strict json_schema. Ask for plain JSON and
        # let the caller validate the shape.
        try:
            response = await _create(
                _with_json_hint(messages, prompt, images), model_name, {"type": "json_object"}
            )
        except openai.APIError as retry_exc:
            raise LLMError(f"LLM request failed: {retry_exc}") from retry_exc
    except openai.APIError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    text = response.choices[0].message.content if response.choices else None
    if not text:
        raise LLMError(f"the model returned no text ({_no_text_reason(response)})")
    return text


async def _create(messages: list, model: str, response_format: dict | None):
    """One chat completion. Kept separate so the JSON fallback can reuse it."""
    kwargs: dict = {"model": model, "messages": messages}
    if response_format is not None:
        kwargs["response_format"] = response_format
    return await get_client().chat.completions.create(**kwargs)


def _with_json_hint(messages: list, prompt: str, images: Sequence[str]) -> list:
    """Plain JSON mode requires the word "json" in the request, so say it."""
    hint = prompt + "\n\nRespond with JSON only, and nothing else."
    content: Any = [*decode_images(images), {"type": "text", "text": hint}] if images else hint
    return [{"role": "user", "content": content}]


async def generate_json(
    prompt: str,
    response_schema: Any,
    images: Sequence[str] = (),
    model: str | None = None,
) -> Any:
    """Same as generate(), but the answer is decoded JSON instead of text.

    The schema is enforced by the provider where it supports strict mode, so
    malformed JSON should be impossible; it is still checked here rather than
    handed on as a surprise for the caller.
    """
    text = await generate(prompt, images, model, response_schema=response_schema)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"the model returned malformed JSON: {exc}") from exc


def _no_text_reason(response: Any) -> str:
    """Best explanation available for an answer with no text in it."""
    if not response.choices:
        return "no choices returned"
    finish_reason = response.choices[0].finish_reason
    if finish_reason:
        # "content_filter" is where a blocked prompt surfaces here.
        return f"finish reason: {finish_reason}"
    return "empty message content"
