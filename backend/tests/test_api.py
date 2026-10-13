from datetime import timedelta

from app.models import utcnow

# ---------------------------------------------------------------- meta


def test_health_does_not_need_the_database(client):
    assert client.get("/health").json() == {"status": "UP"}


def test_ready_checks_the_database(client):
    assert client.get("/ready").json() == {"status": "READY"}


def test_root_describes_the_service(client):
    body = client.get("/").json()
    assert body["service"] == "BloodLink API"
    assert body["docs"] == "/docs"


def test_metrics_expose_http_and_inventory_metrics(client, stock):
    stock("O-", count=2)
    client.get("/api/inventory")
    body = client.get("/metrics").text
    assert "http_requests_total" in body
    assert 'bloodlink_units_available{blood_group="O-"} 2.0' in body
    assert 'bloodlink_units_available{blood_group="AB+"} 0.0' in body
    assert "bloodlink_safety_stock_units 10.0" in body


def test_compatibility_table(client):
    table = {row["blood_group"]: row for row in client.get("/api/compatibility").json()}
    assert len(table) == 8
    assert table["O-"]["can_receive_from"] == ["O-"]
    assert len(table["O-"]["can_donate_to"]) == 8
    assert table["AB+"]["can_donate_to"] == ["AB+"]


# ---------------------------------------------------------------- donors


def test_donor_crud(client):
    created = client.post(
        "/api/donors", json={"name": "Asha Rao", "blood_group": "B+", "phone": "+91 98765 43210", "city": "Pune"}
    )
    assert created.status_code == 201
    donor = created.json()
    assert donor["next_eligible_on"] is None

    assert client.get(f"/api/donors/{donor['id']}").json()["name"] == "Asha Rao"

    updated = client.put(f"/api/donors/{donor['id']}", json={"city": "Mumbai"})
    assert updated.json()["city"] == "Mumbai"
    assert updated.json()["blood_group"] == "B+"

    assert client.delete(f"/api/donors/{donor['id']}").status_code == 204
    assert client.get(f"/api/donors/{donor['id']}").status_code == 404


def test_donor_validation(client):
    assert client.post("/api/donors", json={"name": "Ravi", "blood_group": "C+"}).status_code == 422
    assert client.post("/api/donors", json={"name": "R", "blood_group": "A+"}).status_code == 422
    assert client.post("/api/donors", json={"name": "Ravi", "blood_group": "A+", "phone": "call me"}).status_code == 422
    future = (utcnow() + timedelta(days=3)).date().isoformat()
    response = client.post("/api/donors", json={"name": "Ravi", "blood_group": "A+", "last_donation_on": future})
    assert response.status_code == 422


def test_donor_filters(client):
    recent = (utcnow() - timedelta(days=10)).date().isoformat()
    client.post("/api/donors", json={"name": "Recent Donor", "blood_group": "A+", "last_donation_on": recent})
    client.post("/api/donors", json={"name": "Ready Donor", "blood_group": "A+"})
    client.post("/api/donors", json={"name": "Other Group", "blood_group": "O-"})

    assert [d["name"] for d in client.get("/api/donors", params={"blood_group": "A+"}).json()] == [
        "Ready Donor",
        "Recent Donor",
    ]
    eligible = client.get("/api/donors", params={"eligible": "true"}).json()
    assert {d["name"] for d in eligible} == {"Ready Donor", "Other Group"}
    resting = client.get("/api/donors", params={"eligible": "false"}).json()
    assert [d["name"] for d in resting] == ["Recent Donor"]


def test_unknown_donor_is_404(client):
    assert client.get("/api/donors/999").status_code == 404
    assert client.put("/api/donors/999", json={"city": "X"}).status_code == 404


# ---------------------------------------------------------------- donations


