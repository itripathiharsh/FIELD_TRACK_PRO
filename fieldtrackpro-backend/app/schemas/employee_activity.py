"""
Employee Activity: a read-only aggregation over existing visits, payments,
and order-capture media for one employee (P2-C). Deliberately not a new
data store - every field here is computed from tables that already exist.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.payment import PaymentMethod, PaymentStatus
from app.models.visit import VisitStatus


class EmployeeActivityVisit(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    outlet_code: str | None
    scheduled_at: datetime
    check_in_at: datetime | None
    check_out_at: datetime | None
    duration_minutes: int | None
    status: VisitStatus
    geo_failure_count: int


class EmployeeActivityCollection(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str | None
    amount: Decimal
    payment_method: PaymentMethod
    payment_date: date
    status: PaymentStatus


class EmployeeActivityOrder(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    note: str | None
    uploaded_at: datetime


class EmployeeActivity(BaseModel):
    employee_id: uuid.UUID
    full_name: str
    employee_code: str | None
    territory_id: uuid.UUID | None
    territory_name: str | None
    is_active: bool

    visits_total: int
    visits_completed: int
    visits_missed: int
    visits_flagged: int
    visits: list[EmployeeActivityVisit]

    collections_total: int
    collections_pending: int
    collections_verified: int
    collections_rejected: int
    collections_verified_amount: Decimal
    collections: list[EmployeeActivityCollection]

    orders_total: int
    orders: list[EmployeeActivityOrder]
