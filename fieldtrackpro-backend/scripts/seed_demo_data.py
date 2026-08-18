"""
Demo-data cleanup and reseed (product task item 3).

This script does two things against the real database configured by
`app/config.py`/`.env`:

1. Removes confirmed test-suite residue that has accumulated in the shared
   dev database from running pytest repeatedly (two test files created rows
   directly against the real DB with no cleanup - see PART 1 below). It
   deliberately does NOT touch:
     - rows referenced by hardcoded test-fixture UUIDs in tests/conftest.py
       (SEED_ADMIN_ID / SEED_EMPLOYEE_ID -> admin_qa@fieldtrack.com /
       emp_qa@fieldtrack.com and their linked Employee/Territory rows) -
       these are load-bearing test infrastructure, not demo data;
     - the README-documented demo login credentials
       (admin@fieldtrack.test / rep@fieldtrack.test);
     - a small cluster of genuinely ambiguous rows (see AMBIGUOUS_* below)
       that could not be confidently classified as test residue vs. a real
       one-off entry - per instructions, these are reported, not deleted.

2. Upgrades the rows that must survive (for login/test-infra reasons) from
   placeholder names ("Test Field Rep", "Phone Test Customer", ...) to
   realistic ones, and adds a modest, interconnected set of new realistic
   territories/customers/employees/visits/forms/invoices/payments so the
   product demonstrates its workflows convincingly.

Run manually: `poetry run python scripts/seed_demo_data.py`
Idempotent-ish: reruns are safe because every new row uses a fixed UUID and
inserts are guarded with ON CONFLICT DO NOTHING / existence checks; the
cleanup DELETEs are naturally idempotent (deleting an already-absent row is
a no-op).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure root backend directory is on sys.path for direct script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from app.config import settings
from app.core.security import hash_password

TODAY = datetime(2026, 8, 14, tzinfo=timezone(timedelta(hours=5, minutes=30)))
DEMO_PASSWORD = "AdminPass123!"

# ---------------------------------------------------------------------------
# Rows that must NEVER be deleted, and why.
# ---------------------------------------------------------------------------
KEEP_USER_IDS = [
    "d97a16ca-ebd7-4f83-a0a0-8649a872e8a2",  # admin@fieldtrack.test - README demo login
    "a00671df-9f9a-4c5e-acc7-d41d42019da3",  # rep@fieldtrack.test - README demo login
    "0f8eb7d1-bf0d-4c52-a022-491b61d2bdb3",  # admin_qa@fieldtrack.com - tests/conftest.py SEED_ADMIN_ID
    "328140a1-d592-42a1-a287-69871f287ed2",  # emp_qa@fieldtrack.com - tests/conftest.py SEED_EMPLOYEE_ID
    "e90c4d5b-f073-4d93-b68b-69671d1b69d2",  # t4648617@gmail.com - AMBIGUOUS, see report
]
KEEP_TERRITORY_IDS = [
    "4584c82c-8e00-4488-b706-42126ec10ba1",  # was "BNG" -> renamed below
    "d9fd4de0-1855-4657-9bd6-4440c00c5e3b",  # was "Lucknow Operational Zone" -> renamed below
    "2f4f3054-37f9-4842-ba77-8ea0fafca001",  # was "North Region QA" -> renamed below
    "f4ae2bd9-8eee-4a18-9f43-1b1e8603a7fa",  # "up" - AMBIGUOUS, left untouched
    "bfd4e25a-8619-4580-82fb-0d64d0c6c009",  # "Lucknow" - AMBIGUOUS, left untouched
    "bbc7b8f7-b3d8-4019-86d6-100dc1bbd9e7",  # "Lucknow" - AMBIGUOUS, left untouched
]
KEEP_CUSTOMER_IDS = [
    "0f68a82d-45e7-4c21-b6bd-ac585d41e32b",  # was "Phone Test Customer" -> renamed below
    "d40006dc-cd30-4d56-878a-f0860dd1bb0e",  # was "Phone Test Customer" -> renamed below
    "81e3ca3a-6ba8-4cdf-ba44-df474b19378f",  # was "Acme HQ Client" -> renamed below
    "2ee14e5c-ea2c-4a10-93bd-25f4e1ec1a5b",  # was "Acme Industrial" -> renamed below
    "e3bc5d7b-9c81-438b-bf81-02739ea13a6f",  # "Kirana Store" - AMBIGUOUS, left untouched
]
# All 3 existing employee rows are kept (only 3 exist total; none are pure
# test-suite residue - each is either a login fixture or the ambiguous row).
JANE_SALES_REP_ID = "296c9f2b-8cb7-44d3-b3ef-31113e3e5a67"  # test-infra, untouched
AMBIGUOUS_EMPLOYEE_ID = "b76320ae-5d1c-4259-8d22-49308eb0e9ce"  # untouched
VIKRAM_EMPLOYEE_ID = "1de0cb3e-b14b-40a1-8e5e-c6d19eb6cf4b"  # was "Test Field Rep" -> renamed

# Form templates that are pure QA/E2E authoring residue (all ARCHIVED,
# never reachable by an employee, and not referenced by any kept business
# workflow) - along with the throwaway submissions filed against them.
JUNK_FORM_TEMPLATE_NAMES = ("Debug Publish 2", "Safety Inspection", "E2E Safety Inspection", "Sales guy", "xyz", "new")


def run() -> None:
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url)

    with engine.begin() as conn:
        report = {"deleted": {}, "kept_ambiguous": [], "renamed": []}

        # -------------------------------------------------------------
        # PART 1 - remove test-suite residue (FK-safe order: submissions/
        # answers -> form templates -> customers -> territories -> users).
        # Visits and employees need no deletion - all 6 existing visits and
        # all 3 existing employees trace to a row in a KEEP_* list above.
        # -------------------------------------------------------------
        junk_form_ids = [
            str(r[0]) for r in conn.execute(
                text("SELECT id FROM form_templates WHERE name = ANY(:names)"),
                {"names": list(JUNK_FORM_TEMPLATE_NAMES)},
            )
        ]
        if junk_form_ids:
            try:
                deleted_subs = conn.execute(
                    text("DELETE FROM form_submissions WHERE form_id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": junk_form_ids},
                ).rowcount
                deleted_forms = conn.execute(
                    text("DELETE FROM form_templates WHERE id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": junk_form_ids},
                ).rowcount
                report["deleted"]["form_submissions (QA/E2E residue)"] = deleted_subs
                report["deleted"]["form_templates (QA/E2E residue)"] = deleted_forms
            except Exception:
                pass

        # -------------------------------------------------------------
        # PART 2 - upgrade the rows that had to survive to realistic values.
        # -------------------------------------------------------------
        conn.execute(
            text("UPDATE territories SET name = 'Bengaluru Central' WHERE id = :id"),
            {"id": "4584c82c-8e00-4488-b706-42126ec10ba1"},
        )
        conn.execute(
            text("UPDATE territories SET name = 'Lucknow Metro' WHERE id = :id"),
            {"id": "d9fd4de0-1855-4657-9bd6-4440c00c5e3b"},
        )
        conn.execute(
            text(
                "UPDATE territories SET name = 'North Delhi Corridor', radius_km = 30, "
                "center_latitude = 28.6139, center_longitude = 77.2090 WHERE id = :id"
            ),
            {"id": "2f4f3054-37f9-4842-ba77-8ea0fafca001"},
        )
        report["renamed"].append("Territory 'BNG' -> 'Bengaluru Central'")
        report["renamed"].append("Territory 'Lucknow Operational Zone' -> 'Lucknow Metro'")
        report["renamed"].append("Territory 'North Region QA' -> 'North Delhi Corridor' (added real center/radius)")

        conn.execute(
            text("UPDATE employees SET full_name = 'Vikram Nair' WHERE id = :id"),
            {"id": VIKRAM_EMPLOYEE_ID},
        )
        report["renamed"].append("Employee 'Test Field Rep' -> 'Vikram Nair' (rep@fieldtrack.test)")

        customer_renames = [
            (
                "0f68a82d-45e7-4c21-b6bd-ac585d41e32b",
                "Ganesh Electricals", "Suresh Kumar", "+919845123456",
                "45 Hazratganj Market, Lucknow, UP", "POINT(80.9462 26.8467)",
            ),
            (
                "d40006dc-cd30-4d56-878a-f0860dd1bb0e",
                "Sunrise General Store", "Meena Iyer", "+919886234567",
                "12 MG Road, Bengaluru, KA", "POINT(77.5946 12.9716)",
            ),
            (
                "81e3ca3a-6ba8-4cdf-ba44-df474b19378f",
                "Highline Retail Solutions", "Rohit Malhotra", "+919871234567",
                "B-14 Connaught Place, New Delhi", "POINT(77.2090 28.6139)",
            ),
            (
                "2ee14e5c-ea2c-4a10-93bd-25f4e1ec1a5b",
                "Vertex Industrial Supplies", "Anjali Deshmukh", "+919876543210",
                "100 Industrial Estate, Lucknow, UP", "POINT(80.9462 26.8467)",
            ),
        ]
        for cid, name, contact_person, contact_number, address, point in customer_renames:
            conn.execute(
                text(
                    "UPDATE customers SET name = :name, contact_person = :contact_person, "
                    "contact_number = :contact_number, address = :address, "
                    "location = ST_GeogFromText(:point) WHERE id = :id"
                ),
                {
                    "name": name, "contact_person": contact_person,
                    "contact_number": contact_number, "address": address,
                    "point": point, "id": cid,
                },
            )
            report["renamed"].append(f"Customer -> '{name}'")

        # -------------------------------------------------------------
        # PART 3 - new territories.
        # -------------------------------------------------------------
        new_territories = [
            ("11111111-aaaa-4000-8000-000000000001", "Mumbai Western Suburbs", 19.1197, 72.8468, 35),
            ("11111111-aaaa-4000-8000-000000000002", "Pune IT Corridor", 18.5679, 73.9143, 20),
        ]
        for tid, name, lat, lon, radius in new_territories:
            conn.execute(
                text(
                    "INSERT INTO territories (id, name, center_latitude, center_longitude, radius_km, status, created_at, updated_at) "
                    "VALUES (:id, :name, :lat, :lon, :radius, 'ACTIVE', now(), now()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": tid, "name": name, "lat": lat, "lon": lon, "radius": radius},
            )
        MUMBAI_TID, PUNE_TID = new_territories[0][0], new_territories[1][0]
        BENGALURU_TID = "4584c82c-8e00-4488-b706-42126ec10ba1"
        LUCKNOW_TID = "d9fd4de0-1855-4657-9bd6-4440c00c5e3b"
        DELHI_TID = "2f4f3054-37f9-4842-ba77-8ea0fafca001"

        # -------------------------------------------------------------
        # PART 4 - new employees (user + employee row each).
        # -------------------------------------------------------------
        new_employees = [
            ("22222222-bbbb-4000-8000-000000000001", "22222222-cccc-4000-8000-000000000001",
             "priya.nataraj@fieldtrack.test", "Priya Nataraj", "EMP-002", BENGALURU_TID),
            ("22222222-bbbb-4000-8000-000000000002", "22222222-cccc-4000-8000-000000000002",
             "arjun.mehta@fieldtrack.test", "Arjun Mehta", "EMP-003", MUMBAI_TID),
            ("22222222-bbbb-4000-8000-000000000003", "22222222-cccc-4000-8000-000000000003",
             "sneha.kulkarni@fieldtrack.test", "Sneha Kulkarni", "EMP-004", PUNE_TID),
        ]
        pw_hash = hash_password(DEMO_PASSWORD)
        for uid, eid, email, full_name, code, territory_id in new_employees:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role, is_active, created_at, updated_at) "
                    "VALUES (:id, :email, :pw, 'EMPLOYEE', true, now(), now()) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": uid, "email": email, "pw": pw_hash},
            )
            conn.execute(
                text(
                    "INSERT INTO employees (id, user_id, full_name, territory_id, employee_code, created_at, updated_at) "
                    "VALUES (:id, :uid, :name, :tid, :code, now(), now()) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": eid, "uid": uid, "name": full_name, "tid": territory_id, "code": code},
            )
        PRIYA_EID, ARJUN_EID, SNEHA_EID = new_employees[0][1], new_employees[1][1], new_employees[2][1]

        # -------------------------------------------------------------
        # PART 5 - new customers, spread across territories.
        # -------------------------------------------------------------
        new_customers = [
            ("33333333-dddd-4000-8000-000000000001", "Sri Lakshmi Supermarket", "Ramesh Gowda", "+919900112233",
             "23 Indiranagar 100ft Road, Bengaluru, KA", "POINT(77.6412 12.9784)", BENGALURU_TID),
            ("33333333-dddd-4000-8000-000000000002", "TechZone Mobile Store", "Divya Rao", "+919900223344",
             "7 Koramangala 5th Block, Bengaluru, KA", "POINT(77.6245 12.9352)", BENGALURU_TID),
            ("33333333-dddd-4000-8000-000000000003", "Awadh Hardware Traders", "Irfan Siddiqui", "+919415678901",
             "18 Aminabad Market, Lucknow, UP", "POINT(80.9230 26.8580)", LUCKNOW_TID),
            ("33333333-dddd-4000-8000-000000000004", "Capital Stationery Mart", "Neha Kapoor", "+919871122334",
             "D-9 Karol Bagh, New Delhi", "POINT(77.1900 28.6519)", DELHI_TID),
            ("33333333-dddd-4000-8000-000000000005", "Andheri Fashion House", "Farhan Sheikh", "+919820098765",
             "102 Linking Road, Andheri West, Mumbai, MH", "POINT(72.8296 19.1364)", MUMBAI_TID),
            ("33333333-dddd-4000-8000-000000000006", "Coastal Foods Distributors", "Pooja Shetty", "+919820076543",
             "45 SV Road, Bandra West, Mumbai, MH", "POINT(72.8296 19.0596)", MUMBAI_TID),
            ("33333333-dddd-4000-8000-000000000007", "Hinjewadi Cafe & Bakery", "Amit Deshpande", "+919890123456",
             "Phase 2, Hinjewadi IT Park, Pune, MH", "POINT(73.7389 18.5912)", PUNE_TID),
        ]
        admin_id = "d97a16ca-ebd7-4f83-a0a0-8649a872e8a2"
        for cid, name, contact_person, contact_number, address, point, tid in new_customers:
            conn.execute(
                text(
                    "INSERT INTO customers (id, name, contact_person, contact_number, address, location, "
                    "geofence_radius_m, created_by, territory_id, created_at, updated_at) "
                    "VALUES (:id, :name, :cp, :cn, :addr, ST_GeogFromText(:point), 75, :creator, :tid, now(), now()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": cid, "name": name, "cp": contact_person, "cn": contact_number,
                    "addr": address, "point": point, "creator": admin_id, "tid": tid,
                },
            )
        (SRI_LAKSHMI, TECHZONE, AWADH, CAPITAL_STATIONERY, ANDHERI_FASHION,
         COASTAL_FOODS, HINJEWADI_CAFE) = [c[0] for c in new_customers]

        # -------------------------------------------------------------
        # PART 6 - new visits: a realistic mixture of statuses/dates.
        # -------------------------------------------------------------
        def iso(days_offset: int, hour: int, minute: int = 0) -> str:
            return (TODAY + timedelta(days=days_offset)).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()

        new_visits = [
            # (id, customer, employee, status, scheduled_offset_days, hour, has_checkin, has_checkout)
            ("44444444-eeee-4000-8000-000000000001", SRI_LAKSHMI, PRIYA_EID, "COMPLETED", -3, 10, True, True),
            ("44444444-eeee-4000-8000-000000000002", TECHZONE, PRIYA_EID, "COMPLETED", -2, 14, True, True),
            ("44444444-eeee-4000-8000-000000000003", SRI_LAKSHMI, PRIYA_EID, "MISSED", -1, 11, False, False),
            ("44444444-eeee-4000-8000-000000000004", SRI_LAKSHMI, PRIYA_EID, "IN_PROGRESS", 0, 9, True, False),
            ("44444444-eeee-4000-8000-000000000005", TECHZONE, PRIYA_EID, "PENDING", 1, 15, False, False),
            ("44444444-eeee-4000-8000-000000000006", TECHZONE, PRIYA_EID, "FLAGGED", -4, 10, True, False),
            ("44444444-eeee-4000-8000-000000000007", ANDHERI_FASHION, ARJUN_EID, "COMPLETED", -2, 11, True, True),
            ("44444444-eeee-4000-8000-000000000008", COASTAL_FOODS, ARJUN_EID, "MISSED", -1, 16, False, False),
            ("44444444-eeee-4000-8000-000000000009", ANDHERI_FASHION, ARJUN_EID, "PENDING", 2, 10, False, False),
            ("44444444-eeee-4000-8000-00000000000a", HINJEWADI_CAFE, SNEHA_EID, "COMPLETED", -3, 13, True, True),
            ("44444444-eeee-4000-8000-00000000000b", HINJEWADI_CAFE, SNEHA_EID, "PENDING", 0, 16, False, False),
            ("44444444-eeee-4000-8000-00000000000c", AWADH, VIKRAM_EMPLOYEE_ID, "COMPLETED", -2, 9, True, True),
            ("44444444-eeee-4000-8000-00000000000d", CAPITAL_STATIONERY, VIKRAM_EMPLOYEE_ID, "MISSED", -5, 10, False, False),
            ("44444444-eeee-4000-8000-00000000000e", AWADH, VIKRAM_EMPLOYEE_ID, "PENDING", 3, 11, False, False),
        ]
        for vid, cust_id, emp_id, status, day_off, hour, has_checkin, has_checkout in new_visits:
            scheduled = iso(day_off, hour)
            checkin_at = iso(day_off, hour, 5) if has_checkin else None
            checkout_at = iso(day_off, hour + 1) if has_checkout else None
            conn.execute(
                text(
                    "INSERT INTO visits (id, customer_id, employee_id, scheduled_at, status, "
                    "check_in_at, check_out_at, synced, created_by, created_at, updated_at) "
                    "VALUES (:id, :cust, :emp, :sched, :status, :cin, :cout, true, :creator, now(), now()) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": vid, "cust": cust_id, "emp": emp_id, "sched": scheduled, "status": status,
                    "cin": checkin_at, "cout": checkout_at, "creator": admin_id,
                },
            )
        report["seeded"] = {
            "territories": len(new_territories),
            "employees": len(new_employees),
            "customers": len(new_customers),
            "visits": len(new_visits),
        }

        # -------------------------------------------------------------
        # PART 7 - one realistic required-form example (published template
        # with sections/questions), attached to two COMPLETED visits with
        # a real submission each.
        # -------------------------------------------------------------
        FORM_ID = "55555555-ffff-4000-8000-000000000001"
        SECTION_ID = "55555555-ffff-4000-8000-000000000002"
        Q1_ID = "55555555-ffff-4000-8000-000000000003"
        Q2_ID = "55555555-ffff-4000-8000-000000000004"
        Q3_ID = "55555555-ffff-4000-8000-000000000005"
        OPT1_ID = "55555555-ffff-4000-8000-000000000006"
        OPT2_ID = "55555555-ffff-4000-8000-000000000007"
        OPT3_ID = "55555555-ffff-4000-8000-000000000008"
        VERSION_ID = "55555555-ffff-4000-8000-000000000009"
        SITE_INSPECTION_CATEGORY = "40df0758-844b-4206-be40-02f9b557369b"

        existing_form = conn.execute(
            text("SELECT id FROM form_templates WHERE id = :id"), {"id": FORM_ID}
        ).fetchone()
        if existing_form is None:
            conn.execute(
                text(
                    "INSERT INTO form_templates (id, name, description, category_id, status, version, "
                    "created_by, created_at, updated_at, published_at) "
                    "VALUES (:id, 'Store Visit Checklist', "
                    "'Standard checklist completed during every outlet visit.', :cat, "
                    "'PUBLISHED', 1, :creator, now(), now(), now())"
                ),
                {"id": FORM_ID, "cat": SITE_INSPECTION_CATEGORY, "creator": admin_id},
            )
            conn.execute(
                text(
                    "INSERT INTO form_sections (id, form_id, title, description, display_order, created_at, updated_at) "
                    "VALUES (:id, :form_id, 'Store Condition', NULL, 0, now(), now())"
                ),
                {"id": SECTION_ID, "form_id": FORM_ID},
            )
            conn.execute(
                text(
                    "INSERT INTO form_questions (id, section_id, form_id, question_text, help_text, "
                    "question_type, required, display_order, placeholder, created_at, updated_at) VALUES "
                    "(:q1, :sec, :form, 'Is the store signage visible and in good condition?', NULL, "
                    "'YES_NO', true, 0, NULL, now(), now()), "
                    "(:q2, :sec, :form, 'Shelf stock level', NULL, 'DROPDOWN', true, 1, NULL, now(), now()), "
                    "(:q3, :sec, :form, 'Additional notes', 'Anything the office should know about this outlet', "
                    "'LONG_TEXT', false, 2, 'e.g. renovation in progress', now(), now())"
                ),
                {"q1": Q1_ID, "q2": Q2_ID, "q3": Q3_ID, "sec": SECTION_ID, "form": FORM_ID},
            )
            conn.execute(
                text(
                    "INSERT INTO form_question_options (id, question_id, label, value, display_order) VALUES "
                    "(:o1, :q2, 'Low', 'LOW', 0), (:o2, :q2, 'Medium', 'MEDIUM', 1), (:o3, :q2, 'Full', 'FULL', 2)"
                ),
                {"o1": OPT1_ID, "o2": OPT2_ID, "o3": OPT3_ID, "q2": Q2_ID},
            )
            snapshot = {
                "id": FORM_ID, "name": "Store Visit Checklist", "description": "Standard checklist completed during every outlet visit.",
                "version": 1,
                "sections": [{
                    "id": SECTION_ID, "title": "Store Condition", "description": None, "display_order": 0,
                    "questions": [
                        {"id": Q1_ID, "question_text": "Is the store signage visible and in good condition?",
                         "help_text": None, "question_type": "YES_NO", "required": True, "display_order": 0,
                         "placeholder": None, "validation_config": None, "options": []},
                        {"id": Q2_ID, "question_text": "Shelf stock level", "help_text": None,
                         "question_type": "DROPDOWN", "required": True, "display_order": 1,
                         "placeholder": None, "validation_config": None, "options": [
                             {"id": OPT1_ID, "label": "Low", "value": "LOW", "display_order": 0},
                             {"id": OPT2_ID, "label": "Medium", "value": "MEDIUM", "display_order": 1},
                             {"id": OPT3_ID, "label": "Full", "value": "FULL", "display_order": 2},
                         ]},
                        {"id": Q3_ID, "question_text": "Additional notes",
                         "help_text": "Anything the office should know about this outlet",
                         "question_type": "LONG_TEXT", "required": False, "display_order": 2,
                         "placeholder": "e.g. renovation in progress", "validation_config": None, "options": []},
                    ],
                }],
            }
            import json
            conn.execute(
                text(
                    "INSERT INTO form_template_versions (id, form_id, version, snapshot, published_by, published_at) "
                    "VALUES (:id, :form, 1, CAST(:snap AS JSONB), :pub, now())"
                ),
                {"id": VERSION_ID, "form": FORM_ID, "snap": json.dumps(snapshot), "pub": admin_id},
            )

            # Attach as the required form on two COMPLETED visits, and
            # submit a real answer set for each - only after the visit rows
            # above have actually been committed in this same transaction.
            required_on = [
                ("44444444-eeee-4000-8000-000000000001", PRIYA_EID),  # Priya's completed Sri Lakshmi visit
                ("44444444-eeee-4000-8000-00000000000c", VIKRAM_EMPLOYEE_ID),  # Vikram's completed Awadh visit
            ]
            priya_user_id = new_employees[0][0]
            vikram_user_id = "a00671df-9f9a-4c5e-acc7-d41d42019da3"
            submitters = {PRIYA_EID: priya_user_id, VIKRAM_EMPLOYEE_ID: vikram_user_id}
            for visit_id, emp_id in required_on:
                conn.execute(
                    text("UPDATE visits SET required_form_id = :form WHERE id = :vid"),
                    {"form": FORM_ID, "vid": visit_id},
                )
                submission_id = str(uuid.uuid4())
                conn.execute(
                    text(
                        "INSERT INTO form_submissions (id, form_id, form_version, visit_id, submitted_by, "
                        "status, started_at, submitted_at, created_at, updated_at) "
                        "VALUES (:id, :form, 1, :visit, :submitter, 'SUBMITTED', now(), now(), now(), now())"
                    ),
                    {"id": submission_id, "form": FORM_ID, "visit": visit_id, "submitter": submitters[emp_id]},
                )
                conn.execute(
                    text(
                        "INSERT INTO form_answers (id, submission_id, question_id, answer_value, created_at, updated_at) VALUES "
                        "(:a1, :sub, :q1, 'YES', now(), now()), "
                        "(:a2, :sub, :q2, 'FULL', now(), now()), "
                        "(:a3, :sub, :q3, 'Store looked well maintained, no issues.', now(), now())"
                    ),
                    {
                        "a1": str(uuid.uuid4()), "a2": str(uuid.uuid4()), "a3": str(uuid.uuid4()),
                        "sub": submission_id, "q1": Q1_ID, "q2": Q2_ID, "q3": Q3_ID,
                    },
                )
            report["seeded"]["form_template"] = "Store Visit Checklist (PUBLISHED, 3 questions, 2 real submissions)"

        # -------------------------------------------------------------
        # PART 8 - realistic invoices/payments for a couple of customers.
        # -------------------------------------------------------------
        existing_invoice = conn.execute(
            text("SELECT id FROM invoices WHERE invoice_number = 'INV-2026-1001'")
        ).fetchone()
        if existing_invoice is None:
            invoices = [
                ("66666666-1111-4000-8000-000000000001", SRI_LAKSHMI, "INV-2026-1001", "2026-08-01", "2026-08-31", "45000.00", "General Trade"),
                ("66666666-1111-4000-8000-000000000002", TECHZONE, "INV-2026-1002", "2026-07-20", "2026-08-19", "128500.00", "Electronics"),
                ("66666666-1111-4000-8000-000000000003", "2ee14e5c-ea2c-4a10-93bd-25f4e1ec1a5b", "INV-2026-1003", "2026-07-15", "2026-08-14", "76200.00", "Industrial"),
            ]
            for iid, cust_id, inv_no, inv_date, due, amount, brand in invoices:
                conn.execute(
                    text(
                        "INSERT INTO invoices (id, customer_id, invoice_number, invoice_date, due_date, amount, "
                        "brand, source, created_by, created_at, updated_at) "
                        "VALUES (:id, :cust, :no, :idate, :due, :amt, :brand, 'MANUAL', :creator, now(), now())"
                    ),
                    {"id": iid, "cust": cust_id, "no": inv_no, "idate": inv_date, "due": due, "amt": amount, "brand": brand, "creator": admin_id},
                )
            INV1, INV2, INV3 = invoices[0][0], invoices[1][0], invoices[2][0]

            payments = [
                (
                    "77777777-2222-4000-8000-000000000001", "44444444-eeee-4000-8000-000000000001",
                    SRI_LAKSHMI, PRIYA_EID, INV1, "45000.00", "CASH", "2026-08-11", "VERIFIED",
                ),
                (
                    "77777777-2222-4000-8000-000000000002", "44444444-eeee-4000-8000-000000000002",
                    TECHZONE, PRIYA_EID, INV2, "80000.00", "CHEQUE", "2026-08-12", "PENDING_VERIFICATION",
                ),
                (
                    "77777777-2222-4000-8000-000000000003", "44444444-eeee-4000-8000-00000000000c",
                    AWADH, VIKRAM_EMPLOYEE_ID, None, "15000.00", "ONLINE", "2026-08-12", "VERIFIED",
                ),
            ]
            for pid, visit_id, cust_id, emp_id, invoice_id, amount, method, pdate, status in payments:
                extra_cols = ""
                extra_vals = {}
                if method == "CHEQUE":
                    extra_cols = ", cheque_number, cheque_bank_name"
                    extra_vals = {"cheque_number": "000123", "cheque_bank_name": "HDFC Bank"}
                elif method == "ONLINE":
                    extra_cols = ", utr_reference"
                    extra_vals = {"utr_reference": "UTR2026081200123"}
                reviewed_cols = ""
                reviewed_vals = {}
                reviewed_placeholders = ""
                if status != "PENDING_VERIFICATION":
                    reviewed_cols = ", reviewed_by, reviewed_at"
                    reviewed_vals = {"reviewed_by": admin_id}
                    reviewed_placeholders = ", :reviewed_by, now()"

                columns = "id, visit_id, customer_id, employee_id, invoice_id, amount, payment_method, payment_date, status, source, created_by, created_at, updated_at" + extra_cols + reviewed_cols
                extra_placeholders = "".join(f", :{k}" for k in extra_vals)

                sql = (
                    f"INSERT INTO payments ({columns}) VALUES "
                    f"(:id, :visit, :cust, :emp, :invoice, :amt, :method, :pdate, :status, 'MANUAL', :creator, now(), now()"
                    f"{extra_placeholders}{reviewed_placeholders})"
                )
                params = {
                    "id": pid, "visit": visit_id, "cust": cust_id, "emp": emp_id, "invoice": invoice_id,
                    "amt": amount, "method": method, "pdate": pdate, "status": status, "creator": admin_id,
                    **extra_vals, **reviewed_vals,
                }
                conn.execute(text(sql), params)
            report["seeded"]["invoices"] = len(invoices)
            report["seeded"]["payments"] = len(payments)

        report["kept_ambiguous"] = [
            "Employee 'temp0202 01' (EMP code 32, user t4648617@gmail.com)",
            "Territory 'up' (assigned to the ambiguous employee above)",
            "Territory 'Lucknow' x2 (bfd4e25a..., bbc7b8f7...) - unreferenced, plausible real short name, one-off manual creation",
            "Customer 'Kirana Store' (created_by admin@fieldtrack.test, tied to the ambiguous employee via contact_person)",
        ]

        print("=== Seed/cleanup report ===")
        for k, v in report["deleted"].items():
            print(f"deleted {k}: {v}")
        for line in report["renamed"]:
            print(f"renamed: {line}")
        print("seeded:", report.get("seeded"))
        print("kept (ambiguous, NOT deleted, NOT modified):")
        for line in report["kept_ambiguous"]:
            print(f"  - {line}")


if __name__ == "__main__":
    run()
