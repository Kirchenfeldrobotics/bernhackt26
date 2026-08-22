"""Gemini access for the API routes.

One lazily created client, shared by every request. The API key comes from
GEMINI_API_KEY (see server/.env), the model from GEMINI_MODEL.
"""
import base64
import json
import os
from functools import lru_cache
from typing import Any, Sequence

from google import genai
from google.genai import errors, types

DEFAULT_MODEL = "gemini-2.5-flash"

# The VR app sends JPEG captures, and /send-to-gemini takes them the same way:
# raw base64, no data-URL prefix.
IMAGE_MIME_TYPE = "image/jpeg"


class GeminiError(RuntimeError):
    """Gemini could not be reached, or returned nothing we can pass on."""


class GeminiNotConfigured(GeminiError):
    """No API key, so no request can be made at all."""


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiNotConfigured("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


def decode_images(images: Sequence[str]) -> list[types.Part]:
    """Turn base64 strings into image parts. Raises ValueError on bad input."""
    parts = []
    for i, b64 in enumerate(images):
        try:
            # Whitespace is stripped first so line-wrapped base64 still decodes.
            raw = base64.b64decode("".join(b64.split()), validate=True)
        except ValueError as exc:  # binascii.Error subclasses ValueError
            raise ValueError(f"image {i} is not valid base64") from exc
        if not raw:
            raise ValueError(f"image {i} is empty")
        parts.append(types.Part.from_bytes(data=raw, mime_type=IMAGE_MIME_TYPE))
    return parts


async def generate(
    prompt: str,
    images: Sequence[str] = (),
    model: str | None = None,
    response_schema: Any = None,
    tools: Sequence[types.Tool] | None = None,
) -> str:
    """Send a prompt plus optional base64 images to Gemini, return its text.

    With a response_schema (a pydantic model or a genai Schema) the answer is
    constrained to JSON matching it, so no other shape can come back.

    `tools` turns on Gemini-side tools such as search grounding (pass
    `[types.Tool(google_search=types.GoogleSearch())]`). The Gemini API does not
    accept `tools` together with a forced JSON `response_schema` in the same
    request, so a caller that needs both must make two calls -- one grounded and
    schema-free, one schema-constrained -- rather than passing both here at once.

    Raises ValueError if an image is not decodable, GeminiError if the call
    fails or comes back without any text.
    """
    # Images first, prompt last: Gemini follows the instruction better when it
    # already has the pictures in context.
    parts = [*decode_images(images), types.Part.from_text(text=prompt)]

    config = None
    if response_schema is not None or tools is not None:
        config = types.GenerateContentConfig(
            response_mime_type="application/json" if response_schema is not None else None,
            response_schema=response_schema,
            tools=tools,
        )

    try:
        response = await get_client().aio.models.generate_content(
            # `or` rather than a getenv default: an env var that is set but
            # empty (GEMINI_MODEL="") must fall back too.
            model=model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )
    except errors.APIError as exc:
        raise GeminiError(f"Gemini request failed: {exc}") from exc

    text = response.text
    if not text:
        raise GeminiError(f"Gemini returned no text ({_no_text_reason(response)})")
    return text


async def generate_json(
    prompt: str,
    response_schema: Any,
    images: Sequence[str] = (),
    model: str | None = None,
    tools: Sequence[types.Tool] | None = None,
) -> Any:
    """Same as generate(), but the answer is decoded JSON instead of text.

    The schema is enforced by the API while the answer is being decoded, so
    malformed JSON should be impossible; it is still checked here rather than
    handed on as a surprise for the caller. See generate() for why combining
    `tools` with the forced schema here is the caller's responsibility to avoid.
    """
    text = await generate(prompt, images, model, response_schema=response_schema, tools=tools)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini returned malformed JSON: {exc}") from exc


def _no_text_reason(response: types.GenerateContentResponse) -> str:
    """Best explanation available for an answer with no text in it."""
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason is not None:
        return f"prompt blocked: {feedback.block_reason}"
    if response.candidates:
        return f"finish reason: {response.candidates[0].finish_reason}"
    return "no candidates returned"
