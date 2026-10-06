import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Make the Django project importable when this script is run directly.
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django

django.setup()

from bescheidcheck.services.extraction import extract_structured_data


MODELS = [
    "verdigado-think",
    "verdigado-pro",
    "verdigado-translate",
]

CASE_DIR = Path(__file__).parent / "dublin_001"
INPUT_FILE = CASE_DIR / "input_ocr.txt"
RESULTS_DIR = CASE_DIR / "results"

BESCHEID_TYPE = "dublin_decision"


async def run_model(model: str, document_text: str) -> None:
    print(f"\nRunning {model}...")

    started = time.monotonic()

    extracted_data = await extract_structured_data(
        document_text=document_text,
        bescheid_type=BESCHEID_TYPE,
        model=model,
    )

    elapsed = round(time.monotonic() - started, 2)

    result = {
        "model": model,
        "seconds": elapsed,
        "document_type_input": BESCHEID_TYPE,
        "extracted_data": extracted_data,
    }

    output_file = RESULTS_DIR / f"{model}.json"

    output_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Finished in {elapsed}s")
    print(f"Saved: {output_file}")


async def main() -> None:
    document_text = INPUT_FILE.read_text(encoding="utf-8")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for model in MODELS:
        await run_model(model, document_text)


if __name__ == "__main__":
    asyncio.run(main())