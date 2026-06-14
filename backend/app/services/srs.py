"""
Spaced-Repetition System (SRS) for L.E.A.D.S. flashcards.

Implements the classic SM-2 schedule. Decks are persisted PER SESSION via the
shared cache layer (Upstash when configured — durable + cross-device for the
same session id; in-memory otherwise). Each card tracks an ease factor (ef),
interval (days), repetition count, and a due date; reviews update the schedule.

GUARDRAILS: no PII; stores only the user's own study cards keyed by their
session id; cache keys namespaced (cache.py adds the "leads:" prefix).
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from . import cache

_TTL = 90 * 86400  # keep decks ~90 days
_RATINGS = {"again": 2, "hard": 3, "good": 4, "easy": 5}


def _today_iso() -> str:
    return date.today().isoformat()


def _deck_key(session: str, name: str) -> str:
    return f"srs::{session}::{name}"


def _index_key(session: str) -> str:
    return f"srs_decks::{session}"


def _cid(front: str) -> str:
    return hashlib.sha1(front.encode("utf-8")).hexdigest()[:12]


def _load_index(session: str) -> List[str]:
    idx = cache.get(_index_key(session))
    return idx if isinstance(idx, list) else []


def save_cards(session: str, cards: List[Dict[str, str]], deck: str = "default") -> Dict[str, Any]:
    """Add flashcards to a session deck (dedup by front). New cards are due today."""
    deck = (deck or "default").strip() or "default"
    key = _deck_key(session, deck)
    existing = cache.get(key)
    if not isinstance(existing, dict) or "cards" not in existing:
        existing = {"name": deck, "cards": []}
    fronts = {c.get("front") for c in existing["cards"]}
    added = 0
    for c in (cards or []):
        front = (c.get("front") or "").strip()
        if not front or front in fronts:
            continue
        fronts.add(front)
        existing["cards"].append(
            {
                "id": _cid(front),
                "front": front,
                "back": (c.get("back") or "").strip(),
                "ef": 2.5,
                "interval": 0,
                "reps": 0,
                "due": _today_iso(),
            }
        )
        added += 1
    cache.set(key, existing, ttl=_TTL)

    idx = _load_index(session)
    if deck not in idx:
        idx.append(deck)
        cache.set(_index_key(session), idx, ttl=_TTL)

    return {"deck": deck, "added": added, "total": len(existing["cards"])}


def list_decks(session: str) -> Dict[str, Any]:
    today = _today_iso()
    out = []
    for name in _load_index(session):
        d = cache.get(_deck_key(session, name))
        if not isinstance(d, dict):
            continue
        cards = d.get("cards", [])
        due = sum(1 for c in cards if c.get("due", today) <= today)
        out.append({"name": name, "total": len(cards), "due": due})
    return {"decks": out}


def due(session: str, deck: str = "default", limit: int = 20) -> Dict[str, Any]:
    deck = (deck or "default").strip() or "default"
    d = cache.get(_deck_key(session, deck))
    cards = d.get("cards", []) if isinstance(d, dict) else []
    today = _today_iso()
    duecards = sorted((c for c in cards if c.get("due", today) <= today), key=lambda c: c.get("due", today))
    limit = max(1, min(int(limit or 20), 100))
    return {
        "deck": deck,
        "due_count": len(duecards),
        "total": len(cards),
        "cards": [{"id": c["id"], "front": c["front"], "back": c["back"]} for c in duecards[:limit]],
    }


def _sm2(card: Dict[str, Any], q: int) -> None:
    """SM-2 update in place."""
    if q < 3:
        card["reps"] = 0
        card["interval"] = 1
    else:
        card["reps"] = int(card.get("reps", 0)) + 1
        if card["reps"] == 1:
            card["interval"] = 1
        elif card["reps"] == 2:
            card["interval"] = 6
        else:
            card["interval"] = max(1, round(float(card.get("interval", 1)) * float(card.get("ef", 2.5))))
    ef = float(card.get("ef", 2.5)) + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    card["ef"] = max(1.3, round(ef, 3))
    card["due"] = (date.today() + timedelta(days=int(card["interval"]))).isoformat()


def review(session: str, deck: str, card_id: str, rating: str) -> Dict[str, Any]:
    """Apply a review rating (again/hard/good/easy) to a card and reschedule it."""
    deck = (deck or "default").strip() or "default"
    q = _RATINGS.get((rating or "").strip().lower())
    if q is None:
        return {"error": "rating must be one of: again, hard, good, easy"}
    key = _deck_key(session, deck)
    d = cache.get(key)
    if not isinstance(d, dict):
        return {"error": "deck not found"}
    for c in d.get("cards", []):
        if c.get("id") == card_id:
            _sm2(c, q)
            cache.set(key, d, ttl=_TTL)
            return {"id": card_id, "due": c["due"], "interval": c["interval"], "ef": c["ef"], "reps": c["reps"]}
    return {"error": "card not found"}
