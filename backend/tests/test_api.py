from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.main import app
from app.models import Donor
from app.security import hash_password


def register(client, email="donor@example.com"):
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": "Test Donor",
            "password": "Secure-password-123",
            "phone": "555-0101",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_admin(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    admin = Donor(
        email="admin@example.com",
        full_name="Test Admin",
        password_hash=hash_password("Secure-admin-123"),
        is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    donor_id = admin.id
    db.close()
    generator.close()
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "Secure-admin-123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, donor_id


def test_registration_login_and_donor_data_are_scoped(client):
    first = register(client)
    second = register(client, "other@example.com")
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}

    profile = client.get("/api/donors/me", headers=first_headers)
    assert profile.status_code == 200
    assert profile.json()["email"] == "donor@example.com"

    created = client.post(
        "/api/donations",
        headers=first_headers,
        json={"amount": "40.00", "cause": "Education"},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"

    other_list = client.get(
        f"/api/donations?donor_id={second['donor']['id']}", headers=first_headers
    )
    assert other_list.status_code == 200
    assert len(other_list.json()) == 1
    assert other_list.json()[0]["donor_id"] == first["donor"]["id"]

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "donor@example.com", "password": "incorrect-password"},
    )
    assert wrong_password.status_code == 401


def test_donor_admin_crud_and_search(client):
    register(client)
    admin_headers, _ = create_admin(client)
    listing = client.get("/api/donors?q=donor", headers=admin_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    donor_id = listing.json()[0]["id"]

    changed = client.patch(
        f"/api/donors/{donor_id}",
        headers=admin_headers,
        json={"full_name": "Updated Donor"},
    )
    assert changed.status_code == 200
    assert changed.json()["full_name"] == "Updated Donor"

    deleted = client.delete(f"/api/donors/{donor_id}", headers=admin_headers)
    assert deleted.status_code == 204
    login = client.post(
        "/api/auth/login",
        json={"email": "donor@example.com", "password": "Secure-password-123"},
    )
    assert login.status_code == 401


def test_material_donation_approval_schedule_receipt(client):
    donor = register(client)
    donor_headers = {"Authorization": f"Bearer {donor['access_token']}"}
    admin_headers, _ = create_admin(client)
    created = client.post(
        "/api/material-donations",
        headers=donor_headers,
        json={
            "item_name": "Winter blankets",
            "description": "Clean, folded blankets",
            "quantity": 4,
            "unit": "pieces",
            "pickup_method": "dropoff",
            "address": "12 Hope Street, City",
        },
    )
    assert created.status_code == 201
    material_id = created.json()["id"]

    forbidden = client.post(
        f"/api/admin/material-donations/{material_id}/decision",
        headers=donor_headers,
        json={"status": "approved"},
    )
    assert forbidden.status_code == 403

    approved = client.post(
        f"/api/admin/material-donations/{material_id}/decision",
        headers=admin_headers,
        json={"status": "approved", "admin_note": "Drop-off approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    scheduled = client.post(
        f"/api/admin/material-donations/{material_id}/schedule",
        headers=admin_headers,
        json={"scheduled_for": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["status"] == "scheduled"

    received = client.post(
        f"/api/admin/material-donations/{material_id}/receive",
        headers=admin_headers,
        json={"confirmation_note": "Items received in good condition"},
    )
    assert received.status_code == 200
    assert received.json()["status"] == "received"

    receipts = client.get("/api/receipts", headers=donor_headers)
    assert receipts.status_code == 200
    assert len(receipts.json()) == 1
    document = client.get(
        f"/api/receipts/{receipts.json()[0]['id']}/document", headers=donor_headers
    )
    assert document.status_code == 200
    assert "Winter blankets" in document.text


def test_donor_cannot_change_material_status(client):
    donor = register(client)
    headers = {"Authorization": f"Bearer {donor['access_token']}"}
    created = client.post(
        "/api/material-donations",
        headers=headers,
        json={
            "item_name": "Rice",
            "quantity": 3,
            "unit": "kg",
            "pickup_method": "pickup",
            "address": "5 Main Road, City",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending_approval"


def test_admin_can_create_donor_and_dashboard_stats_are_empty(client):
    admin_headers, _ = create_admin(client)
    created = client.post(
        "/api/donors",
        headers=admin_headers,
        json={
            "email": "created@example.com",
            "full_name": "Created Donor",
            "password": "Created-password-123",
        },
    )
    assert created.status_code == 201
    assert created.json()["email"] == "created@example.com"
    stats = client.get("/api/dashboard/stats", headers=admin_headers)
    assert stats.status_code == 200
    assert stats.json()["verified_monetary_total"] == "0.00"
    assert stats.json()["monetary_donation_count"] == 0
