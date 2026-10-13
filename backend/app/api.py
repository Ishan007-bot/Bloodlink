from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import services
from .compatibility import BLOOD_GROUPS, donor_groups_for, recipients_for
from .db import get_db
from .models import Allocation, BloodRequest, BloodUnit, Donor, Hospital, utcnow
from .schemas import (
    AllocationOut,
    BloodGroup,
    CompatibilityOut,
    DonationCreate,
    DonorCreate,
    DonorOut,
    DonorUpdate,
    FulfilmentOut,
    GroupStockOut,
    HospitalCreate,
    HospitalOut,
    HospitalUpdate,
    Priority,
    RequestCreate,
    RequestOut,
    RequestStatus,
    RequestUpdate,
    StatsOut,
    UnitOut,
    UnitStatus,
)

router = APIRouter(prefix="/api")
DB = Depends(get_db)


def _get_or_404(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} {obj_id} not found")
    return obj


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def _donor_out(donor: Donor) -> DonorOut:
    out = DonorOut.model_validate(donor)
    out.next_eligible_on = services.next_eligible_date(donor)
    return out


def _allocation_out(a: Allocation) -> AllocationOut:
    return AllocationOut(
        unit_id=a.unit_id,
        blood_group=a.unit.blood_group,
        expires_at=a.unit.expires_at,
        match_type=a.match_type,
    )


def _request_out(r: BloodRequest) -> RequestOut:
    return RequestOut(
        id=r.id,
        hospital_id=r.hospital_id,
        hospital_name=r.hospital.name,
        patient_ref=r.patient_ref,
        blood_group=r.blood_group,
        units_needed=r.units_needed,
        units_allocated=r.units_allocated,
        priority=r.priority,
        status=r.status,
        created_at=r.created_at,
        fulfilled_at=r.fulfilled_at,
        allocations=[_allocation_out(a) for a in r.allocations],
    )


# ---------------------------------------------------------------- compatibility
@router.get("/compatibility", response_model=list[CompatibilityOut], tags=["reference"])
def compatibility_table():
    """Who can receive from whom, for all eight blood groups."""
    return [
        CompatibilityOut(
            blood_group=g, can_receive_from=list(donor_groups_for(g)), can_donate_to=list(recipients_for(g))
        )
        for g in BLOOD_GROUPS
    ]


# ---------------------------------------------------------------- donors
@router.get("/donors", response_model=list[DonorOut], tags=["donors"])
def list_donors(
    blood_group: BloodGroup | None = None,
    eligible: bool | None = Query(default=None, description="Only donors who can donate today"),
    db: Session = DB,
):
    query = select(Donor).order_by(Donor.name)
    if blood_group:
        query = query.where(Donor.blood_group == blood_group)
    donors = [_donor_out(d) for d in db.scalars(query)]
    if eligible is not None:
        today = utcnow().date()
        donors = [
            d for d in donors if (d.next_eligible_on is None or d.next_eligible_on <= today) == eligible
        ]
    return donors


@router.post("/donors", response_model=DonorOut, status_code=status.HTTP_201_CREATED, tags=["donors"])
def create_donor(payload: DonorCreate, db: Session = DB):
    if payload.last_donation_on and payload.last_donation_on > utcnow().date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "last_donation_on cannot be in the future")
    donor = Donor(**payload.model_dump())
    db.add(donor)
    db.commit()
    db.refresh(donor)
    return _donor_out(donor)


@router.get("/donors/{donor_id}", response_model=DonorOut, tags=["donors"])
def get_donor(donor_id: int, db: Session = DB):
    return _donor_out(_get_or_404(db, Donor, donor_id, "donor"))


@router.put("/donors/{donor_id}", response_model=DonorOut, tags=["donors"])
def update_donor(donor_id: int, payload: DonorUpdate, db: Session = DB):
    donor = _get_or_404(db, Donor, donor_id, "donor")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(donor, key, value)
    db.commit()
    db.refresh(donor)
    return _donor_out(donor)


@router.delete("/donors/{donor_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["donors"])
def delete_donor(donor_id: int, db: Session = DB):
    donor = _get_or_404(db, Donor, donor_id, "donor")
    # Donated units stay in stock; they just lose the link to the donor record.
    db.execute(update(BloodUnit).where(BloodUnit.donor_id == donor_id).values(donor_id=None))
    db.delete(donor)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- donations / units
@router.post("/donations", response_model=UnitOut, status_code=status.HTTP_201_CREATED, tags=["units"])
def create_donation(payload: DonationCreate, db: Session = DB):
    """Record a donation: creates one AVAILABLE unit that expires after the shelf life."""
    donor = _get_or_404(db, Donor, payload.donor_id, "donor")
    now = utcnow()
    collected_at = payload.collected_at.replace(tzinfo=None) if payload.collected_at else now
    if collected_at > now + timedelta(minutes=5):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "collected_at cannot be in the future")
    try:
        return services.record_donation(db, donor, collected_at)
    except services.DomainError as exc:
        raise _conflict(str(exc)) from None


