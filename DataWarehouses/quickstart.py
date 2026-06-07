"""Quickstart example using the official `mistralai` SDK.

Usage:
1. Install the SDK: `pip install mistralai`
2. Ensure MISTRAL_API_KEY is set in environment or .env
3. Run: `python quickstart.py`
"""
import os
from dotenv import load_dotenv

load_dotenv()

try:
    from mistralai import Mistral
except Exception as exc:
    raise SystemExit("Please install mistralai (pip install mistralai)") from exc


def main():
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise SystemExit("MISTRAL_API_KEY not set in environment or .env")

    client = Mistral(api_key=api_key)

    response = client.chat.complete(
        model=os.getenv("MISTRAL_MODEL", "mistral-large-latest"),
        messages=[{"role": "user", "content": "Hello from the quickstart example. Please respond briefly."}],
    )

    # Print the assistant's content in a defensive way
    try:
        content = response.choices[0].message.content
    except Exception:
        # Fallback for other response shapes
        content = getattr(response, "output", str(response))

    print("Assistant response:\n", content)


if __name__ == "__main__":
    main()
