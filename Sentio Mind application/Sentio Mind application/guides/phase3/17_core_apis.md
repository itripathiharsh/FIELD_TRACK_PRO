# FieldTrack Pro — Core APIs (Employees, Customers, Visits)
### Phase 3.3 — Backend Development
### Revision 2 — rewritten for Python/FastAPI

Router → Service → Repository (via SQLAlchemy session) implementation for the three central modules, built against the API Design doc's endpoint list — **which is completely unchanged**; every path, method, request shape, and response shape below matches the original API Design doc exactly.

---

## 1. Employees

```python
# app/api/v1/employees.py
from fastapi import APIRouter, Depends, Query
from uuid import UUID
from app.api.deps import require_admin, get_current_user
from app.schemas.employee import EmployeeResponse, CreateEmployeeRequest, UpdateEmployeeRequest
from app.schemas.common import Page
from app.services.employee_service import EmployeeService

router = APIRouter()


@router.get("", response_model=Page[EmployeeResponse], dependencies=[Depends(require_admin)])
async def list_employees(
    territory_id: UUID | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(0),
    size: int = Query(20),
    service: EmployeeService = Depends(),
):
    return await service.list(territory_id, is_active, page, size)


@router.post("", response_model=EmployeeResponse, status_code=201, dependencies=[Depends(require_admin)])
async def create_employee(request: CreateEmployeeRequest, service: EmployeeService = Depends()):
    return await service.create(request)


@router.get("/{employee_id}", response_model=EmployeeResponse, dependencies=[Depends(require_admin)])
async def get_employee(employee_id: UUID, service: EmployeeService = Depends()):
    return await service.get_by_id(employee_id)


@router.put("/{employee_id}", response_model=EmployeeResponse, dependencies=[Depends(require_admin)])
async def update_employee(employee_id: UUID, request: UpdateEmployeeRequest, service: EmployeeService = Depends()):
    return await service.update(employee_id, request)


@router.patch("/{employee_id}/deactivate", status_code=204, dependencies=[Depends(require_admin)])
async def deactivate_employee(employee_id: UUID, service: EmployeeService = Depends()):
    await service.deactivate(employee_id)   # also revokes refresh tokens — see Authentication doc Section 3


@router.get("/me", response_model=EmployeeResponse)
async def get_my_profile(user=Depends(get_current_user), service: EmployeeService = Depends()):
    return await service.get_by_user_id(user.id)
```

**Service — creation flow** (creates both `users` and `employees` rows in one transaction):

```python
# app/services/employee_service.py
from app.security.password import hash_password
from app.models.user import User, Role
from app.models.employee import Employee


class EmployeeService:
    def __init__(self, db=Depends(get_db)):
        self.db = db

    async def create(self, request: CreateEmployeeRequest) -> Employee:
        existing = await self.db.scalar(
            select(User).where(or_(User.email == request.email, User.phone == request.phone))
        )
        if existing:
            raise DuplicateResourceException("Email or phone already registered")

        user = User(
            email=request.email,
            phone=request.phone,
            password_hash=hash_password(request.initial_password),
            role=Role.EMPLOYEE,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()   # get user.id before creating the dependent row, same transaction

        employee = Employee(
            user_id=user.id,
            full_name=request.full_name,
            territory_id=request.territory_id,
            employee_code=self._generate_employee_code(),
        )
        self.db.add(employee)
        await self.db.commit()
        await self.db.refresh(employee)
        return employee

    async def deactivate(self, employee_id):
        employee = await self.db.get(Employee, employee_id)
        if employee is None:
            raise ResourceNotFoundException("Employee not found")
        employee.user.is_active = False
        await self.db.commit()
        await RefreshTokenService(self.db).revoke_all_for_user(employee.user_id)
```

Both writes happen inside the same SQLAlchemy session/transaction (`db.flush()` before the second insert, single `db.commit()` at the end) — the same atomicity guarantee the original `@Transactional` annotation gave, just expressed as an explicit session scope instead of a declarative annotation.

---

## 2. Customers

```python
# app/api/v1/customers.py
router = APIRouter()


@router.get("", response_model=Page[CustomerResponse], dependencies=[Depends(require_admin)])
async def list_customers(
    territory_id: UUID | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(0), size: int = Query(20),
    service: CustomerService = Depends(),
):
    return await service.list(territory_id, search, page, size)


@router.post("", response_model=CustomerResponse, status_code=201, dependencies=[Depends(require_admin)])
async def create_customer(request: CreateCustomerRequest, service: CustomerService = Depends()):
    return await service.create(request)


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    user=Depends(get_current_user),
    service: CustomerService = Depends(),
):
    # ADMIN always allowed; EMPLOYEE only if they have a visit assigned to this customer —
    # same ownership-style check as the original @PreAuthorize SpEL expression, expressed
    # as an explicit guard inside the service instead of a route annotation
    await service.assert_visible_to(customer_id, user)
    return await service.get_by_id(customer_id)


@router.put("/{customer_id}", response_model=CustomerResponse, dependencies=[Depends(require_admin)])
async def update_customer(customer_id: UUID, request: UpdateCustomerRequest, service: CustomerService = Depends()):
    return await service.update(customer_id, request)


@router.get("/{customer_id}/visits", response_model=Page[VisitSummaryResponse], dependencies=[Depends(require_admin)])
async def customer_visit_history(customer_id: UUID, page: int = Query(0), size: int = Query(20), visit_service: VisitService = Depends()):
    return await visit_service.get_by_customer(customer_id, page, size)
```