@router.get("/units", response_model=list[UnitOut], tags=["units"])
def list_units(
    blood_group: BloodGroup | None = None,
    status_: UnitStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = DB,
):
    services.expire_stale_units(db, utcnow())
    query = select(BloodUnit).order_by(BloodUnit.expires_at).limit(limit)
    if blood_group:
        query = query.where(BloodUnit.blood_group == blood_group)
    if status_:
        query = query.where(BloodUnit.status == status_)
    return list(db.scalars(query))


# ---------------------------------------------------------------- hospitals
@router.get("/hospitals", response_model=list[HospitalOut], tags=["hospitals"])
def list_hospitals(db: Session = DB):
    return list(db.scalars(select(Hospital).order_by(Hospital.name)))


@router.post("/hospitals", response_model=HospitalOut, status_code=status.HTTP_201_CREATED, tags=["hospitals"])
def create_hospital(payload: HospitalCreate, db: Session = DB):
    hospital = Hospital(**payload.model_dump())
    db.add(hospital)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict(f"hospital {payload.name!r} already exists") from None
    db.refresh(hospital)
    return hospital


@router.get("/hospitals/{hospital_id}", response_model=HospitalOut, tags=["hospitals"])
def get_hospital(hospital_id: int, db: Session = DB):
    return _get_or_404(db, Hospital, hospital_id, "hospital")


@router.put("/hospitals/{hospital_id}", response_model=HospitalOut, tags=["hospitals"])
def update_hospital(hospital_id: int, payload: HospitalUpdate, db: Session = DB):
    hospital = _get_or_404(db, Hospital, hospital_id, "hospital")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(hospital, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict("another hospital already has that name") from None
    db.refresh(hospital)
    return hospital


@router.delete("/hospitals/{hospital_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["hospitals"])
def delete_hospital(hospital_id: int, db: Session = DB):
    hospital = _get_or_404(db, Hospital, hospital_id, "hospital")
    if hospital.requests:
        raise _conflict("hospital has blood requests on record and cannot be deleted")
    db.delete(hospital)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- requests
@router.get("/requests", response_model=list[RequestOut], tags=["requests"])
def list_requests(
    status_: RequestStatus | None = Query(default=None, alias="status"),
    priority: Priority | None = None,
    db: Session = DB,
):
    query = select(BloodRequest).order_by(BloodRequest.created_at.desc(), BloodRequest.id.desc())
    if status_:
        query = query.where(BloodRequest.status == status_)
    if priority:
        query = query.where(BloodRequest.priority == priority)
    return [_request_out(r) for r in db.scalars(query)]


@router.post("/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED, tags=["requests"])
def create_request(payload: RequestCreate, db: Session = DB):
    _get_or_404(db, Hospital, payload.hospital_id, "hospital")
    request = BloodRequest(**payload.model_dump(), created_at=utcnow())
    db.add(request)
    db.commit()
    db.refresh(request)
    return _request_out(request)


@router.get("/requests/{request_id}", response_model=RequestOut, tags=["requests"])
def get_request(request_id: int, db: Session = DB):
    return _request_out(_get_or_404(db, BloodRequest, request_id, "request"))


@router.put("/requests/{request_id}", response_model=RequestOut, tags=["requests"])
def update_request(request_id: int, payload: RequestUpdate, db: Session = DB):
    request = _get_or_404(db, BloodRequest, request_id, "request")
    if request.status in ("FULFILLED", "CANCELLED"):
        raise _conflict(f"request {request_id} is {request.status.lower()} and can no longer change")
    changes = payload.model_dump(exclude_unset=True)
    if "units_needed" in changes and changes["units_needed"] < request.units_allocated:
        raise _conflict(f"{request.units_allocated} units are already allocated")
    for key, value in changes.items():
        setattr(request, key, value)
    db.commit()
    db.refresh(request)
    return _request_out(request)


@router.delete("/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["requests"])
def delete_request(request_id: int, db: Session = DB):
    request = _get_or_404(db, BloodRequest, request_id, "request")
    if request.units_allocated > 0:
        raise _conflict("units have been issued for this request; cancel it instead")
    db.delete(request)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/requests/{request_id}/fulfil", response_model=FulfilmentOut, tags=["requests"])
def fulfil(request_id: int, db: Session = DB):
    """Allocate compatible units: exact group first, O- last, first-expiring-first-out."""
    request = _get_or_404(db, BloodRequest, request_id, "request")
    try:
        made = services.fulfil_request(db, request, utcnow())
    except services.DomainError as exc:
        raise _conflict(str(exc)) from None
    db.refresh(request)
    return FulfilmentOut(request=_request_out(request), newly_allocated=[_allocation_out(a) for a in made])


@router.post("/requests/process-queue", response_model=list[RequestOut], tags=["requests"])
def process_queue(db: Session = DB):
    """Try every open request, emergencies first, then oldest first."""
    return [_request_out(r) for r in services.process_queue(db, utcnow())]


# ---------------------------------------------------------------- reporting
@router.get("/inventory", response_model=list[GroupStockOut], tags=["reporting"])
def get_inventory(db: Session = DB):
    return [GroupStockOut(**vars(s)) for s in services.inventory(db, utcnow())]


@router.get("/stats", response_model=StatsOut, tags=["reporting"])
def get_stats(db: Session = DB):
    return services.stats(db, utcnow())
