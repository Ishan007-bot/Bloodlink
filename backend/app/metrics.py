"""Domain metrics for Prometheus.

Stock and request counts are read from the database at scrape time, so every backend
replica reports the same values. Fulfilment time is a histogram observed in-process
when a request becomes FULFILLED.
"""

import logging
from datetime import timedelta

from prometheus_client import REGISTRY, Histogram
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select

log = logging.getLogger(__name__)

FULFILMENT_SECONDS = Histogram(
    "bloodlink_request_fulfilment_seconds",
    "Time from a blood request being raised to being fully allocated.",
    ["priority"],
    buckets=(60, 300, 900, 1800, 3600, 4 * 3600, 12 * 3600, 24 * 3600, 72 * 3600),
)


def observe_fulfilment(priority: str, seconds: float) -> None:
    FULFILMENT_SECONDS.labels(priority=priority).observe(max(seconds, 0.0))


class InventoryCollector:
    """Exposes current stock and request queue from the database on every scrape."""

    def describe(self):
        # Lets the registry learn the metric names without querying the database.
        yield GaugeMetricFamily("bloodlink_units_available", "", labels=["blood_group"])
        yield GaugeMetricFamily("bloodlink_units_expiring_soon", "", labels=["blood_group"])
        yield GaugeMetricFamily("bloodlink_units", "", labels=["status"])
        yield GaugeMetricFamily("bloodlink_requests", "", labels=["status", "priority"])
        yield GaugeMetricFamily("bloodlink_safety_stock_units", "")

    def collect(self):
        # Imported here to avoid a circular import (db -> config only, models -> db).
        from .compatibility import BLOOD_GROUPS
        from .config import settings
        from .db import SessionLocal
        from .models import BloodRequest, BloodUnit, utcnow

        available = GaugeMetricFamily(
            "bloodlink_units_available", "Usable blood units in stock.", labels=["blood_group"]
        )
        expiring = GaugeMetricFamily(
            "bloodlink_units_expiring_soon",
            f"Available units expiring within {settings.expiring_window_days} days.",
            labels=["blood_group"],
        )
        units_total = GaugeMetricFamily(
            "bloodlink_units", "Blood units by status.", labels=["status"]
        )
        requests = GaugeMetricFamily(
            "bloodlink_requests", "Blood requests by status and priority.",
            labels=["status", "priority"],
        )
        safety = GaugeMetricFamily(
            "bloodlink_safety_stock_units", "Configured safety stock per blood group."
        )
        safety.add_metric([], settings.safety_stock)

        try:
            now = utcnow()
            soon = now + timedelta(days=settings.expiring_window_days)
            with SessionLocal() as db:
                stock = dict(
                    db.execute(
                        select(BloodUnit.blood_group, func.count())
                        .where(BloodUnit.status == "AVAILABLE", BloodUnit.expires_at > now)
                        .group_by(BloodUnit.blood_group)
                    ).all()
                )
                soon_stock = dict(
                    db.execute(
                        select(BloodUnit.blood_group, func.count())
                        .where(
                            BloodUnit.status == "AVAILABLE",
                            BloodUnit.expires_at > now,
                            BloodUnit.expires_at <= soon,
                        )
                        .group_by(BloodUnit.blood_group)
                    ).all()
                )
                by_status = db.execute(
                    select(BloodUnit.status, func.count()).group_by(BloodUnit.status)
                ).all()
                req_rows = db.execute(
                    select(BloodRequest.status, BloodRequest.priority, func.count()).group_by(
                        BloodRequest.status, BloodRequest.priority
                    )
                ).all()
        except Exception:  # the database being down must not break /metrics
            log.warning("inventory metrics skipped: database unavailable", exc_info=True)
            yield safety
            return

        for group in BLOOD_GROUPS:
            available.add_metric([group], stock.get(group, 0))
            expiring.add_metric([group], soon_stock.get(group, 0))
        for status, count in by_status:
            units_total.add_metric([status], count)
        for status, priority, count in req_rows:
            requests.add_metric([status, priority], count)
        yield from (available, expiring, units_total, requests, safety)


_registered = False


def register_collectors() -> None:
    global _registered
    if not _registered:
        REGISTRY.register(InventoryCollector())
        _registered = True
