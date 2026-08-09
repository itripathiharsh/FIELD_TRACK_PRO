"""
Report service — generates report data from the database.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Sequence

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.employee import Employee
from app.models.customer import Customer
from app.models.visit import Visit, VisitStatus
from app.models.geo_verification_log import GeoVerificationLog, GeoVerificationType

logger = logging.getLogger("fieldtrackpro")


class ReportService:
    """Service for generating various reports."""

    @staticmethod
    async def get_employee_visit_report(
        session: AsyncSession,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        """Generate employee visit report."""
        query = (
            select(
                Employee.id.label("employee_id"),
                Employee.full_name.label("employee_name"),
                func.count(Visit.id).label("total_visits"),
                func.sum(case((Visit.status == VisitStatus.COMPLETED, 1), else_=0)).label("completed"),
                func.sum(case((Visit.status == VisitStatus.PENDING, 1), else_=0)).label("pending"),
                func.sum(case((Visit.status == VisitStatus.MISSED, 1), else_=0)).label("missed"),
                func.sum(case((Visit.status == VisitStatus.FLAGGED, 1), else_=0)).label("flagged"),
            )
            .outerjoin(Visit, Visit.employee_id == Employee.id)
            .group_by(Employee.id, Employee.full_name)
        )

        if start_date:
            query = query.where(Visit.scheduled_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
        if end_date:
            query = query.where(Visit.scheduled_at < datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))

        result = await session.execute(query)
        rows = result.all()

        report = []
        for row in rows:
            total = row.total_visits or 0
            completed = row.completed or 0
            rate = (completed / total * 100) if total > 0 else 0.0
            report.append({
                "employee_id": str(row.employee_id),
                "employee_name": row.employee_name,
                "total_visits": total,
                "completed_visits": completed,
                "pending_visits": row.pending or 0,
                "missed_visits": row.missed or 0,
                "flagged_visits": row.flagged or 0,
                "completion_rate": round(rate, 1),
            })

        return report

    @staticmethod
    async def get_customer_visit_history(
        session: AsyncSession,
        customer_id: uuid.UUID,
    ) -> list[dict]:
        """Generate visit history for a specific customer."""
        query = (
            select(
                Visit,
                Employee.full_name.label("employee_name"),
            )
            .join(Employee, Visit.employee_id == Employee.id)
            .where(Visit.customer_id == customer_id)
            .order_by(Visit.scheduled_at.desc())
        )

        result = await session.execute(query)
        rows = result.all()

        return [
            {
                "visit_id": str(row.Visit.id),
                "scheduled_at": row.Visit.scheduled_at.isoformat() if row.Visit.scheduled_at else "",
                "status": row.Visit.status.value,
                "employee_name": row.employee_name,
                "check_in_at": row.Visit.check_in_at.isoformat() if row.Visit.check_in_at else None,
                "check_out_at": row.Visit.check_out_at.isoformat() if row.Visit.check_out_at else None,
            }
            for row in rows
        ]

    @staticmethod
    async def get_productivity_dashboard(session: AsyncSession) -> dict:
        """Generate productivity dashboard data."""
        today = datetime.now(tz=timezone.utc).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)

        # Total employees
        emp_count = await session.execute(select(func.count(Employee.id)))
        total_employees = emp_count.scalar_one()

        # Active employees (checked in today)
        active_query = (
            select(func.count(func.distinct(Visit.employee_id)))
            .where(Visit.check_in_at >= today_start)
        )
        active_result = await session.execute(active_query)
        active_employees = active_result.scalar_one()

        # Today's visits
        visit_stats = await session.execute(
            select(
                func.count(Visit.id),
                func.sum(case((Visit.status == VisitStatus.COMPLETED, 1), else_=0)),
                func.sum(case((Visit.status == VisitStatus.PENDING, 1), else_=0)),
                func.sum(case((Visit.status == VisitStatus.MISSED, 1), else_=0)),
                func.sum(case((Visit.status == VisitStatus.FLAGGED, 1), else_=0)),
            )
            .where(Visit.scheduled_at >= today_start, Visit.scheduled_at <= today_end)
        )
        stats = visit_stats.one()

        total_visits = stats[0] or 0
        avg_visits = (total_visits / active_employees) if active_employees > 0 else 0.0

        return {
            "total_employees": total_employees,
            "active_employees": active_employees,
            "total_visits_today": total_visits,
            "completed_visits_today": stats[1] or 0,
            "pending_visits_today": stats[2] or 0,
            "missed_visits_today": stats[3] or 0,
            "flagged_visits_today": stats[4] or 0,
            "avg_visits_per_employee": round(avg_visits, 1),
        }

    @staticmethod
    async def get_geo_verification_report(
        session: AsyncSession,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        """Generate geo-verification report."""
        query = (
            select(
                GeoVerificationLog,
                Employee.full_name.label("employee_name"),
                Customer.name.label("customer_name"),
            )
            .join(Visit, GeoVerificationLog.visit_id == Visit.id)
            .join(Employee, Visit.employee_id == Employee.id)
            .join(Customer, Visit.customer_id == Customer.id)
            .order_by(GeoVerificationLog.attempted_at.desc())
        )

        if start_date:
            query = query.where(GeoVerificationLog.attempted_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
        if end_date:
            query = query.where(GeoVerificationLog.attempted_at < datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))

        result = await session.execute(query)
        rows = result.all()

        return [
            {
                "visit_id": str(row.GeoVerificationLog.id),
                "employee_name": row.employee_name,
                "customer_name": row.customer_name,
                "attempted_at": row.GeoVerificationLog.attempted_at.isoformat(),
                "verification_type": row.GeoVerificationLog.verification_type.value,
                "is_valid": row.GeoVerificationLog.is_valid,
                "distance_m": row.GeoVerificationLog.distance_from_customer_m,
                "failure_reason": row.GeoVerificationLog.failure_reason,
            }
            for row in rows
        ]


report_service = ReportService()
