"""Business operations that read or change the database."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from . import metrics
from .allocation import Candidate, choose_units, match_type
from .compatibility import BLOOD_GROUPS, donor_groups_for
from .config import settings
from .models import Allocation, BloodRequest, BloodUnit, Donor


class DomainError(Exception):
    """A request that breaks a business rule; the API maps it to 409 Conflict."""


def expire_stale_units(db: Session, now: datetime) -> int:
    """Mark AVAILABLE units past their expiry date as EXPIRED. Returns how many changed."""
    result = db.execute(
        update(BloodUnit)
        .where(BloodUnit.status == "AVAILABLE", BloodUnit.expires_at <= now)
        .values(status="EXPIRED")
    )
    db.commit()
    return result.rowcount or 0


def next_eligible_date(donor: Donor) -> date | None:
    if donor.last_donation_on is None:
        return None
    return donor.last_donation_on + timedelta(days=settings.donation_gap_days)


def record_donation(db: Session, donor: Donor, collected_at: datetime) -> BloodUnit:
    """Store one donated unit, enforcing the minimum gap between donations."""
    eligible_from = next_eligible_date(donor)
    if eligible_from is not None and collected_at.date() < eligible_from:
        raise DomainError(
            f"donor {donor.id} is not eligible to donate until {eligible_from.isoformat()}"
        )
    unit = BloodUnit(
        donor_id=donor.id,
        blood_group=donor.blood_group,
        collected_at=collected_at,
        expires_at=collected_at + timedelta(days=settings.unit_shelf_life_days),
        status="AVAILABLE",
    )
    donor.last_donation_on = collected_at.date()
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


def fulfil_request(db: Session, request: BloodRequest, now: datetime) -> list[Allocation]:
    """Allocate as many compatible units as possible to an open request."""
    if request.status in ("FULFILLED", "CANCELLED"):
        raise DomainError(f"request {request.id} is already {request.status.lower()}")
    expire_stale_units(db, now)

    remaining = request.units_needed - request.units_allocated
    rows = db.execute(
        select(BloodUnit.id, BloodUnit.blood_group, BloodUnit.expires_at).where(
            BloodUnit.status == "AVAILABLE",
            BloodUnit.blood_group.in_(donor_groups_for(request.blood_group)),
        )
    ).all()
    chosen = choose_units(
        [Candidate(r.id, r.blood_group, r.expires_at) for r in rows],
        request.blood_group,
        remaining,
        now,
    )

    made: list[Allocation] = []
    for c in chosen:
        unit = db.get(BloodUnit, c.unit_id)
        unit.status = "ISSUED"
        allocation = Allocation(
            request_id=request.id,
            unit_id=c.unit_id,
            match_type=match_type(c.blood_group, request.blood_group),
            allocated_at=now,
        )
        db.add(allocation)
        made.append(allocation)

    request.units_allocated += len(chosen)
    if request.units_allocated >= request.units_needed:
        request.status = "FULFILLED"
        request.fulfilled_at = now
        metrics.observe_fulfilment(request.priority, (now - request.created_at).total_seconds())
    elif request.units_allocated > 0:
        request.status = "PARTIAL"
    db.commit()
    for a in made:
        db.refresh(a)
    return made


def open_requests_in_queue_order(db: Session) -> list[BloodRequest]:
    """Open requests, emergencies first, then oldest first."""
    emergency_first = case((BloodRequest.priority == "EMERGENCY", 0), else_=1)
    return list(
        db.scalars(
            select(BloodRequest)
            .where(BloodRequest.status.in_(("PENDING", "PARTIAL")))
            .order_by(emergency_first, BloodRequest.created_at, BloodRequest.id)
        )
    )


def process_queue(db: Session, now: datetime) -> list[BloodRequest]:
    """Try to fulfil every open request in queue order. Returns the requests touched."""
    touched = []
    for request in open_requests_in_queue_order(db):
        if fulfil_request(db, request, now):
            touched.append(request)
    return touched


def stock_level(available: int) -> str:
    if available < settings.safety_stock / 2:
        return "CRITICAL"
    if available < settings.safety_stock:
        return "LOW"
    return "OK"


@dataclass
class GroupStock:
    blood_group: str
    available: int
    expiring_soon: int
    level: str


def inventory(db: Session, now: datetime) -> list[GroupStock]:
    """Available and soon-to-expire units for every blood group."""
    expire_stale_units(db, now)
    soon = now + timedelta(days=settings.expiring_window_days)
    rows = db.execute(
        select(
            BloodUnit.blood_group,
            func.count(BloodUnit.id),
            func.sum(case((BloodUnit.expires_at <= soon, 1), else_=0)),
        )
        .where(BloodUnit.status == "AVAILABLE")
        .group_by(BloodUnit.blood_group)
    ).all()
    found = {group: (int(count), int(expiring or 0)) for group, count, expiring in rows}
    result = []
    for group in BLOOD_GROUPS:
        available, expiring = found.get(group, (0, 0))
        result.append(GroupStock(group, available, expiring, stock_level(available)))
    return result


def stats(db: Session, now: datetime) -> dict:
    """Headline numbers for the dashboard."""
    expire_stale_units(db, now)
    units_by_status = dict(
        db.execute(select(BloodUnit.status, func.count()).group_by(BloodUnit.status)).all()
    )
    requests_by_status = dict(
        db.execute(select(BloodRequest.status, func.count()).group_by(BloodRequest.status)).all()
    )
    fulfilled = requests_by_status.get("FULFILLED", 0)
    considered = sum(requests_by_status.values()) - requests_by_status.get("CANCELLED", 0)

    issued = units_by_status.get("ISSUED", 0)
    expired = units_by_status.get("EXPIRED", 0)

    emergency_fills = db.execute(
        select(BloodRequest.created_at, BloodRequest.fulfilled_at).where(
            BloodRequest.priority == "EMERGENCY", BloodRequest.status == "FULFILLED"
        )
    ).all()
    minutes = [(f - c).total_seconds() / 60 for c, f in emergency_fills if f is not None]

    return {
        "donors": db.scalar(select(func.count(Donor.id))) or 0,
        "units_available": units_by_status.get("AVAILABLE", 0),
        "units_issued": issued,
        "units_expired": expired,
        "requests_open": requests_by_status.get("PENDING", 0) + requests_by_status.get("PARTIAL", 0),
        "requests_fulfilled": fulfilled,
        "fill_rate": round(fulfilled / considered, 4) if considered else 0.0,
        "wastage_rate": round(expired / (issued + expired), 4) if (issued + expired) else 0.0,
        "avg_emergency_fill_minutes": round(sum(minutes) / len(minutes), 1) if minutes else None,
    }
