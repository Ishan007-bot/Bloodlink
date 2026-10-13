from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    """Naive UTC timestamp; every datetime column in the schema is stored as UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


class Donor(Base):
    __tablename__ = "donors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    blood_group: Mapped[str] = mapped_column(String(3), index=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    last_donation_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    units: Mapped[list["BloodUnit"]] = relationship(back_populates="donor")


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    city: Mapped[str] = mapped_column(String(80))
    contact_phone: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    requests: Mapped[list["BloodRequest"]] = relationship(back_populates="hospital")


class BloodUnit(Base):
    __tablename__ = "blood_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donor_id: Mapped[int | None] = mapped_column(ForeignKey("donors.id", ondelete="SET NULL"), nullable=True)
    blood_group: Mapped[str] = mapped_column(String(3), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # AVAILABLE -> ISSUED (allocated to a request) or EXPIRED (past expires_at).
    status: Mapped[str] = mapped_column(String(12), default="AVAILABLE", index=True)

    donor: Mapped[Donor | None] = relationship(back_populates="units")


class BloodRequest(Base):
    __tablename__ = "blood_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id", ondelete="CASCADE"))
    patient_ref: Mapped[str] = mapped_column(String(60), default="")
    blood_group: Mapped[str] = mapped_column(String(3))
    units_needed: Mapped[int] = mapped_column(Integer)
    units_allocated: Mapped[int] = mapped_column(Integer, default=0)
    # ROUTINE or EMERGENCY.
    priority: Mapped[str] = mapped_column(String(10), default="ROUTINE")
    # PENDING -> PARTIAL -> FULFILLED, or CANCELLED.
    status: Mapped[str] = mapped_column(String(10), default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    hospital: Mapped[Hospital] = relationship(back_populates="requests")
    allocations: Mapped[list["Allocation"]] = relationship(back_populates="request", cascade="all, delete-orphan")


class Allocation(Base):
    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("blood_requests.id", ondelete="CASCADE"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("blood_units.id"), unique=True)
    # EXACT when the unit's group equals the request's group, SUBSTITUTE otherwise.
    match_type: Mapped[str] = mapped_column(String(10))
    allocated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    request: Mapped[BloodRequest] = relationship(back_populates="allocations")
    unit: Mapped[BloodUnit] = relationship()
