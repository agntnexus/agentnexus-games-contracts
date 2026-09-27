"""Reference check of a provider manifest's form and compatibility, for `agentnexus-games-v1`.

It runs the cases in `vectors/manifest-v1/` and nothing else: it is test code. Admission is
administrative and belongs to `#87`, and every value of a deadline, rate or retention belongs to
`#82` and `#87`; this check says only whether a manifest has the form `D-123` and `D-124` fix and fits
this contract. It refuses, naming each reason it finds:

- `schema`: the manifest is not the strict form of `protocol/v1/manifest.schema.json`;
- `origin`: an origin is not `https`;
- `contract_version`: none of its contract versions is one this contract implements;
- `game_version`: a game version has no directory in `games/`;
- `operations`: the operations are not exactly `move` and `resign`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from json_schema import valid

IMPLEMENTED: Final = frozenset({"agentnexus-games-v1"})
OPERATIONS: Final = ("move", "resign")


def check(manifest: Any, root: Path) -> list[str]:
    """Every reason the manifest is refused for; an empty list means it is accepted."""
    reasons = []
    origins = manifest.get("origins") if isinstance(manifest, dict) else None
    if isinstance(origins, list) and any(
        isinstance(origin, str) and not origin.startswith("https://")
        for origin in origins
    ):
        reasons.append("origin")
    schema_path = root / "protocol" / "v1" / "manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not valid(manifest, schema):
        return [*reasons, "schema"]
    if not set(manifest["contract_versions"]) & IMPLEMENTED:
        reasons.append("contract_version")
    for game in manifest["games"]:
        if not list(
            (root / "games").glob(f"*/{game['game_version']}/move.schema.json")
        ):
            reasons.append("game_version")
    if tuple(sorted(manifest["operations"])) != OPERATIONS:
        reasons.append("operations")
    return reasons
