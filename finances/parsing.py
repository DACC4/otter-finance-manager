"""Parse untrusted request input once, at the boundary, into trusted values."""

import json
from collections.abc import Iterable

BULK_TAG_ACTIONS = ("add", "remove", "set")


class InvalidPayload(ValueError):
    """Client sent a request body we cannot accept; the message is safe to return."""


def _id_list(value, field: str) -> list[int]:
    # bool is a subclass of int; reject it so `true` is never read as id 1.
    if not isinstance(value, list) or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in value
    ):
        raise InvalidPayload(f"{field} must be a list of integer ids.")
    return value


def parse_bulk_tags_payload(raw: bytes) -> tuple[str, list[int], list[int]]:
    """Return (action, item_ids, tag_ids) or raise InvalidPayload."""
    try:
        body = json.loads(raw)
    except ValueError:
        raise InvalidPayload("Invalid JSON.") from None
    if not isinstance(body, dict):
        raise InvalidPayload("Body must be a JSON object.")
    action = body.get("action")
    if action not in BULK_TAG_ACTIONS:
        raise InvalidPayload("Invalid action.")
    return (
        action,
        _id_list(body.get("item_ids", []), "item_ids"),
        _id_list(body.get("tag_ids", []), "tag_ids"),
    )


def parse_owned_tag_id(raw: str | None, owned_ids: Iterable[int]) -> int | None:
    """Return the tag id from a query string only if it names one of the user's tags."""
    if not raw or not raw.isdigit():
        return None
    tag_id = int(raw)
    return tag_id if tag_id in set(owned_ids) else None
