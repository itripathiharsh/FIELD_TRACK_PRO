import uuid
from datetime import timedelta, timezone
import pytest
from httpx import AsyncClient

from tests.integration.conftest import TEST_MARKER, requires_db
from app.core.datetime_utils import get_ist_today_range, IST

pytestmark = [requires_db, pytest.mark.integration, pytest.mark.asyncio]


async def test_invalid_cross_territory_area_assignment_rejected(
    client: AsyncClient,
    admin_headers: dict[str, str],
    seeded_world: dict,
    created_territories: list,
):
    """WEB-H-3: Assigning an area from an unassigned territory must be rejected with 400."""
    uid = uuid.uuid4().hex[:8]

    # Create Territory B
    res_tb = await client.post(
        "/api/v1/territories",
        headers=admin_headers,
        json={"name": f"{TEST_MARKER}Cross Zone B {uid}"},
    )
    assert res_tb.status_code == 201
    tb_id = res_tb.json()["id"]
    created_territories.append(tb_id)

    # Create Area B in Territory B
    res_ab = await client.post(
        "/api/v1/areas",
        headers=admin_headers,
        json={"name": f"{TEST_MARKER}Area B {uid}", "territory_id": tb_id},
    )
    assert res_ab.status_code == 201
    ab_id = res_ab.json()["id"]

    # seeded_world["employee_id"] is assigned to seeded_world["territory_id"]
    # Attempting to assign Area B (which belongs to Territory B) to this employee must fail with 400
    assign_res = await client.post(
        f"/api/v1/employees/{seeded_world['employee_id']}/areas",
        headers=admin_headers,
        json={"area_id": ab_id},
    )
    assert assign_res.status_code == 400
    assert assign_res.json()["error"]["code"] == "INVALID_AREA_TERRITORY"


async def test_territory_reassignment_cleans_up_orphaned_areas(
    client: AsyncClient,
    admin_headers: dict[str, str],
    seeded_world: dict,
    created_territories: list,
):
    """WEB-H-3: When employee's territory changes, orphaned area assignments must be cleaned up."""
    uid = uuid.uuid4().hex[:8]

    # Create Territory 1 and Area 1
    res_t1 = await client.post(
        "/api/v1/territories",
        headers=admin_headers,
        json={"name": f"{TEST_MARKER}Zone 1 {uid}"},
    )
    assert res_t1.status_code == 201
    t1_id = res_t1.json()["id"]
    created_territories.append(t1_id)

    res_a1 = await client.post(
        "/api/v1/areas",
        headers=admin_headers,
        json={"name": f"{TEST_MARKER}Area 1 {uid}", "territory_id": t1_id},
    )
    assert res_a1.status_code == 201
    a1_id = res_a1.json()["id"]

    # Create Territory 2 and Area 2
    res_t2 = await client.post(
        "/api/v1/territories",
        headers=admin_headers,
        json={"name": f"{TEST_MARKER}Zone 2 {uid}"},
    )
    assert res_t2.status_code == 201
    t2_id = res_t2.json()["id"]
    created_territories.append(t2_id)

    res_a2 = await client.post(
        "/api/v1/areas",
        headers=admin_headers,
        json={"name": f"{TEST_MARKER}Area 2 {uid}", "territory_id": t2_id},
    )
    assert res_a2.status_code == 201
    a2_id = res_a2.json()["id"]

    # Create a new Employee in Territory 1
    emp_res = await client.post(
        "/api/v1/employees/register",
        headers=admin_headers,
        json={
            "user": {
                "email": f"emp_clean_{uid}@example.com",
                "password": "Password123!",
                "role": "EMPLOYEE",
            },
            "full_name": f"{TEST_MARKER}Emp Clean {uid}",
            "employee_code": f"EC_{uid}".upper(),
            "territory_id": t1_id,
        },
    )
    assert emp_res.status_code == 201
    emp_id = emp_res.json()["id"]

    # Assign Area 1 to Employee (succeeds because Employee is in Territory 1)
    assign1_res = await client.post(
        f"/api/v1/employees/{emp_id}/areas",
        headers=admin_headers,
        json={"area_id": a1_id},
    )
    assert assign1_res.status_code == 201

    # Verify Area 1 is in employee's area coverage list
    list1_res = await client.get(f"/api/v1/employees/{emp_id}/areas", headers=admin_headers)
    assert list1_res.status_code == 200
    assert len(list1_res.json()) == 1
    assert list1_res.json()[0]["area_id"] == a1_id

    # Reassign Employee to Territory 2
    update_res = await client.patch(
        f"/api/v1/employees/{emp_id}",
        headers=admin_headers,
        json={"territory_id": t2_id},
    )
    assert update_res.status_code == 200

    # Verify Area 1 was pruned because Employee is no longer in Territory 1
    list2_res = await client.get(f"/api/v1/employees/{emp_id}/areas", headers=admin_headers)
    assert list2_res.status_code == 200
    assert len(list2_res.json()) == 0

    # Now assigning Area 2 succeeds because Employee is in Territory 2
    assign2_res = await client.post(
        f"/api/v1/employees/{emp_id}/areas",
        headers=admin_headers,
        json={"area_id": a2_id},
    )
    assert assign2_res.status_code == 201


async def test_ist_datetime_boundaries():
    """WEB-C-1 / WEB-C-2: Verify authoritative IST day range boundaries."""
    start_dt, end_dt = get_ist_today_range()

    # Range must span exactly 24 hours
    assert end_dt - start_dt == timedelta(days=1)

    # Both must be timezone aware in UTC
    assert start_dt.tzinfo == timezone.utc
    assert end_dt.tzinfo == timezone.utc

    # When converted to IST, start_dt must be 00:00:00.000000
    ist_start = start_dt.astimezone(IST)
    assert ist_start.hour == 0
    assert ist_start.minute == 0
    assert ist_start.second == 0
    assert ist_start.microsecond == 0

    # When converted to IST, end_dt must be next day 00:00:00.000000
    ist_end = end_dt.astimezone(IST)
    assert ist_end.hour == 0
    assert ist_end.minute == 0
    assert ist_end.second == 0
    assert ist_end.microsecond == 0
    assert (ist_end.date() - ist_start.date()) == timedelta(days=1)
