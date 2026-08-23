import asyncio
import base64
import json
import os
from functools import lru_cache
from typing import Any, Sequence

from google import genai
from google.genai import errors, types

DEFAULT_MODEL = "gemini-3.6-flash"

# generous: the search-grounded call is slow, and a false timeout is worse than none
REQUEST_TIMEOUT_MS = 300_000

# retry transient failures only; a 4xx would just buy the same rejection
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 2.0

IMAGE_MIME_TYPE = "image/jpeg"


# the model could not be reached, or said nothing usable
class GeminiError(RuntimeError):
    pass


# no api key, so nothing can be sent at all
class GeminiNotConfigured(GeminiError):
    pass


# one client for the process, built on first use
@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiNotConfigured("GEMINI_API_KEY is not set")
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )


# turn base64 captures into image parts, refusing anything malformed
def decode_images(images: Sequence[str]) -> list[types.Part]:
    parts = []
    for i, b64 in enumerate(images):
        try:
            raw = base64.b64decode("".join(b64.split()), validate=True)
        except ValueError as exc:
            raise ValueError(f"image {i} is not valid base64") from exc
        if not raw:
            raise ValueError(f"image {i} is empty")
        parts.append(types.Part.from_bytes(data=raw, mime_type=IMAGE_MIME_TYPE))
    return parts


# send a prompt to the model and hand back its text
async def generate(
    prompt: str,
    images: Sequence[str] = (),
    model: str | None = None,
    response_schema: Any = None,
    tools: Sequence[types.Tool] | None = None,
) -> str:
    # pictures before the instruction: the model follows it better that way
    parts = [*decode_images(images), types.Part.from_text(text=prompt)]

    # a schema forces json; tools switch on search grounding. never both at once
    config = None
    if response_schema is not None or tools is not None:
        config = types.GenerateContentConfig(
            response_mime_type="application/json" if response_schema is not None else None,
            response_schema=response_schema,
            tools=tools,
        )

    model_name = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
    contents = [types.Content(role="user", parts=parts)]

    # retry loop, exponential backoff between tries
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await get_client().aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            break
        except errors.APIError as exc:
            if attempt == MAX_ATTEMPTS or not _is_transient(exc):
                raise GeminiError(f"Gemini request failed: {exc}") from exc
            delay = BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"[gemini] {exc.code} on attempt {attempt}, retrying in {delay:.0f}s")
            await asyncio.sleep(delay)

    text = response.text
    if not text:
        raise GeminiError(f"Gemini returned no text ({_no_text_reason(response)})")
    return text


# same as generate, but hand back parsed json
async def generate_json(
    prompt: str,
    response_schema: Any,
    images: Sequence[str] = (),
    model: str | None = None,
    tools: Sequence[types.Tool] | None = None,
) -> Any:
    text = await generate(prompt, images, model, response_schema=response_schema, tools=tools)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini returned malformed JSON: {exc}") from exc


# failures a retry can plausibly fix: 5xx and rate limiting
def _is_transient(exc: errors.APIError) -> bool:
    return isinstance(exc, errors.ServerError) or getattr(exc, "code", None) == 429


# best guess at why an answer came back empty, for the error message
def _no_text_reason(response: types.GenerateContentResponse) -> str:
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason is not None:
        return f"prompt blocked: {feedback.block_reason}"
    if response.candidates:
        return f"finish reason: {response.candidates[0].finish_reason}"
    return "no candidates returned"