def test_donation_creates_a_unit_that_expires_after_42_days(client):
    donor = client.post("/api/donors", json={"name": "Meera", "blood_group": "O-"}).json()
    unit = client.post("/api/donations", json={"donor_id": donor["id"]})
    assert unit.status_code == 201
    body = unit.json()
    assert body["status"] == "AVAILABLE"
    assert body["blood_group"] == "O-"
    from datetime import datetime

    shelf = datetime.fromisoformat(body["expires_at"]) - datetime.fromisoformat(body["collected_at"])
    assert shelf == timedelta(days=42)
    assert client.get(f"/api/donors/{donor['id']}").json()["next_eligible_on"] is not None


def test_donor_must_wait_90_days_between_donations(client):
    donor = client.post("/api/donors", json={"name": "Kabir", "blood_group": "A-"}).json()
    first = (utcnow() - timedelta(days=30)).isoformat()
    assert client.post("/api/donations", json={"donor_id": donor["id"], "collected_at": first}).status_code == 201
    second = client.post("/api/donations", json={"donor_id": donor["id"]})
    assert second.status_code == 409
    assert "not eligible" in second.json()["detail"]


def test_donation_after_the_gap_is_accepted(client):
    donor = client.post("/api/donors", json={"name": "Kabir", "blood_group": "A-"}).json()
    long_ago = (utcnow() - timedelta(days=95)).isoformat()
    client.post("/api/donations", json={"donor_id": donor["id"], "collected_at": long_ago})
    assert client.post("/api/donations", json={"donor_id": donor["id"]}).status_code == 201


def test_donation_cannot_be_in_the_future_or_from_unknown_donor(client):
    donor = client.post("/api/donors", json={"name": "Zoya", "blood_group": "B-"}).json()
    future = (utcnow() + timedelta(days=1)).isoformat()
    assert client.post("/api/donations", json={"donor_id": donor["id"], "collected_at": future}).status_code == 422
    assert client.post("/api/donations", json={"donor_id": 999}).status_code == 404


def test_deleting_a_donor_keeps_the_donated_units(client, stock):
    [unit_id] = stock("AB-")
    units = client.get("/api/units").json()
    donor_id = units[0]["donor_id"]
    assert client.delete(f"/api/donors/{donor_id}").status_code == 204
    unit = client.get("/api/units").json()[0]
    assert unit["id"] == unit_id
    assert unit["donor_id"] is None
    assert unit["status"] == "AVAILABLE"


def test_units_past_shelf_life_become_expired(client, stock):
    stock("B+", days_old=50)
    stock("B+", days_old=2)
    statuses = sorted(u["status"] for u in client.get("/api/units", params={"blood_group": "B+"}).json())
    assert statuses == ["AVAILABLE", "EXPIRED"]
    assert len(client.get("/api/units", params={"status": "EXPIRED"}).json()) == 1


# ---------------------------------------------------------------- hospitals


def test_hospital_crud(client):
    created = client.post("/api/hospitals", json={"name": "Sassoon Hospital", "city": "Pune"})
    assert created.status_code == 201
    hospital_id = created.json()["id"]
    assert client.get(f"/api/hospitals/{hospital_id}").json()["city"] == "Pune"
    assert (
        client.put(f"/api/hospitals/{hospital_id}", json={"contact_phone": "020-1234"}).json()["contact_phone"]
        == "020-1234"
    )
    assert [h["name"] for h in client.get("/api/hospitals").json()] == ["Sassoon Hospital"]
    assert client.delete(f"/api/hospitals/{hospital_id}").status_code == 204
    assert client.get(f"/api/hospitals/{hospital_id}").status_code == 404


def test_hospital_names_are_unique(client):
    client.post("/api/hospitals", json={"name": "Ruby Hall", "city": "Pune"})
    assert client.post("/api/hospitals", json={"name": "Ruby Hall", "city": "Mumbai"}).status_code == 409


def test_hospital_with_requests_cannot_be_deleted(client, hospital, make_request):
    make_request("A+", 1)
    assert client.delete(f"/api/hospitals/{hospital['id']}").status_code == 409


# ---------------------------------------------------------------- requests and allocation


def test_request_needs_an_existing_hospital(client):
    response = client.post("/api/requests", json={"hospital_id": 42, "blood_group": "A+", "units_needed": 1})
    assert response.status_code == 404


