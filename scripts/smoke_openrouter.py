"""T2.6: model preflight investigation. Tests candidate free vision models
on OpenRouter for two properties -- image support, and reliably parseable
JSON -- with 2 calls each against a real diagram to check consistency, not
just a single sample. Not part of the shipped package."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

env_path = Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"'))

from umlregen.perception.openrouter import OpenRouterClient

CANDIDATES = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "dots-studio/dots-3-note-preview:free",
]
CALLS_PER_MODEL = 2

image_bytes = Path("corpus/img/ecommerce_checkout.png").read_bytes()
prompt = (
    "How many classes (boxes) are in this UML class diagram, and what are "
    'their names? Answer with a single JSON object: '
    '{"class_count": <integer>, "class_names": [<string>, ...]}. '
    "No other text."
)

EXPECTED_NAMES = {
    "CreditCard", "Customer", "PaymentMethod", "Order",
    "Person", "OrderLine", "PaymentGateway", "Product",
}

for model_id in CANDIDATES:
    print("=" * 70)
    print("model:", model_id)
    client = OpenRouterClient(model_id=model_id, timeout=90.0, requests_per_minute=15.0)

    valid_json_count = 0
    correct_count_count = 0
    for i in range(CALLS_PER_MODEL):
        try:
            response = client.complete(image_bytes, prompt)
        except Exception as exc:  # noqa: BLE001 -- investigation script
            print(f"  call {i + 1}: ERROR {type(exc).__name__}: {exc}")
            continue

        is_valid_json = isinstance(response.parsed_json, dict) and "class_count" in response.parsed_json
        if is_valid_json:
            valid_json_count += 1
            names = set(response.parsed_json.get("class_names", []))
            is_correct = response.parsed_json.get("class_count") == 8 and names == EXPECTED_NAMES
            if is_correct:
                correct_count_count += 1
        print(
            f"  call {i + 1}: tokens(p/c)={response.prompt_tokens}/{response.completion_tokens} "
            f"cost=${response.cost_usd} valid_json={is_valid_json} raw[:120]={response.raw_text[:120]!r}"
        )

    print(f"  => valid_json {valid_json_count}/{CALLS_PER_MODEL}, exactly_correct {correct_count_count}/{CALLS_PER_MODEL}")
