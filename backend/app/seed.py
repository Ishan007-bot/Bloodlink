"""Fill an empty database with a realistic few weeks of blood bank activity.

    python -m app.seed            # only seeds an empty database
    python -m app.seed --force    # adds another batch even if data exists

Donations are spread over the last 60 days (so some units are already expired and some
are about to), and hospital requests over the last 7 days. Requests are fulfilled at
realistic delays after they were raised, so the dashboard and metrics have history.
"""

import argparse
import random
from datetime import timedelta

from sqlalchemy import func, select

from .db import SessionLocal
from .models import BloodRequest, Donor, Hospital, utcnow
from .services import DomainError, fulfil_request, record_donation

# Roughly the Indian donor mix, with rare Rh-negative groups slightly boosted for the demo.
GROUP_WEIGHTS = {"O+": 34, "B+": 30, "A+": 21, "AB+": 7, "O-": 3, "B-": 2.5, "A-": 1.5, "AB-": 1}

HOSPITALS = [
    ("Sassoon General Hospital", "Pune"),
    ("Ruby Hall Clinic", "Pune"),
    ("KEM Hospital", "Mumbai"),
    ("Tata Memorial Hospital", "Mumbai"),
    ("AIIMS Trauma Centre", "Delhi"),
]
FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Ananya", "Vihaan", "Isha", "Arjun", "Sara", "Kunal", "Nisha"]
LAST = ["Sharma", "Patel", "Rao", "Iyer", "Khan", "Singh", "Das", "Menon", "Joshi", "Gupta"]


def seed(force: bool = False, donors: int = 320, requests: int = 40, rng_seed: int = 13) -> str:
    rng = random.Random(rng_seed)
    now = utcnow()
    with SessionLocal() as db:
        if not force and db.scalar(select(func.count(Hospital.id))):
            return "database already has data; use --force to add more"

        hospitals = []
        for name, city in HOSPITALS:
            existing = db.scalar(select(Hospital).where(Hospital.name == name))
            hospitals.append(existing or Hospital(name=name, city=city, contact_phone="020-5550100"))
        db.add_all(hospitals)
        db.commit()

        groups, weights = zip(*GROUP_WEIGHTS.items(), strict=True)
        donated = 0
        for i in range(donors):
            donor = Donor(
                name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                blood_group=rng.choices(groups, weights)[0],
                phone=f"+91 9{rng.randint(100000000, 999999999)}",
                city=rng.choice(HOSPITALS)[1],
            )
            db.add(donor)
            db.commit()
            # About 85% of donors gave blood in the last 60 days.
            if i % 7 != 0:
                collected = now - timedelta(days=rng.uniform(0, 60), hours=rng.uniform(0, 8))
                try:
                    record_donation(db, donor, collected)
                    donated += 1
                except DomainError:
                    pass

        raised = []
        for _ in range(requests):
            created = now - timedelta(days=rng.uniform(0, 7))
            emergency = rng.random() < 0.3
            request = BloodRequest(
                hospital_id=rng.choice(hospitals).id,
                patient_ref=f"PT-{rng.randint(1000, 9999)}",
                blood_group=rng.choices(groups, weights)[0],
                units_needed=rng.randint(1, 2 if emergency else 3),
                priority="EMERGENCY" if emergency else "ROUTINE",
                created_at=created,
            )
            db.add(request)
            raised.append(request)
        db.commit()

        # Work through requests in the order they were raised; emergencies are handled
        # within minutes, routine ones within hours. The newest few are left open.
        raised.sort(key=lambda r: r.created_at)
        for request in raised[:-6]:
            delay = (
                timedelta(minutes=rng.uniform(4, 25))
                if request.priority == "EMERGENCY"
                else timedelta(hours=rng.uniform(1, 18))
            )
            handled_at = min(request.created_at + delay, now)
            fulfil_request(db, request, handled_at)

        return f"seeded {len(hospitals)} hospitals, {donors} donors, {donated} units, {len(raised)} requests"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="seed even if the database is not empty")
    args = parser.parse_args()
    print(seed(force=args.force))


if __name__ == "__main__":
    main()
