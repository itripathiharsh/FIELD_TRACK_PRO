"""
Form Template Builder API routes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.exceptions.custom import BaseAPIException
from app.models.form_template import (
    FormQuestion,
    FormStatus,
    FormSubmission,
    FormTemplate,
)
from app.models.user import Role, User
from app.models.visit import Visit
from app.schemas.form_template import (
    FormTemplateCreate,
    FormTemplateListRead,
    FormTemplateRead,
    FormTemplateUpdate,
    QuestionCreate,
    QuestionRead,
    QuestionUpdate,
    QuestionOptionCreate,
    QuestionOptionRead,
    QuestionOptionUpdate,
    SectionCreate,
    SectionRead,
    SectionUpdate,
    SubmissionCreate,
    SubmissionRead,
    SubmissionDetailRead,
    AnswerRead,
    FormRenderRead,
)
from app.services import form_template_service
from app.services.pdf_service import render_submission_pdf
from app.services.visit_service import assert_visit_access, get_visit

router = APIRouter(tags=["Form Templates"])

AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


def _enrich_template_read(template: FormTemplate) -> FormTemplateRead:
    """Build a FormTemplateRead with enriched fields."""
    question_count = sum(len(s.questions) for s in template.sections)
    return FormTemplateRead(
        id=template.id,
        name=template.name,
        description=template.description,
        category_id=template.category_id,
        status=template.status,
        version=template.version,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
        published_at=template.published_at,
        archived_at=template.archived_at,
        sections=[
            SectionRead(
                id=s.id,
                form_id=s.form_id,
                title=s.title,
                description=s.description,
                display_order=s.display_order,
                created_at=s.created_at,
                updated_at=s.updated_at,
                questions=[
                    QuestionRead(
                        id=q.id,
                        section_id=q.section_id,
                        form_id=q.form_id,
                        question_text=q.question_text,
                        help_text=q.help_text,
                        question_type=q.question_type,
                        required=q.required,
                        display_order=q.display_order,
                        placeholder=q.placeholder,
                        validation_config=q.validation_config,
                        created_at=q.created_at,
                        updated_at=q.updated_at,
                        options=[
                            QuestionOptionRead(
                                id=o.id,
                                question_id=o.question_id,
                                label=o.label,
                                value=o.value,
                                display_order=o.display_order,
                            )
                            for o in q.options
                        ],
                    )
                    for q in s.questions
                ],
            )
            for s in template.sections
        ],
        category_name=template.category.name if template.category else None,
        question_count=question_count,
    )


# ---------------------------------------------------------------------------
# Template endpoints
# ---------------------------------------------------------------------------

@router.post("/form-templates", response_model=FormTemplateRead, dependencies=[AdminOnly])
async def create_template(data: FormTemplateCreate, session: AsyncSession = Depends(get_async_session), current_user: CurrentUser = None):
    template = await form_template_service.create_template(
        session=session, name=data.name, created_by=current_user.id,
        description=data.description, category_id=data.category_id,
    )
    return _enrich_template_read(template)


@router.get("/form-templates", response_model=list[FormTemplateListRead], dependencies=[AnyAuth])
async def list_templates(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
    status: FormStatus | None = None,
    category_id: uuid.UUID | None = None,
):
    """
    P1-1: an EMPLOYEE only ever sees PUBLISHED templates - the client-supplied
    `status` is honoured only for ADMIN (who still manages DRAFT/ARCHIVED
    templates here), overridden server-side for everyone else.
    """
    if current_user.role != Role.ADMIN:
        status = FormStatus.PUBLISHED
    templates = await form_template_service.list_templates(session, status=status, category_id=category_id)
    result = []
    for t in templates:
        q_count = await session.execute(select(func.count(FormQuestion.id)).where(FormQuestion.form_id == t.id))
        s_count = await session.execute(select(func.count(FormSubmission.id)).where(FormSubmission.form_id == t.id))
        v_count = await session.execute(select(func.count(Visit.id)).where(Visit.required_form_id == t.id))
        result.append(FormTemplateListRead(
            id=t.id, name=t.name, description=t.description, category_id=t.category_id,
            status=t.status, version=t.version, created_by=t.created_by,
            created_at=t.created_at, updated_at=t.updated_at, published_at=t.published_at,
            category_name=t.category.name if t.category else None,
            question_count=q_count.scalar_one(), submission_count=s_count.scalar_one(),
            visit_count=v_count.scalar_one(),
        ))
    return result


@router.get("/form-templates/{template_id}", response_model=FormTemplateRead, dependencies=[AnyAuth])
async def get_template(template_id: uuid.UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_async_session)):
    """
    P1-1: an EMPLOYEE may only fetch a PUBLISHED template by ID - closes the
    IDOR-style gap where knowing/guessing a DRAFT/ARCHIVED template's id
    would otherwise return its full structure. Mirrors the identical check
    already enforced on /render. ADMIN keeps full management access.
    """
    template = await form_template_service.get_template(session, template_id)
    if current_user.role != Role.ADMIN and template.status != FormStatus.PUBLISHED:
        raise BaseAPIException(status_code=403, detail="This form is not available", error_code="FORM_NOT_PUBLISHED")
    return _enrich_template_read(template)


@router.patch("/form-templates/{template_id}", response_model=FormTemplateRead, dependencies=[AdminOnly])
async def update_template(template_id: uuid.UUID, data: FormTemplateUpdate, session: AsyncSession = Depends(get_async_session)):
    template = await form_template_service.update_template(
        session, template_id, name=data.name, description=data.description, category_id=data.category_id,
    )
    return _enrich_template_read(template)


@router.delete("/form-templates/{template_id}", status_code=204, dependencies=[AdminOnly])
async def delete_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    await form_template_service.delete_template(session, template_id)


@router.post("/form-templates/{template_id}/publish", response_model=FormTemplateRead, dependencies=[AdminOnly])
async def publish_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_async_session), current_user: CurrentUser = None):
    template = await form_template_service.publish_template(session, template_id, published_by=current_user.id)
    return _enrich_template_read(template)


@router.post("/form-templates/{template_id}/unpublish", response_model=FormTemplateRead, dependencies=[AdminOnly])
async def unpublish_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    template = await form_template_service.unpublish_template(session, template_id)
    return _enrich_template_read(template)


@router.post("/form-templates/{template_id}/archive", response_model=FormTemplateRead, dependencies=[AdminOnly])
async def archive_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    template = await form_template_service.archive_template(session, template_id)
    return _enrich_template_read(template)


@router.post("/form-templates/{template_id}/duplicate", response_model=FormTemplateRead, dependencies=[AdminOnly])
async def duplicate_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_async_session), current_user: CurrentUser = None):
    template = await form_template_service.duplicate_template(session, template_id, current_user.id)
    return _enrich_template_read(template)


# ---------------------------------------------------------------------------
# Section endpoints
# ---------------------------------------------------------------------------

@router.post("/form-templates/{template_id}/sections", response_model=SectionRead, dependencies=[AdminOnly])
async def add_section(template_id: uuid.UUID, data: SectionCreate, session: AsyncSession = Depends(get_async_session)):
    section = await form_template_service.add_section(
        session, template_id, title=data.title, description=data.description, display_order=data.display_order,
    )
    return SectionRead.model_validate(section)


@router.patch("/sections/{section_id}", response_model=SectionRead, dependencies=[AdminOnly])
async def update_section(section_id: uuid.UUID, data: SectionUpdate, session: AsyncSession = Depends(get_async_session)):
    section = await form_template_service.update_section(
        session, section_id, title=data.title, description=data.description, display_order=data.display_order,
    )
    return SectionRead.model_validate(section)


@router.delete("/sections/{section_id}", status_code=204, dependencies=[AdminOnly])
async def delete_section(section_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    await form_template_service.delete_section(session, section_id)


# ---------------------------------------------------------------------------
# Question endpoints
# ---------------------------------------------------------------------------

@router.post("/form-templates/{template_id}/questions", response_model=QuestionRead, dependencies=[AdminOnly])
async def add_question(template_id: uuid.UUID, data: QuestionCreate, session: AsyncSession = Depends(get_async_session)):
    question = await form_template_service.add_question(
        session, template_id, section_id=data.section_id, question_text=data.question_text,
        question_type=data.question_type, required=data.required, help_text=data.help_text,
        placeholder=data.placeholder, display_order=data.display_order,
        validation_config=data.validation_config,
        options=[o.model_dump() for o in data.options] if data.options else None,
    )
    return QuestionRead.model_validate(question)


@router.patch("/questions/{question_id}", response_model=QuestionRead, dependencies=[AdminOnly])
async def update_question(question_id: uuid.UUID, data: QuestionUpdate, session: AsyncSession = Depends(get_async_session)):
    update_data = data.model_dump(exclude_unset=True)
    if "options" in update_data:
        update_data["options"] = [o.model_dump() for o in data.options] if data.options else []
    question = await form_template_service.update_question(session, question_id, **update_data)
    return QuestionRead.model_validate(question)


@router.delete("/questions/{question_id}", status_code=204, dependencies=[AdminOnly])
async def delete_question(question_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    await form_template_service.delete_question(session, question_id)


@router.post("/questions/{question_id}/duplicate", response_model=QuestionRead, dependencies=[AdminOnly])
async def duplicate_question(question_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    question = await form_template_service.duplicate_question(session, question_id)
    return QuestionRead.model_validate(question)


@router.post("/questions/{question_id}/options", response_model=QuestionOptionRead, dependencies=[AdminOnly])
async def add_option(question_id: uuid.UUID, data: QuestionOptionCreate, session: AsyncSession = Depends(get_async_session)):
    option = await form_template_service.add_option(
        session, question_id, label=data.label, value=data.value, display_order=data.display_order,
    )
    return QuestionOptionRead.model_validate(option)


@router.patch("/question-options/{option_id}", response_model=QuestionOptionRead, dependencies=[AdminOnly])
async def update_option(option_id: uuid.UUID, data: QuestionOptionUpdate, session: AsyncSession = Depends(get_async_session)):
    option = await form_template_service.update_option(
        session, option_id, label=data.label, value=data.value, display_order=data.display_order,
    )
    return QuestionOptionRead.model_validate(option)


@router.delete("/question-options/{option_id}", status_code=204, dependencies=[AdminOnly])
async def delete_option(option_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    await form_template_service.delete_option(session, option_id)


# ---------------------------------------------------------------------------
# Employee-facing: get form for rendering
# ---------------------------------------------------------------------------

@router.get("/form-templates/{template_id}/render", response_model=FormRenderRead, dependencies=[AnyAuth])
async def render_form(template_id: uuid.UUID, session: AsyncSession = Depends(get_async_session), current_user: CurrentUser = None):
    template = await form_template_service.get_template(session, template_id)
    if current_user.role != Role.ADMIN and template.status != FormStatus.PUBLISHED:
        # Employees fill PUBLISHED forms only. Admins still use this endpoint
        # to preview a DRAFT/ARCHIVED form's employee-facing rendering.
        raise BaseAPIException(status_code=403, detail="This form is not available", error_code="FORM_NOT_PUBLISHED")
    return FormRenderRead(
        id=template.id, name=template.name, description=template.description,
        version=template.version, status=template.status,
        sections=[
            SectionRead(
                id=s.id, form_id=s.form_id, title=s.title, description=s.description,
                display_order=s.display_order, created_at=s.created_at, updated_at=s.updated_at,
                questions=[
                    QuestionRead(
                        id=q.id, section_id=q.section_id, form_id=q.form_id,
                        question_text=q.question_text, help_text=q.help_text,
                        question_type=q.question_type, required=q.required,
                        display_order=q.display_order, placeholder=q.placeholder,
                        validation_config=q.validation_config,
                        created_at=q.created_at, updated_at=q.updated_at,
                        options=[
                            QuestionOptionRead(id=o.id, question_id=o.question_id, label=o.label, value=o.value, display_order=o.display_order)
                            for o in q.options
                        ],
                    )
                    for q in s.questions
                ],
            )
            for s in template.sections
        ],
    )


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------

async def _resolve_submission_context(
    submission: FormSubmission, session: AsyncSession
) -> dict:
    """
    Who filled it, for which outlet, during which visit - the context an
    admin needs to make sense of a submission, per the "never an orphaned
    standalone object" requirement. Resolved fresh per submission (list
    sizes here are small admin/review views, matching this codebase's
    existing N+1-per-row style for template list enrichment) rather than
    baked onto FormSubmission itself, since none of it is that row's own
    data - it all belongs to the visit and the submitter's identity.
    """
    from app.models.customer import Customer
    from app.models.employee import Employee
    from app.models.territory import Territory

    visit_row = await session.execute(
        select(Visit.scheduled_at, Customer.name, Customer.outlet_code, Territory.name)
        .join(Customer, Customer.id == Visit.customer_id)
        .outerjoin(Territory, Territory.id == Customer.territory_id)
        .where(Visit.id == submission.visit_id)
    )
    row = visit_row.one_or_none()
    visit_scheduled_at, customer_name, outlet_code, territory_name = row if row else (None, None, None, None)

    # submitted_by is a users.id - resolve to the employee's real name where
    # one exists (a submitting ADMIN has no employee profile, so falls back
    # to their account email rather than showing nothing).
    employee_row = await session.execute(
        select(Employee.full_name).where(Employee.user_id == submission.submitted_by)
    )
    employee_name = employee_row.scalar_one_or_none()
    if employee_name is None:
        user_row = await session.execute(select(User.email).where(User.id == submission.submitted_by))
        employee_name = user_row.scalar_one_or_none()

    return {
        "employee_name": employee_name,
        "customer_name": customer_name,
        "outlet_code": outlet_code,
        "territory_name": territory_name,
        "visit_scheduled_at": visit_scheduled_at,
    }


async def _require_visit_access(visit_id: uuid.UUID, current_user: User, session: AsyncSession) -> None:
    """
    Employees may only act on a visit assigned to them; admins may act on
    any visit. Delegates to visit_service's single authoritative
    visit-ownership check (P2-1) - previously reimplemented inline here.
    Preserves the existing behavior of never even looking up the visit for
    a non-employee caller.
    """
    if current_user.role != Role.EMPLOYEE:
        return
    visit = await get_visit(visit_id, session)
    await assert_visit_access(visit, current_user, session)


@router.post("/form-submissions", response_model=SubmissionRead)
async def create_submission(data: SubmissionCreate, session: AsyncSession = Depends(get_async_session), current_user: CurrentUser = None):
    await _require_visit_access(data.visit_id, current_user, session)
    submission = await form_template_service.create_or_update_submission(
        session=session, form_id=data.form_id, visit_id=data.visit_id,
        user_id=current_user.id, answers=[a.model_dump() for a in data.answers], submit=False,
        is_admin=current_user.role == Role.ADMIN,
    )
    return SubmissionRead.model_validate(submission)


@router.post("/form-submissions/{submission_id}/submit", response_model=SubmissionRead)
async def submit_form(submission_id: uuid.UUID, session: AsyncSession = Depends(get_async_session), current_user: CurrentUser = None):
    submission = await form_template_service.get_submission(session, submission_id)
    if submission.submitted_by != current_user.id and current_user.role != Role.ADMIN:
        raise BaseAPIException(status_code=403, detail="Not your submission", error_code="NOT_OWNER")
    submission = await form_template_service.finalize_submission(session, submission_id)
    return SubmissionRead.model_validate(submission)


def _question_lookup_from_snapshot(snapshot: dict) -> dict[uuid.UUID, dict]:
    lookup: dict[uuid.UUID, dict] = {}
    for section in snapshot["sections"]:
        for question in section["questions"]:
            lookup[uuid.UUID(question["id"])] = question
    return lookup


def _sections_from_snapshot(snapshot: dict) -> list[SectionRead]:
    now = datetime.now(tz=timezone.utc)
    return [
        SectionRead(
            id=uuid.UUID(s["id"]), form_id=uuid.UUID(snapshot["id"]), title=s["title"],
            description=s["description"], display_order=s["display_order"],
            created_at=now, updated_at=now,
            questions=[
                QuestionRead(
                    id=uuid.UUID(q["id"]), section_id=uuid.UUID(s["id"]), form_id=uuid.UUID(snapshot["id"]),
                    question_text=q["question_text"], help_text=q["help_text"],
                    question_type=q["question_type"], required=q["required"],
                    display_order=q["display_order"], placeholder=q["placeholder"],
                    validation_config=q["validation_config"], created_at=now, updated_at=now,
                    options=[
                        QuestionOptionRead(id=uuid.UUID(o["id"]), question_id=uuid.UUID(q["id"]), label=o["label"], value=o["value"], display_order=o["display_order"])
                        for o in q["options"]
                    ],
                )
                for q in s["questions"]
            ],
        )
        for s in snapshot["sections"]
    ]


def _sections_from_live_template(template: FormTemplate) -> list[SectionRead]:
    return [
        SectionRead(
            id=s.id, form_id=s.form_id, title=s.title, description=s.description,
            display_order=s.display_order, created_at=s.created_at, updated_at=s.updated_at,
            questions=[
                QuestionRead(
                    id=q.id, section_id=q.section_id, form_id=q.form_id,
                    question_text=q.question_text, help_text=q.help_text,
                    question_type=q.question_type, required=q.required,
                    display_order=q.display_order, placeholder=q.placeholder,
                    validation_config=q.validation_config,
                    created_at=q.created_at, updated_at=q.updated_at,
                    options=[
                        QuestionOptionRead(id=o.id, question_id=o.question_id, label=o.label, value=o.value, display_order=o.display_order)
                        for o in q.options
                    ],
                )
                for q in s.questions
            ],
        )
        for s in template.sections
    ]


@router.get("/form-submissions/{submission_id}", response_model=SubmissionDetailRead)
async def get_submission_detail(submission_id: uuid.UUID, session: AsyncSession = Depends(get_async_session), current_user: CurrentUser = None):
    submission = await form_template_service.get_submission(session, submission_id)
    if submission.submitted_by != current_user.id and current_user.role != Role.ADMIN:
        raise BaseAPIException(status_code=403, detail="Not authorized", error_code="NOT_AUTHORIZED")

    template = await form_template_service.get_template(session, submission.form_id)
    snapshot = await form_template_service.get_version_snapshot(session, submission.form_id, submission.form_version)

    if snapshot is not None:
        # The exact structure this submission was answered against - never
        # the live template, which may have moved on to a later version.
        question_lookup = _question_lookup_from_snapshot(snapshot)
        sections = _sections_from_snapshot(snapshot)
    else:
        # No snapshot exists for this version (e.g. a draft saved before the
        # form was ever published). Fall back to the live structure.
        question_lookup = {q.id: q for s in template.sections for q in s.questions}
        sections = _sections_from_live_template(template)

    answer_reads = []
    for ans in submission.answers:
        q = question_lookup.get(ans.question_id)
        if snapshot is not None:
            q_text = q["question_text"] if q else None
            q_type = q["question_type"] if q else None
            q_options = [
                QuestionOptionRead(id=uuid.UUID(o["id"]), question_id=ans.question_id, label=o["label"], value=o["value"], display_order=o["display_order"])
                for o in (q["options"] if q else [])
            ]
        else:
            q_text = q.question_text if q else None
            q_type = q.question_type if q else None
            q_options = [
                QuestionOptionRead(id=o.id, question_id=o.question_id, label=o.label, value=o.value, display_order=o.display_order)
                for o in (q.options if q else [])
            ]
        answer_reads.append(AnswerRead(
            id=ans.id, submission_id=ans.submission_id, question_id=ans.question_id,
            answer_value=ans.answer_value, created_at=ans.created_at, updated_at=ans.updated_at,
            question_text=q_text, question_type=q_type, options=q_options,
        ))

    context = await _resolve_submission_context(submission, session)

    return SubmissionDetailRead(
        id=submission.id, form_id=submission.form_id, form_name=template.name,
        form_version=submission.form_version, visit_id=submission.visit_id,
        submitted_by=submission.submitted_by, employee_name=context["employee_name"],
        customer_name=context["customer_name"], outlet_code=context["outlet_code"],
        territory_name=context["territory_name"], visit_scheduled_at=context["visit_scheduled_at"],
        status=submission.status, started_at=submission.started_at,
        submitted_at=submission.submitted_at, answers=answer_reads, sections=sections,
    )


@router.get("/form-submissions/{submission_id}/pdf")
async def download_submission_pdf(submission_id: uuid.UUID, session: AsyncSession = Depends(get_async_session), current_user: CurrentUser = None):
    detail = await get_submission_detail(submission_id, session, current_user)
    pdf_bytes = render_submission_pdf(detail)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="submission-{submission_id}.pdf"'},
    )


async def _resolve_submission_contexts_batch(
    submissions: Sequence[FormSubmission], session: AsyncSession
) -> dict[uuid.UUID, dict]:
    """
    P1-15: batched form of _resolve_submission_context - one round trip per
    lookup kind (visit/customer/territory, employee name, email fallback)
    for the whole page instead of one full round of queries per submission.
    """
    from app.models.customer import Customer
    from app.models.employee import Employee
    from app.models.territory import Territory

    if not submissions:
        return {}

    visit_ids = {s.visit_id for s in submissions}
    visit_rows = await session.execute(
        select(Visit.id, Visit.scheduled_at, Customer.name, Customer.outlet_code, Territory.name)
        .join(Customer, Customer.id == Visit.customer_id)
        .outerjoin(Territory, Territory.id == Customer.territory_id)
        .where(Visit.id.in_(visit_ids))
    )
    visit_context = {
        vid: {"visit_scheduled_at": sched, "customer_name": cname, "outlet_code": ocode, "territory_name": tname}
        for vid, sched, cname, ocode, tname in visit_rows.all()
    }

    submitter_ids = {s.submitted_by for s in submissions}
    employee_rows = await session.execute(
        select(Employee.user_id, Employee.full_name).where(Employee.user_id.in_(submitter_ids))
    )
    employee_names: dict[uuid.UUID, str] = dict(employee_rows.all())

    missing_ids = submitter_ids - employee_names.keys()
    user_emails: dict[uuid.UUID, str] = {}
    if missing_ids:
        user_rows = await session.execute(select(User.id, User.email).where(User.id.in_(missing_ids)))
        user_emails = dict(user_rows.all())

    contexts: dict[uuid.UUID, dict] = {}
    for s in submissions:
        vctx = visit_context.get(s.visit_id, {})
        contexts[s.id] = {
            "employee_name": employee_names.get(s.submitted_by) or user_emails.get(s.submitted_by),
            "customer_name": vctx.get("customer_name"),
            "outlet_code": vctx.get("outlet_code"),
            "territory_name": vctx.get("territory_name"),
            "visit_scheduled_at": vctx.get("visit_scheduled_at"),
        }
    return contexts


@router.get("/form-submissions", response_model=list[SubmissionRead])
async def list_submissions(
    session: AsyncSession = Depends(get_async_session),
    current_user: CurrentUser = None,
    form_id: uuid.UUID | None = None,
    visit_id: uuid.UUID | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
):
    """P1-15: paginated (matching this codebase's existing skip/limit
    convention, e.g. GET /customers, GET /payments/queue) and batch-resolves
    per-row context instead of the previous one-round-trip-per-row N+1."""
    user_id = None if current_user.role == Role.ADMIN else current_user.id
    submissions = await form_template_service.list_submissions(
        session, form_id=form_id, visit_id=visit_id, user_id=user_id, skip=skip, limit=limit,
    )

    form_ids = {s.form_id for s in submissions}
    form_names: dict[uuid.UUID, str] = {}
    if form_ids:
        rows = await session.execute(select(FormTemplate.id, FormTemplate.name).where(FormTemplate.id.in_(form_ids)))
        form_names = dict(rows.all())

    contexts = await _resolve_submission_contexts_batch(submissions, session)

    result = []
    for s in submissions:
        context = contexts.get(s.id, {})
        read = SubmissionRead.model_validate(s)
        read.form_name = form_names.get(s.form_id)
        read.employee_name = context.get("employee_name")
        read.customer_name = context.get("customer_name")
        read.outlet_code = context.get("outlet_code")
        read.visit_scheduled_at = context.get("visit_scheduled_at")
        result.append(read)
    return result
