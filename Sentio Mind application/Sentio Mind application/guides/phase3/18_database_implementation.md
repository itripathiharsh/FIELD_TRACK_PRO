# FieldTrack Pro — Database Implementation
### Phase 3.4 — Backend Development
### Revision 2 — rewritten for Python/SQLAlchemy + GeoAlchemy2

ORM layer matching the Database Design schema exactly, plus the one query that matters most: the PostGIS geo-fence check.

---

## 1. Core Models

```python
# app/models/customer.py
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geography
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150))
    contact_number: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    geofence_radius_m: Mapped[int] = mapped_column(Integer, default=75)
    territory_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("territories.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

```python
# app/models/visit.py
import enum
import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geography
from app.database import Base


class VisitStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    FLAGGED = "FLAGGED"


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False)
    scheduled_at: Mapped[datetime]
    status: Mapped[VisitStatus] = mapped_column(Enum(VisitStatus))
    check_in_at: Mapped[datetime | None]
    check_in_location: Mapped[str | None] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    check_out_at: Mapped[datetime | None]
    check_out_location: Mapped[str | None] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    employee: Mapped["Employee"] = relationship(lazy="joined")
    customer: Mapped["Customer"] = relationship(lazy="joined")
```

`VisitStatus` is a Python `str` enum mapped directly to the Postgres `ENUM` type — matches the DB CHECK constraint exactly, so an invalid status can't even construct a valid `Visit` object, the same compile-time-ish guarantee the original Java enum gave.

---

## 2. The Geo-Fence Query (Core Product Logic)

This is the single most important query in the codebase — it's what makes server-side verification (E5, the non-negotiable from Security Design) actually real:

```python
# app/geo/verification.py
from sqlalchemy import select, func
from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_SetSRID, ST_MakePoint
from app.models.customer import Customer


async def verify_location(db, customer_id, latitude: float, longitude: float) -> tuple[bool, float]:
    point = func.cast(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326), Geography)

    result = await db.execute(
        select(
            ST_DWithin(Customer.location, point, Customer.geofence_radius_m).label("within_radius"),
            ST_Distance(Customer.location, point).label("distance_meters"),
        ).where(Customer.id == customer_id)
    )
    row = result.one()
    return row.within_radius, row.distance_meters
```

**Why GeoAlchemy2's function wrappers here specifically**: `ST_DWithin` and `ST_Distance` don't map to plain SQLAlchemy column comparisons — GeoAlchemy2 provides typed Python wrappers around these PostGIS functions so the query stays fully parameterized (no string concatenation, no injection risk) while still being the actual product-critical calculation. This is the direct equivalent of the original's deliberate native-SQL exception, except here it doesn't even need to drop to raw SQL — GeoAlchemy2's ORM-integrated function expressions handle it natively.

---

## 3. Geo-Verification Service (Wraps the Query, Writes the Audit Log)

```python
# app/services/geo_verification_service.py
from decimal import Decimal
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from app.geo.verification import verify_location
from app.models.geo_verification_log import GeoVerificationLog


class GeoVerificationService:
    def __init__(self, db):
        self.db = db

    async def verify(self, visit_id, customer_id, lat: float, lng: float) -> "GeoVerificationOutcome":
        within_radius, distance_meters = await verify_location(self.db, customer_id, lat, lng)

        reason = None if within_radius else "OUTSIDE_RADIUS"

        log = GeoVerificationLog(
            visit_id=visit_id,
            attempted_location=from_shape(Point(lng, lat), srid=4326),
            distance_meters=Decimal(str(distance_meters)),
            result="SUCCESS" if within_radius else "FAILED",
            reason=reason,
        )
        self.db.add(log)
        await self.db.commit()   # insert-only, per Security Design Section 4 — no update/delete path exists in code

        return GeoVerificationOutcome(is_valid=within_radius, distance_meters=distance_meters, reason=reason)
```

Note this log write happens **regardless of outcome** — success and failure both get logged, which is what makes the Geo-verification Report (K4) and the repeated-failure alert (FR-28) possible without any extra tracking logic elsewhere. Identical behavior to the original.

**Database-level insert-only enforcement** (per Security Design Section 4) is applied the same way it was originally — via a `REVOKE UPDATE, DELETE ON geo_verification_logs FROM fieldtrackpro_app;` grant statement run once against the production role, added as a standalone Alembic migration rather than application code, since this needs to be a database-level guarantee, not just an application-level convention.

---

## 4. Repository-Equivalent Query Patterns

SQLAlchemy doesn't have a separate repository-interface layer the way Spring Data JPA does — query methods live directly as small async functions or as methods on the service classes that need them, using SQLAlchemy's `select()` construct:

```python
# app/services/visit_service.py (query excerpts)
from sqlalchemy import select, func

async def get_by_employee_and_date_range(db, employee_id, date_from, date_to) -> list[Visit]:
    result = await db.execute(
        select(Visit).where(
            Visit.employee_id == employee_id,
            Visit.scheduled_at.between(date_from, date_to),
        )
    )
    return result.scalars().all()

async def count_failed_attempts(db, visit_id) -> int:
    result = await db.execute(
        select(func.count()).select_from(GeoVerificationLog).where(
            GeoVerificationLog.visit_id == visit_id,
            GeoVerificationLog.result == "FAILED",
        )
    )
    return result.scalar_one()   # powers FR-28 repeated-failure alert, same threshold logic as before
```

This is a smaller amount of boilerplate than the original `JpaRepository` interfaces, not a functional gap — every derived-query-method equivalent from the original repository layer has a direct `select()` translation.

---

## 5. Migration Discipline

- Every schema change from here forward is a new Alembic revision (`alembic revision --autogenerate -m "..."`, reviewed, then `alembic upgrade head`), never a hand-edit of a revision file that's already been applied anywhere — this is the rule that keeps multiple Antigravity sessions from producing conflicting schema states, same discipline as the original Flyway rule.
- SQLAlchemy models are written to match applied migrations, not the other way around — the SQL (captured in Alembic revision files) is the source of truth. Unlike Hibernate's `ddl-auto: validate`, SQLAlchemy has no automatic startup schema-match check, so this is enforced by process discipline plus an integration test that asserts `alembic check` (no pending model/migration drift) passes in CI before merge — closing the gap the original's automatic validation covered.

---

**Next up:** Business Logic (Phase 3.5) — the visit lifecycle state machine, offline-sync conflict handling, and the notification triggers that tie everything together.
