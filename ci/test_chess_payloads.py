"""Chess's own payloads, `chess-1` and `chess-1-solo`, and their size limits, as D-170 fixes them.

The schemas in `games/chess/` and the cases in `vectors/chess-1-payloads/cases.json` are checked
here against the values `D-170` accepted: the move with its UCI vocabulary and typed draw claim,
the observation with the data class and retained flag of every field, the spectator view without
the seat's own fields, the game bounds, and the body limit of every message. The move vocabulary is
derived here on its own, so the schema cannot drift from the rule it states.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from game_payloads import (
    BOUND_KEY,
    CLASS_KEY,
    RETAINED_KEY,
    message_limit,
    message_verdict,
    payload_verdict,
    schema_refusals,
)
from json_schema import valid

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "games" / "chess" / "chess-1"
SOLO = ROOT / "games" / "chess" / "chess-1-solo"
VECTOR = ROOT / "vectors" / "chess-1-payloads" / "cases.json"
SCHEMAS = ("move.schema.json", "observation.schema.json", "spectator.schema.json")

#: What `D-170` accepted, restated so that neither the schemas nor the vector can drift from it.
ACCEPTED_CLAIMS = ["threefold_repetition", "fifty_moves"]
ACCEPTED_FIELDS = {
    "board": ("public", True),
    "you_are": ("public", False),
    "to_move": ("public", True),
    "in_check": ("public", True),
    "castling": ("public", True),
    "en_passant": ("public", True),
    "halfmove_clock": ("public", True),
    "fullmove_number": ("public", True),
    "moves": ("public", True),
    "last_move": ("public", True),
    "result": ("public", True),
    "legal_moves": ("seat_private", False),
    "claimable_draws": ("seat_private", False),
}
ACCEPTED_REASONS = {
    "checkmate",
    "stalemate",
    "dead_position",
    "threefold_repetition",
    "fifty_moves",
    "fivefold_repetition",
    "seventy_five_moves",
    "resignation",
    "timeout",
    "timeout_versus_insufficient_material",
    "seats_not_bound",
    "computer_unavailable",
    "match_time_limit",
    "ply_limit",
    "provider_stopped",
}
ACCEPTED_BOUNDS = {"move": 128, "observation": 8192}
ACCEPTED_CEILINGS = {"move": 4096, "observation": 65536}
ACCEPTED_PLIES = 400
ACCEPTED_LIMITS = {
    "redemption": (4096, "too_large"),
    "resumption": (1024, "too_large"),
    "action": (1024 + 4096, "too_large"),
    "resignation_instruction": (2048, "too_large"),
    "resignation_acknowledgement": (1024, None),
    "seat_answer": (1024 + 8192, None),
    "refusal": (1024, None),
}


def uci_moves() -> list[str]:
    """Every move a piece could make on an empty board, derived without the schema."""
    files = "abcdefgh"

    def name(file: int, rank: int) -> str:
        return files[file] + str(rank + 1)

    knight = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
    lines = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    found = []
    for rank in range(8):
        for file in range(8):
            targets = {
                (file + df, rank + dr)
                for df, dr in knight
                if 0 <= file + df < 8 and 0 <= rank + dr < 8
            }
            for df, dr in lines:
                step = 1
                while 0 <= file + df * step < 8 and 0 <= rank + dr * step < 8:
                    targets.add((file + df * step, rank + dr * step))
                    step += 1
            ordered = sorted(targets, key=lambda target: target[1] * 8 + target[0])
            found.extend(name(file, rank) + name(*target) for target in ordered)
    for origin, target in ((6, 7), (1, 0)):
        for file in range(8):
            for side in (-1, 0, 1):
                if 0 <= file + side < 8:
                    found.extend(
                        name(file, origin) + name(file + side, target) + piece
                        for piece in "qrbn"
                    )
    return found


def schema(payload: str, game: Path = GAME) -> dict[str, Any]:
    return json.loads((game / f"{payload}.schema.json").read_text(encoding="utf-8"))


def vector() -> dict[str, Any]:
    return json.loads(VECTOR.read_text(encoding="utf-8"))


def plus() -> dict[str, int]:
    return {
        "move_ceiling": vector()["shared_ceilings"]["move"],
        "observation_bound": schema("observation")[BOUND_KEY],
    }


def names(kind: str) -> list[str]:
    return [case["name"] for case in json.loads(VECTOR.read_text("utf-8"))[kind]]


def case(kind: str, name: str) -> dict[str, Any]:
    (found,) = [c for c in vector()[kind] if c["name"] == name]
    return found


def padded(value: Any, length: int) -> str:
    text = json.dumps(value, separators=(",", ":"))
    assert len(text) <= length, "the case pads to less than its compact value"
    return text + " " * (length - len(text))


# The move vocabulary.


def test_the_vocabulary_is_every_queen_or_knight_line_and_every_promotion() -> None:
    moves = uci_moves()
    assert len(moves) == 1968
    assert len(set(moves)) == 1968
    assert sum(len(move) == 5 for move in moves) == 176


# Where the schemas are, and what they hold.


@pytest.mark.parametrize("game", [GAME, SOLO], ids=["chess-1", "chess-1-solo"])
def test_each_game_version_has_its_own_directory(game: Path) -> None:
    assert sorted(path.name for path in game.glob("*")) == ["README.md", *SCHEMAS]


def test_the_vector_names_its_game_version_and_schemas() -> None:
    assert vector()["game_version"] == "chess-1"
    assert vector()["decision"] == "D-170"
    assert vector()["schemas"] == {
        payload: f"games/chess/chess-1/{payload}.schema.json"
        for payload in ("move", "observation")
    }


@pytest.mark.parametrize("payload", ["move", "observation"])
def test_each_schema_keeps_every_rule(payload: str) -> None:
    assert schema_refusals(schema(payload), payload, ACCEPTED_CEILINGS) == []


def test_the_move_is_what_d170_accepted() -> None:
    move = schema("move")
    assert move["properties"] == {
        "uci": {"enum": uci_moves()},
        "claim": {"enum": ACCEPTED_CLAIMS},
    }
    assert move["anyOf"] == [{"required": ["uci"]}, {"required": ["claim"]}]
    assert "required" not in move
    assert move[BOUND_KEY] == ACCEPTED_BOUNDS["move"]


def test_the_observation_is_what_d170_accepted() -> None:
    observation = schema("observation")
    fields = observation["properties"]
    assert observation["required"] == list(ACCEPTED_FIELDS)
    assert {
        name: (field[CLASS_KEY], field[RETAINED_KEY]) for name, field in fields.items()
    } == ACCEPTED_FIELDS
    assert observation[BOUND_KEY] == ACCEPTED_BOUNDS["observation"]
    assert fields["moves"]["maxItems"] == ACCEPTED_PLIES
    assert fields["moves"]["items"] == {"enum": uci_moves()}
    assert fields["legal_moves"]["items"] == {"enum": uci_moves()}
    assert fields["last_move"]["enum"] == [None, *uci_moves()]
    assert fields["claimable_draws"]["items"] == {"enum": ACCEPTED_CLAIMS}
    (ended,) = [
        form for form in fields["result"]["anyOf"] if form.get("type") == "object"
    ]
    assert set(ended["properties"]["reason"]["enum"]) == ACCEPTED_REASONS


def test_the_spectator_view_is_the_public_observation_without_the_viewer() -> None:
    """Neither `you_are` nor a seat-private field reaches a viewer."""
    observation = schema("observation")
    spectator = schema("spectator")
    public = {
        name: field
        for name, field in observation["properties"].items()
        if field[CLASS_KEY] == "public" and name != "you_are"
    }
    assert spectator["properties"] == public
    assert spectator["required"] == list(public)
    assert spectator["additionalProperties"] is False


def test_the_ceilings_and_body_limits_are_what_d170_accepted() -> None:
    doc = vector()
    assert doc["shared_ceilings"] == ACCEPTED_CEILINGS
    limits = {
        entry["message"]: (message_limit(entry, plus()), entry["over_limit_code"])
        for entry in doc["message_limits"]
    }
    assert limits == ACCEPTED_LIMITS


# The cases as published.


@pytest.mark.parametrize("name", names("move_cases"))
def test_each_move_case_gets_its_published_verdict(name: str) -> None:
    c = case("move_cases", name)
    assert ("valid" if valid(c["move"], schema("move")) else "invalid") == c["expected"]


@pytest.mark.parametrize("name", names("observation_cases"))
def test_each_observation_case_gets_its_published_verdict(name: str) -> None:
    c = case("observation_cases", name)
    verdict = valid(c["observation"], schema("observation"))
    assert ("valid" if verdict else "invalid") == c["expected"]


@pytest.mark.parametrize("kind", ["move_cases", "observation_cases"])
def test_each_payload_has_positive_and_negative_cases(kind: str) -> None:
    assert {c["expected"] for c in vector()[kind]} == {"valid", "invalid"}


def test_the_largest_observation_fits_its_bound() -> None:
    worst = case("observation_cases", "worst-case")["observation"]
    assert len(worst["moves"]) == ACCEPTED_PLIES
    assert len(worst["legal_moves"]) == 218
    text = json.dumps(worst, separators=(",", ":"))
    assert payload_verdict(text, ACCEPTED_BOUNDS["observation"]) == "within_bound"


def test_a_spectator_view_of_each_valid_observation_is_valid() -> None:
    spectator = schema("spectator")
    for c in vector()["observation_cases"]:
        if c["expected"] == "valid":
            view = {
                name: value
                for name, value in c["observation"].items()
                if name in spectator["properties"]
            }
            assert valid(view, spectator), c["name"]
            assert not valid({**view, "legal_moves": []}, spectator), c["name"]


@pytest.mark.parametrize("name", names("payload_size_cases"))
def test_each_payload_size_case_gets_its_published_verdict(name: str) -> None:
    c = case("payload_size_cases", name)
    text = padded(c["value"], c["pad_to_bytes"])
    assert valid(json.loads(text), schema(c["payload"])), (
        "a size case must be a valid payload"
    )
    assert payload_verdict(text, schema(c["payload"])[BOUND_KEY]) == c["expected"]


def test_each_game_bound_is_proven_at_its_edge() -> None:
    edges = {
        (
            c["payload"],
            c["pad_to_bytes"] - schema(c["payload"])[BOUND_KEY],
            c["expected"],
        )
        for c in vector()["payload_size_cases"]
    }
    for payload in ("move", "observation"):
        assert (payload, 0, "within_bound") in edges
        assert (payload, 1, "over_bound") in edges


@pytest.mark.parametrize("name", names("message_size_cases"))
def test_each_message_size_case_gets_its_published_verdict(name: str) -> None:
    c = case("message_size_cases", name)
    (entry,) = [e for e in vector()["message_limits"] if e["message"] == c["message"]]
    assert message_verdict(c["length"], entry, plus()) == (c["expected"], c["code"])


def test_each_message_limit_is_proven_at_its_edge() -> None:
    cases = vector()["message_size_cases"]
    for entry in vector()["message_limits"]:
        limit = message_limit(entry, plus())
        lengths = {c["length"] for c in cases if c["message"] == entry["message"]}
        assert {limit, limit + 1} <= lengths, entry["message"]


# Every rule, broken once.


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            lambda s: s["properties"]["legal_moves"].update({CLASS_KEY: "private"}),
            "carries no data class",
        ),
        (lambda s: s["properties"]["moves"].pop(RETAINED_KEY), "no retained flag"),
        (lambda s: s.update({BOUND_KEY: 65537}), "not within the shared ceiling"),
        (lambda s: s.update({"additionalProperties": True}), "is not a strict object"),
        (
            lambda s: s["properties"]["last_move"].update({"pattern": "^[a-h]"}),
            "is not a keyword this contract uses here",
        ),
    ],
    ids=[
        "unknown class",
        "no retained flag",
        "bound over ceiling",
        "not strict",
        "pattern",
    ],
)
def test_a_broken_observation_schema_is_refused(change: Any, reason: str) -> None:
    broken = copy.deepcopy(schema("observation"))
    change(broken)
    refusals = schema_refusals(broken, "observation", ACCEPTED_CEILINGS)
    assert any(reason in refusal for refusal in refusals), refusals


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda s: s.update({BOUND_KEY: 4097}), "not within the shared ceiling"),
        (
            lambda s: s["properties"]["uci"].update({CLASS_KEY: "public"}),
            "is not a keyword this contract uses here",
        ),
        (lambda s: s.update({"additionalProperties": True}), "is not a strict object"),
    ],
    ids=["bound over ceiling", "annotated move field", "not strict"],
)
def test_a_broken_move_schema_is_refused(change: Any, reason: str) -> None:
    broken = copy.deepcopy(schema("move"))
    change(broken)
    refusals = schema_refusals(broken, "move", ACCEPTED_CEILINGS)
    assert any(reason in refusal for refusal in refusals), refusals


def test_a_move_without_both_members_is_refused() -> None:
    """The draw claim lives inside `move`: no member at all is no action."""
    assert not valid({}, schema("move"))
    loosened = copy.deepcopy(schema("move"))
    loosened.pop("anyOf")
    assert valid({}, loosened)


# The solo game version.


@pytest.mark.parametrize("name", SCHEMAS)
def test_the_solo_game_version_plays_by_chess_1s_payloads(name: str) -> None:
    base = json.loads((GAME / name).read_text(encoding="utf-8"))
    solo = json.loads((SOLO / name).read_text(encoding="utf-8"))
    assert solo["title"] == base["title"].replace("chess-1", "chess-1-solo")
    assert {k: v for k, v in solo.items() if k != "title"} == {
        k: v for k, v in base.items() if k != "title"
    }


def test_the_solo_readme_states_the_seats_and_the_result() -> None:
    text = " ".join((SOLO / "README.md").read_text(encoding="utf-8").split())
    for phrase in (
        "**Not a published contract version.**",
        "A match is solo when its grant ticket names the game version `chess-1-solo`",
        "the agent holds `first`, plays White and moves first",
        "the provider's computer holds `second` under the pseudonym `computer`",
        "exactly one grant ticket",
        "no ticket binds the computer's seat",
        "`solo: true`",
        "No protocol message, schema, signed line or refusal code of `agentnexus-games-v1` changes",
        "`computer_unavailable` and no winner",
        "`D-101`",
    ):
        assert phrase in text, phrase


def test_the_readme_keeps_the_operations_closed() -> None:
    text = " ".join((GAME / "README.md").read_text(encoding="utf-8").split())
    for phrase in (
        "a draw claim travels inside a `move`, so no operation, path or grant permission is added",
        "The seat `first` plays White and moves first",
        "never from the order in which the seats bind",
        "A provider never claims a draw for a seat",
        "Checkmate takes precedence over both",
        "These are provider limits, not rules, and never a result",
    ):
        assert phrase in text, phrase


# Across game versions: neither game's payload passes as the other's (AC-9 of #202).

CONNECT_FOUR = ROOT / "games" / "connect-four" / "connect-four-1"
CONNECT_FOUR_VECTOR = ROOT / "vectors" / "connect-four-1-payloads" / "cases.json"


def connect_four_valid(kind: str) -> list[dict[str, Any]]:
    cases = json.loads(CONNECT_FOUR_VECTOR.read_text(encoding="utf-8"))[kind]
    return [c for c in cases if c["expected"] == "valid"]


def chess_valid(kind: str) -> list[dict[str, Any]]:
    return [c for c in vector()[kind] if c["expected"] == "valid"]


@pytest.mark.parametrize("payload", ["move", "observation"])
def test_no_valid_payload_of_one_game_passes_as_the_others(payload: str) -> None:
    kind, member = f"{payload}_cases", payload
    chess_cases, connect_four_cases = chess_valid(kind), connect_four_valid(kind)
    assert chess_cases and connect_four_cases
    for c in chess_cases:
        assert not valid(c[member], schema(payload, CONNECT_FOUR)), c["name"]
    for c in connect_four_cases:
        assert not valid(c[member], schema(payload)), c["name"]


def test_the_readme_states_the_recognised_dead_positions_and_their_deadline() -> None:
    """OD-34 (b): kings with fixed pawns are recognised; other pieces are not, and stay so."""
    text = " ".join((GAME / "README.md").read_text(encoding="utf-8").split())
    for phrase in (
        (
            "kings with pawns alone when no sequence of legal moves can move a pawn, capture "
            "anything or checkmate"
        ),
        "searching every position the kings can reach, completely",
        "Dead positions with any other piece are not recognised",
        "opponent holds only a king or the position is a recognised dead position",
    ):
        assert phrase in text, phrase