**Service — geocoding on create** (per C2, auto-geocode if lat/long not explicitly supplied):

```python
# app/services/customer_service.py
from geoalchemy2.shape import from_shape
from shapely.geometry import Point


class CustomerService:
    def __init__(self, db=Depends(get_db), geocoding_service: GeocodingService = Depends()):
        self.db = db
        self.geocoding_service = geocoding_service

    async def create(self, request: CreateCustomerRequest) -> Customer:
        if request.latitude is not None and request.longitude is not None:
            location = from_shape(Point(request.longitude, request.latitude), srid=4326)
        else:
            location = await self.geocoding_service.geocode(request.address)   # calls Google Geocoding API

        customer = Customer(
            name=request.name,
            contact_number=request.contact_number,
            address=request.address,
            location=location,
            geofence_radius_m=request.geofence_radius_m or 75,
            territory_id=request.territory_id,
        )
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        return customer
```

---

## 3. Visits

The most important router in the system — carries the check-in/check-out logic that's the whole product's reason for existing.

```python
# app/api/v1/visits.py
from fastapi import APIRouter, Depends, Header, Query
from app.api.deps import require_admin, get_current_user
from app.services.visit_security import assert_is_owner

router = APIRouter()


@router.get("", response_model=Page[VisitSummaryResponse], dependencies=[Depends(require_admin)])
async def list_visits(
    status: VisitStatus | None = Query(None),
    employee_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(0), size: int = Query(20),
    service: VisitService = Depends(),
):
    return await service.search(status, employee_id, date_from, date_to, page, size)


@router.get("/me/today", response_model=list[VisitSummaryResponse])
async def my_today_visits(user=Depends(get_current_user), service: VisitService = Depends()):
    return await service.get_today_for_employee(user.id)


@router.post("", response_model=VisitResponse, status_code=201, dependencies=[Depends(require_admin)])
async def schedule_visit(request: ScheduleVisitRequest, service: VisitService = Depends()):
    return await service.schedule(request)


@router.post("/bulk", response_model=list[VisitResponse], status_code=201, dependencies=[Depends(require_admin)])
async def bulk_schedule(request: BulkScheduleRequest, service: VisitService = Depends()):
    return await service.bulk_schedule(request)


@router.get("/{visit_id}", response_model=VisitResponse)
async def get_visit(visit_id: UUID, user=Depends(get_current_user), service: VisitService = Depends()):
    await assert_is_owner(visit_id, user, service.db)   # ADMIN or the assigned employee only
    return await service.get_by_id(visit_id)


@router.post("/{visit_id}/check-in", response_model=CheckInResponse)
async def check_in(
    visit_id: UUID,
    request: CheckInRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
    service: VisitService = Depends(),
):
    await assert_is_owner(visit_id, user, service.db)
    return await service.check_in(visit_id, request, idempotency_key)


@router.post("/{visit_id}/check-out", response_model=VisitResponse)
async def check_out(visit_id: UUID, request: CheckOutRequest, user=Depends(get_current_user), service: VisitService = Depends()):
    await assert_is_owner(visit_id, user, service.db)
    return await service.check_out(visit_id, request)


@router.patch("/{visit_id}/status", response_model=VisitResponse, dependencies=[Depends(require_admin)])
async def update_status(visit_id: UUID, request: UpdateStatusRequest, service: VisitService = Depends()):
    return await service.update_status_manually(visit_id, request)
```

**`assert_is_owner`** enforces the resource-ownership rule from Security Design Section 2 — a small async function checked explicitly at the top of each visit-scoped route, the direct equivalent of the original `@visitSecurity.isOwner` SpEL expression, kept in one reusable place (`app/services/visit_security.py`):

```python
# app/services/visit_security.py
async def assert_is_owner(visit_id: UUID, user, db) -> None:
    if user.role == Role.ADMIN:
        return
    visit = await db.get(Visit, visit_id)
    if visit is None or visit.employee.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this visit")
```

---

**Next up:** Database Implementation (Phase 3.4) — SQLAlchemy models matching the schema exactly, and the geo-fence query itself.
