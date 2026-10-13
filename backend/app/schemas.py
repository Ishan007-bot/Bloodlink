from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BloodGroup = Literal["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"]
Priority = Literal["ROUTINE", "EMERGENCY"]
RequestStatus = Literal["PENDING", "PARTIAL", "FULFILLED", "CANCELLED"]
UnitStatus = Literal["AVAILABLE", "ISSUED", "EXPIRED"]

PHONE_PATTERN = r"^[0-9+\- ]*$"


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Donors
class DonorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    blood_group: BloodGroup
    phone: str = Field(default="", max_length=20, pattern=PHONE_PATTERN)
    city: str = Field(default="", max_length=80)
    last_donation_on: date | None = None


class DonorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=20, pattern=PHONE_PATTERN)
    city: str | None = Field(default=None, max_length=80)


class DonorOut(ORM):
    id: int
    name: str
    blood_group: BloodGroup
    phone: str
    city: str
    last_donation_on: date | None
    next_eligible_on: date | None = None
    created_at: datetime


# Hospitals
class HospitalCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    city: str = Field(min_length=2, max_length=80)
    contact_phone: str = Field(default="", max_length=20, pattern=PHONE_PATTERN)


class HospitalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    city: str | None = Field(default=None, min_length=2, max_length=80)
    contact_phone: str | None = Field(default=None, max_length=20, pattern=PHONE_PATTERN)


class HospitalOut(ORM):
    id: int
    name: str
    city: str
    contact_phone: str
    created_at: datetime


# Units and donations
class DonationCreate(BaseModel):
    donor_id: int
    collected_at: datetime | None = Field(
        default=None, description="Defaults to now (UTC). Cannot be in the future."
    )


class UnitOut(ORM):
    id: int
    donor_id: int | None
    blood_group: BloodGroup
    collected_at: datetime
    expires_at: datetime
    status: UnitStatus


# Requests
class RequestCreate(BaseModel):
    hospital_id: int
    blood_group: BloodGroup
    units_needed: int = Field(ge=1, le=20)
    priority: Priority = "ROUTINE"
    patient_ref: str = Field(default="", max_length=60)


class RequestUpdate(BaseModel):
    units_needed: int | None = Field(default=None, ge=1, le=20)
    priority: Priority | None = None
    patient_ref: str | None = Field(default=None, max_length=60)
    status: Literal["CANCELLED"] | None = Field(
        default=None, description="Only cancelling is allowed; other states come from fulfilment."
    )


class AllocationOut(ORM):
    unit_id: int
    blood_group: BloodGroup
    expires_at: datetime
    match_type: Literal["EXACT", "SUBSTITUTE"]


class RequestOut(ORM):
    id: int
    hospital_id: int
    hospital_name: str
    patient_ref: str
    blood_group: BloodGroup
    units_needed: int
    units_allocated: int
    priority: Priority
    status: RequestStatus
    created_at: datetime
    fulfilled_at: datetime | None
    allocations: list[AllocationOut] = []


class FulfilmentOut(BaseModel):
    request: RequestOut
    newly_allocated: list[AllocationOut]


# Reporting
class GroupStockOut(BaseModel):
    blood_group: BloodGroup
    available: int
    expiring_soon: int
    level: Literal["OK", "LOW", "CRITICAL"]


class CompatibilityOut(BaseModel):
    blood_group: BloodGroup
    can_receive_from: list[BloodGroup]
    can_donate_to: list[BloodGroup]


class StatsOut(BaseModel):
    donors: int
    units_available: int
    units_issued: int
    units_expired: int
    requests_open: int
    requests_fulfilled: int
    fill_rate: float
    wastage_rate: float
    avg_emergency_fill_minutes: float | None
