"""Choosing which blood units fill a request.

Pure functions only: no database access, and `now` is always passed in, so the
rules can be unit-tested directly.
"""

from dataclasses import dataclass
from datetime import datetime

from .compatibility import donor_groups_for


@dataclass(frozen=True)
class Candidate:
    unit_id: int
    blood_group: str
    expires_at: datetime


def choose_units(
    candidates: list[Candidate], recipient_group: str, needed: int, now: datetime
) -> list[Candidate]:
    """Pick up to `needed` units for a recipient.

    Rules, in order:
    1. Only compatible groups (see compatibility.py); expired units are never used.
    2. Preferred groups first: exact match, then substitutes, O- last.
    3. Within a group, first-expiring-first-out (FEFO), so the oldest usable
       units are used before they go to waste. Ties break on unit id.
    """
    if needed <= 0:
        return []
    preference = {group: rank for rank, group in enumerate(donor_groups_for(recipient_group))}
    usable = [c for c in candidates if c.blood_group in preference and c.expires_at > now]
    usable.sort(key=lambda c: (preference[c.blood_group], c.expires_at, c.unit_id))
    return usable[:needed]


def match_type(unit_group: str, recipient_group: str) -> str:
    return "EXACT" if unit_group == recipient_group else "SUBSTITUTE"