def test_request_validation(client, hospital):
    base = {"hospital_id": hospital["id"], "blood_group": "A+"}
    assert client.post("/api/requests", json={**base, "units_needed": 0}).status_code == 422
    assert client.post("/api/requests", json={**base, "units_needed": 21}).status_code == 422
    assert client.post("/api/requests", json={**base, "units_needed": 1, "priority": "ASAP"}).status_code == 422


def test_fulfil_with_exact_group(client, stock, make_request):
    stock("A+", count=3)
    request = make_request("A+", 2)
    result = client.post(f"/api/requests/{request['id']}/fulfil").json()
    assert result["request"]["status"] == "FULFILLED"
    assert result["request"]["units_allocated"] == 2
    assert result["request"]["fulfilled_at"] is not None
    assert {a["match_type"] for a in result["newly_allocated"]} == {"EXACT"}
    assert [s["available"] for s in client.get("/api/inventory").json() if s["blood_group"] == "A+"] == [1]


def test_fulfil_uses_oldest_units_first(client, stock, make_request):
    [fresh] = stock("O+", days_old=1)
    [old] = stock("O+", days_old=30)
    request = make_request("O+", 1)
    allocated = client.post(f"/api/requests/{request['id']}/fulfil").json()["newly_allocated"]
    assert [a["unit_id"] for a in allocated] == [old]
    assert fresh != old


def test_fulfil_falls_back_to_compatible_groups(client, stock, make_request):
    stock("A+")
    stock("O-")
    stock("A-")
    request = make_request("A+", 3)
    allocated = client.post(f"/api/requests/{request['id']}/fulfil").json()["newly_allocated"]
    assert [a["blood_group"] for a in allocated] == ["A+", "A-", "O-"]
    assert [a["match_type"] for a in allocated] == ["EXACT", "SUBSTITUTE", "SUBSTITUTE"]


def test_partial_fulfilment_then_completion(client, stock, make_request):
    stock("B-")
    request = make_request("B-", 2)
    first = client.post(f"/api/requests/{request['id']}/fulfil").json()["request"]
    assert (first["status"], first["units_allocated"]) == ("PARTIAL", 1)

    stock("B-")
    second = client.post(f"/api/requests/{request['id']}/fulfil").json()["request"]
    assert (second["status"], second["units_allocated"]) == ("FULFILLED", 2)
    assert len(second["allocations"]) == 2


def test_no_compatible_stock_leaves_request_pending(client, stock, make_request):
    stock("A+", count=3)
    request = make_request("O-", 1)
    result = client.post(f"/api/requests/{request['id']}/fulfil").json()
    assert result["newly_allocated"] == []
    assert result["request"]["status"] == "PENDING"


def test_expired_units_are_not_allocated(client, stock, make_request):
    stock("AB+", days_old=45)
    request = make_request("AB+", 1)
    assert client.post(f"/api/requests/{request['id']}/fulfil").json()["request"]["status"] == "PENDING"


def test_closed_requests_cannot_be_fulfilled_or_changed(client, stock, make_request):
    stock("O+")
    done = make_request("O+", 1)
    client.post(f"/api/requests/{done['id']}/fulfil")
    assert client.post(f"/api/requests/{done['id']}/fulfil").status_code == 409
    assert client.put(f"/api/requests/{done['id']}", json={"units_needed": 3}).status_code == 409

    cancelled = make_request("O+", 1)
    assert client.put(f"/api/requests/{cancelled['id']}", json={"status": "CANCELLED"}).json()["status"] == "CANCELLED"
    assert client.post(f"/api/requests/{cancelled['id']}/fulfil").status_code == 409


