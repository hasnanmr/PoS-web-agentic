"""Write the API's OpenAPI schema to docs/api/openapi.json (T-009 contract check).

    uv run python -m app.tools.export_openapi            # write the file
    uv run python -m app.tools.export_openapi --check    # fail if the file is out of date

CI runs `--check`, so any change to endpoints or response models must update the
committed schema in the same change (and the screen-endpoint map, see CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import Settings
from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.json"


def render() -> str:
    app = create_app(Settings(app_env="local", log_level="WARNING"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    content = render()
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != content:
            print(
                f"{OUTPUT} is out of date. Run: cd backend && uv run python -m "
                "app.tools.export_openapi",
                file=sys.stderr,
            )
            return 1
        print("openapi.json is up to date")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content)
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
