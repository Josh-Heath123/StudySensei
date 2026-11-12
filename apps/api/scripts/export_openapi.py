"""Write the API's OpenAPI schema to the web app, without starting a server.

Run with: uv run python -m scripts.export_openapi
"""

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "api" / "openapi.json"

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"Wrote {OUT}")