def test_update_request(client, stock, make_request):
    stock("A-")
    request = make_request("A-", 3)
    client.post(f"/api/requests/{request['id']}/fulfil")
    updated = client.put(f"/api/requests/{request['id']}", json={"priority": "EMERGENCY", "patient_ref": "ICU-7"})
    assert (updated.json()["priority"], updated.json()["patient_ref"]) == ("EMERGENCY", "ICU-7")
    # One unit is already issued, so the request cannot shrink below 1.
    assert client.put(f"/api/requests/{request['id']}", json={"units_needed": 1}).status_code == 200
    assert client.put(f"/api/requests/{request['id']}", json={"status": "FULFILLED"}).status_code == 422


def test_delete_request_rules(client, stock, make_request):
    pending = make_request("B+", 1)
    assert client.delete(f"/api/requests/{pending['id']}").status_code == 204
    assert client.get(f"/api/requests/{pending['id']}").status_code == 404

    stock("B+")
    issued = make_request("B+", 1)
    client.post(f"/api/requests/{issued['id']}/fulfil")
    assert client.delete(f"/api/requests/{issued['id']}").status_code == 409


def test_queue_serves_emergencies_first(client, stock, make_request):
    routine = make_request("O+", 1)
    emergency = make_request("O+", 1, priority="EMERGENCY")
    stock("O+")  # only one unit for two requests
    touched = client.post("/api/requests/process-queue").json()
    assert [r["id"] for r in touched] == [emergency["id"]]
    assert client.get(f"/api/requests/{routine['id']}").json()["status"] == "PENDING"


def test_list_requests_filters(client, stock, make_request):
    stock("A+")
    first = make_request("A+", 1)
    make_request("A+", 1, priority="EMERGENCY")
    client.post(f"/api/requests/{first['id']}/fulfil")
    assert len(client.get("/api/requests").json()) == 2
    assert [r["id"] for r in client.get("/api/requests", params={"status": "FULFILLED"}).json()] == [first["id"]]
    assert len(client.get("/api/requests", params={"priority": "EMERGENCY"}).json()) == 1


# ---------------------------------------------------------------- reporting


def test_inventory_levels_and_expiring_soon(client, stock):
    stock("O-", days_old=38, count=2)  # 4 days left: expiring soon
    stock("O-", days_old=1, count=3)
    stock("A+", days_old=1, count=12)
    inventory = {row["blood_group"]: row for row in client.get("/api/inventory").json()}
    assert len(inventory) == 8
    assert (inventory["O-"]["available"], inventory["O-"]["expiring_soon"], inventory["O-"]["level"]) == (
        5,
        2,
        "LOW",
    )
    assert inventory["A+"]["level"] == "OK"
    assert inventory["B-"]["level"] == "CRITICAL"


def test_stats(client, stock, make_request):
    stock("O+", count=2)
    stock("O+", days_old=60)  # wasted
    emergency = make_request("O+", 2, priority="EMERGENCY")
    make_request("O+", 1)
    client.post(f"/api/requests/{emergency['id']}/fulfil")
    stats = client.get("/api/stats").json()
    assert stats["donors"] == 3
    assert (stats["units_available"], stats["units_issued"], stats["units_expired"]) == (0, 2, 1)
    assert (stats["requests_open"], stats["requests_fulfilled"]) == (1, 1)
    assert stats["fill_rate"] == 0.5
    assert stats["wastage_rate"] == round(1 / 3, 4)
    assert stats["avg_emergency_fill_minutes"] is not None


# ---------------------------------------------------------------- seed data


def test_seed_generates_consistent_history(client):
    from app.seed import seed

    assert seed().startswith("seeded 5 hospitals")
    assert seed() == "database already has data; use --force to add more"
    stats = client.get("/api/stats").json()
    assert stats["units_expired"] > 0  # some donations are older than 42 days
    assert stats["requests_fulfilled"] > 0
    assert stats["requests_open"] >= 1
    assert 0 < stats["fill_rate"] <= 1
    for request in client.get("/api/requests", params={"status": "FULFILLED"}).json():
        assert request["units_allocated"] == request["units_needed"]
        for allocation in request["allocations"]:
            assert (
                allocation["blood_group"]
                in {row["blood_group"]: row for row in client.get("/api/compatibility").json()}[request["blood_group"]][
                    "can_receive_from"
                ]
            )
