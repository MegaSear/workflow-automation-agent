#!/usr/bin/env python
"""Send a minimal request to the configured OpenAI-compatible LLM endpoint."""

import sys
from urllib.parse import urlsplit

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from react_agent.backend.config import settings


def main() -> int:
    if not settings.LLM_API_KEY.strip():
        print("FAILED: LLM_API_KEY is empty or not configured.")
        return 1
    if not settings.LLM_MODEL.strip():
        print("FAILED: LLM_MODEL is empty or not configured.")
        return 1

    try:
        hostname = urlsplit(settings.LLM_BASE_URL).hostname
    except ValueError:
        hostname = None

    if not hostname:
        print("FAILED: LLM_BASE_URL is invalid or has no hostname.")
        return 1

    print(f"LLM host: {hostname}")
    print(f"Model: {settings.LLM_MODEL}")

    try:
        client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=30.0,
            max_retries=0,
        )
    except OpenAIError as error:
        print(f"FAILED: could not configure the OpenAI client ({type(error).__name__}).")
        return 1

    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": "Reply with OK."}],
        )
    except AuthenticationError:
        print("FAILED: API key was rejected (HTTP 401).")
        return 1
    except PermissionDeniedError:
        print("FAILED: provider denied access (HTTP 403). Check model access and account.")
        return 1
    except NotFoundError:
        print("FAILED: endpoint or model was not found (HTTP 404).")
        return 1
    except RateLimitError:
        print("FAILED: request was rate-limited (HTTP 429).")
        return 1
    except APITimeoutError:
        print("FAILED: request timed out.")
        return 1
    except APIConnectionError as error:
        print(
            f"FAILED: could not connect ({type(error).__name__}). "
            "Check URL, DNS, TLS, and network."
        )
        return 1
    except APIStatusError as error:
        print(f"FAILED: provider returned HTTP {error.status_code}.")
        return 1
    except OpenAIError as error:
        print(f"FAILED: OpenAI client error ({type(error).__name__}).")
        return 1

    reply = response.choices[0].message.content
    print(f"OK: LLM responded successfully (response ID: {response.id}).")
    if reply:
        print(f"Reply: {reply.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
