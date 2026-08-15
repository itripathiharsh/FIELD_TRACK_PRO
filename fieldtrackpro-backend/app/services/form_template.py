"""
Form Template Builder service — business logic for templates, sections,
questions, submissions, and answers.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions.custom import BaseAPIException
from app.models.form_template import (
    FormAnswer,
    FormQuestion,
    FormQuestionOption,
    FormSection,
    FormStatus,
    FormSubmission,
    FormTemplate,
    FormTemplateVersion,
    QuestionType,
    SubmissionStatus,
)

logger = logging.getLogger("fieldtrackpro")


def _serialize_snapshot(template: FormTemplate) -> dict[str, Any]:
    """Plain-JSON snapshot of a template's full section/question/option tree."""
    return {
        "id": str(template.id),
        "name": template.name,
        "description": template.description,
        "version": template.version,
        "sections": [
            {
                "id": str(section.id),
                "title": section.title,
                "description": section.description,
                "display_order": section.display_order,
                "questions": [
                    {
                        "id": str(question.id),
                        "question_text": question.question_text,
                        "help_text": question.help_text,
                        "question_type": question.question_type.value,
                        "required": question.required,
                        "display_order": question.display_order,
                        "placeholder": question.placeholder,
                        "validation_config": question.validation_config,
                        "options": [
                            {
                                "id": str(option.id),
                                "label": option.label,
                                "value": option.value,
                                "display_order": option.display_order,
                            }
                            for option in question.options
                        ],
                    }
                    for question in section.questions
                ],
            }
            for section in template.sections
        ],
    }


class FormTemplateService:
    """Service managing form templates, sections, questions, and submissions."""

    # -- Template CRUD ------------------------------------------------------

    @staticmethod
    async def create_template(
        session: AsyncSession,
        name: str,
        created_by: uuid.UUID,
        description: str | None = None,
        category_id: uuid.UUID | None = None,
    ) -> FormTemplate:
        template = FormTemplate(
            name=name,
            description=description,
            category_id=category_id,
            created_by=created_by,
            status=FormStatus.DRAFT,
            version=1,
        )
        session.add(template)
        await session.commit()
        # get_template (not a bare refresh) eager-loads sections/category, so
        # the caller can safely read those relationships afterward. A plain
        # refresh() only reloads column attributes for a never-before-loaded
        # relationship - a later `template.sections` access would otherwise
        # trigger a classic lazy-load, which crashes under an async driver
        # with "MissingGreenlet: greenlet_spawn has not been called".
        return await FormTemplateService.get_template(session, template.id)

    @staticmethod
    async def get_template(session: AsyncSession, template_id: uuid.UUID) -> FormTemplate:
        result = await session.execute(
            select(FormTemplate)
            .where(FormTemplate.id == template_id)
            .options(
                selectinload(FormTemplate.sections).selectinload(FormSection.questions).selectinload(FormQuestion.options),
                selectinload(FormTemplate.category),
            )
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise BaseAPIException(status_code=404, detail="Form template not found", error_code="FORM_NOT_FOUND")
        return template

    @staticmethod
    async def list_templates(
        session: AsyncSession,
        status: FormStatus | None = None,
        category_id: uuid.UUID | None = None,
    ) -> Sequence[FormTemplate]:
        query = (
            select(FormTemplate)
            .options(selectinload(FormTemplate.category))
            .order_by(FormTemplate.updated_at.desc())
        )
        if status is not None:
            query = query.where(FormTemplate.status == status)
        if category_id is not None:
            query = query.where(FormTemplate.category_id == category_id)
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def update_template(
        session: AsyncSession,
        template_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        category_id: uuid.UUID | None = None,
    ) -> FormTemplate:
        template = await FormTemplateService.get_template(session, template_id)
        if template.status == FormStatus.ARCHIVED:
            raise BaseAPIException(status_code=400, detail="Cannot edit an archived form", error_code="FORM_ARCHIVED")
        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if category_id is not None:
            template.category_id = category_id
        await session.commit()
        await session.refresh(template)
        return template

    @staticmethod
    async def delete_template(session: AsyncSession, template_id: uuid.UUID) -> None:
        template = await FormTemplateService.get_template(session, template_id)
        # `template.submissions` is a plain lazy relationship - get_template's
        # eager-load options don't cover it, and a bare attribute access here
        # would hit the async lazy-load trap (MissingGreenlet). This path had
        # no test coverage until the visit-required-form work added one and
        # caught it; use an explicit count instead, same as the visit check
        # right below.
        submission_count = await session.scalar(
            select(func.count()).select_from(FormSubmission).where(FormSubmission.form_id == template_id)
        )
        if submission_count:
            raise BaseAPIException(
                status_code=409,
                detail="Cannot delete a form that has submissions",
                error_code="FORM_HAS_SUBMISSIONS",
            )
        from app.models.visit import Visit

        visit_count = await session.scalar(
            select(func.count()).select_from(Visit).where(Visit.required_form_id == template_id)
        )
        if visit_count:
            raise BaseAPIException(
                status_code=409,
                detail="Cannot delete a form that is required by one or more visits",
                error_code="FORM_REQUIRED_BY_VISITS",
            )
        await session.delete(template)
        await session.commit()

    @staticmethod
    async def publish_template(session: AsyncSession, template_id: uuid.UUID, published_by: uuid.UUID) -> FormTemplate:
        """
        Publish the current DRAFT structure.

        A version is only ever snapshotted once: if `template.version` has no
        snapshot yet, this is that version's first publish and the version
        number does not change. If a snapshot already exists for the current
        version (i.e. this form was published before, then unpublished and
        edited), publishing again is a genuine new version - bump first, then
        snapshot. Submissions already recorded against the prior version keep
        pointing at that version's immutable snapshot and are never affected.
        """
        template = await FormTemplateService.get_template(session, template_id)
        if template.status == FormStatus.ARCHIVED:
            raise BaseAPIException(status_code=400, detail="Cannot publish an archived form", error_code="FORM_ARCHIVED")
        if not template.sections:
            raise BaseAPIException(status_code=400, detail="Cannot publish a form without sections", error_code="FORM_EMPTY")

        existing_snapshot = await session.execute(
            select(FormTemplateVersion).where(
                FormTemplateVersion.form_id == template.id,
                FormTemplateVersion.version == template.version,
            )
        )
        if existing_snapshot.scalar_one_or_none() is not None:
            template.version += 1

        session.add(FormTemplateVersion(
            form_id=template.id,
            version=template.version,
            snapshot=_serialize_snapshot(template),
            published_by=published_by,
        ))
        template.status = FormStatus.PUBLISHED
        template.published_at = datetime.now(tz=timezone.utc)
        await session.commit()
        await session.refresh(template)
        return template

    @staticmethod
    async def unpublish_template(session: AsyncSession, template_id: uuid.UUID) -> FormTemplate:
        """
        Move a PUBLISHED form back to DRAFT so its structure can be edited.
        The already-taken version snapshot is untouched, so every submission
        recorded against the current version keeps its exact structure
        regardless of what happens next.
        """
        template = await FormTemplateService.get_template(session, template_id)
        if template.status != FormStatus.PUBLISHED:
            raise BaseAPIException(status_code=400, detail="Only a published form can be unpublished", error_code="FORM_NOT_PUBLISHED")
        template.status = FormStatus.DRAFT
        await session.commit()
        await session.refresh(template)
        return template

    @staticmethod
    async def archive_template(session: AsyncSession, template_id: uuid.UUID) -> FormTemplate:
        template = await FormTemplateService.get_template(session, template_id)
        template.status = FormStatus.ARCHIVED
        template.archived_at = datetime.now(tz=timezone.utc)
        await session.commit()
        await session.refresh(template)
        return template

    @staticmethod
    async def duplicate_template(session: AsyncSession, template_id: uuid.UUID, created_by: uuid.UUID) -> FormTemplate:
        source = await FormTemplateService.get_template(session, template_id)
        new_template = FormTemplate(
            name=f"{source.name} (Copy)",
            description=source.description,
            category_id=source.category_id,
            created_by=created_by,
            status=FormStatus.DRAFT,
            version=1,
        )
        session.add(new_template)
        await session.flush()

        for section in source.sections:
            new_section = FormSection(
                id=uuid.uuid4(),
                form_id=new_template.id,
                title=section.title,
                description=section.description,
                display_order=section.display_order,
            )
            session.add(new_section)
            await session.flush()

            for question in section.questions:
                new_question = FormQuestion(
                    id=uuid.uuid4(),
                    section_id=new_section.id,
                    form_id=new_template.id,
                    question_text=question.question_text,
                    help_text=question.help_text,
                    question_type=question.question_type,
                    required=question.required,
                    display_order=question.display_order,
                    placeholder=question.placeholder,
                    validation_config=question.validation_config,
                )
                session.add(new_question)
                await session.flush()

                for option in question.options:
                    new_option = FormQuestionOption(
                        id=uuid.uuid4(),
                        question_id=new_question.id,
                        label=option.label,
                        value=option.value,
                        display_order=option.display_order,
                    )
                    session.add(new_option)

        await session.commit()
        # See create_template: eager-load via get_template, not a bare
        # refresh(), so the never-before-loaded sections/category
        # relationships are safe for the route to read.
        return await FormTemplateService.get_template(session, new_template.id)

    # -- Section CRUD -------------------------------------------------------

    @staticmethod
    async def add_section(
        session: AsyncSession,
        template_id: uuid.UUID,
        title: str,
        description: str | None = None,
        display_order: int = 0,
    ) -> FormSection:
        template = await FormTemplateService.get_template(session, template_id)
        if template.status != FormStatus.DRAFT:
            raise BaseAPIException(status_code=400, detail="Can only add sections to DRAFT forms", error_code="FORM_NOT_DRAFT")
        section = FormSection(
            form_id=template_id,
            title=title,
            description=description,
            display_order=display_order,
        )
        session.add(section)
        await session.commit()
        # SectionRead.questions must be loaded before Pydantic serializes it -
        # a bare refresh() leaves a never-loaded relationship as a classic
        # (sync) lazy-load trap under the async driver (MissingGreenlet).
        await session.refresh(section, attribute_names=["questions"])
        return section

    @staticmethod
    async def _require_draft_template(session: AsyncSession, form_id: uuid.UUID) -> None:
        result = await session.execute(select(FormTemplate.status).where(FormTemplate.id == form_id))
        status = result.scalar_one_or_none()
        if status is not None and status != FormStatus.DRAFT:
            raise BaseAPIException(status_code=400, detail="Can only modify structure on DRAFT forms", error_code="FORM_NOT_DRAFT")

    @staticmethod
    async def update_section(
        session: AsyncSession,
        section_id: uuid.UUID,
        title: str | None = None,
        description: str | None = None,
        display_order: int | None = None,
    ) -> FormSection:
        result = await session.execute(
            select(FormSection).where(FormSection.id == section_id).options(selectinload(FormSection.questions))
        )
        section = result.scalar_one_or_none()
        if section is None:
            raise BaseAPIException(status_code=404, detail="Section not found", error_code="SECTION_NOT_FOUND")
        await FormTemplateService._require_draft_template(session, section.form_id)
        if title is not None:
            section.title = title
        if description is not None:
            section.description = description
        if display_order is not None:
            section.display_order = display_order
        await session.commit()
        # `questions` was already eager-loaded above, so an UNRESTRICTED
        # refresh() correctly reloads it alongside the mutated columns.
        # Restricting to attribute_names=[...] here would leave `updated_at`
        # (onupdate=func.now(), not returned by UPDATE) expired, and a later
        # access would hit the same MissingGreenlet lazy-load trap.
        await session.refresh(section)
        return section

    @staticmethod
    async def delete_section(session: AsyncSession, section_id: uuid.UUID) -> None:
        result = await session.execute(select(FormSection).where(FormSection.id == section_id))
        section = result.scalar_one_or_none()
        if section is None:
            raise BaseAPIException(status_code=404, detail="Section not found", error_code="SECTION_NOT_FOUND")
        await FormTemplateService._require_draft_template(session, section.form_id)
        answer_count = await session.execute(
            select(func.count(FormAnswer.id))
            .join(FormQuestion, FormAnswer.question_id == FormQuestion.id)
            .where(FormQuestion.section_id == section_id)
        )
        if answer_count.scalar_one() > 0:
            raise BaseAPIException(
                status_code=409,
                detail="Cannot delete a section whose questions already have recorded answers.",
                error_code="SECTION_HAS_ANSWERS",
            )
        await session.delete(section)
        await session.commit()

    # -- Question CRUD ------------------------------------------------------

    @staticmethod
    async def add_question(
        session: AsyncSession,
        template_id: uuid.UUID,
        section_id: uuid.UUID,
        question_text: str,
        question_type: QuestionType,
        required: bool = False,
        help_text: str | None = None,
        placeholder: str | None = None,
        display_order: int = 0,
        validation_config: dict[str, Any] | None = None,
        options: list[dict[str, Any]] | None = None,
    ) -> FormQuestion:
        template = await FormTemplateService.get_template(session, template_id)
        if template.status != FormStatus.DRAFT:
            raise BaseAPIException(status_code=400, detail="Can only add questions to DRAFT forms", error_code="FORM_NOT_DRAFT")

        question = FormQuestion(
            section_id=section_id,
            form_id=template_id,
            question_text=question_text,
            help_text=help_text,
            question_type=question_type,
            required=required,
            display_order=display_order,
            placeholder=placeholder,
            validation_config=validation_config,
        )
        session.add(question)
        await session.flush()

        if options:
            for idx, opt in enumerate(options):
                option = FormQuestionOption(
                    question_id=question.id,
                    label=opt["label"],
                    value=opt.get("value", opt["label"]),
                    display_order=opt.get("display_order", idx),
                )
                session.add(option)

        await session.commit()
        await session.refresh(question, attribute_names=["options"])
        return question

    @staticmethod
    async def update_question(
        session: AsyncSession,
        question_id: uuid.UUID,
        **kwargs: Any,
    ) -> FormQuestion:
        result = await session.execute(
            select(FormQuestion)
            .where(FormQuestion.id == question_id)
            .options(selectinload(FormQuestion.options))
        )
        question = result.scalar_one_or_none()
        if question is None:
            raise BaseAPIException(status_code=404, detail="Question not found", error_code="QUESTION_NOT_FOUND")
        await FormTemplateService._require_draft_template(session, question.form_id)

        simple_fields = ("section_id", "question_text", "help_text", "question_type", "required", "display_order", "placeholder", "validation_config")
        for field in simple_fields:
            if field in kwargs and kwargs[field] is not None:
                setattr(question, field, kwargs[field])

        # Handle options replacement
        if "options" in kwargs and kwargs["options"] is not None:
            for opt in question.options:
                await session.delete(opt)
            await session.flush()
            for idx, opt in enumerate(kwargs["options"]):
                option = FormQuestionOption(
                    question_id=question.id,
                    label=opt["label"],
                    value=opt.get("value", opt["label"]),
                    display_order=opt.get("display_order", idx),
                )
                session.add(option)

        await session.commit()
        # `options` was already eager-loaded by the selectinload above, so an
        # unrestricted refresh() reloads it correctly alongside `updated_at`
        # (see update_section for why attribute_names=[...] is wrong here).
        await session.refresh(question)
        return question

    @staticmethod
    async def delete_question(session: AsyncSession, question_id: uuid.UUID) -> None:
        result = await session.execute(select(FormQuestion).where(FormQuestion.id == question_id))
        question = result.scalar_one_or_none()
        if question is None:
            raise BaseAPIException(status_code=404, detail="Question not found", error_code="QUESTION_NOT_FOUND")
        await FormTemplateService._require_draft_template(session, question.form_id)
        # form_answers.question_id is ON DELETE RESTRICT by design - an answer
        # already recorded against this question must never be silently
        # orphaned or cascaded away. Surface that as a clear 409, not a raw
        # IntegrityError/500.
        answer_count = await session.execute(select(func.count(FormAnswer.id)).where(FormAnswer.question_id == question_id))
        if answer_count.scalar_one() > 0:
            raise BaseAPIException(
                status_code=409,
                detail="Cannot delete a question that already has recorded answers. Unpublish and duplicate the form instead if you need a clean slate.",
                error_code="QUESTION_HAS_ANSWERS",
            )
        await session.delete(question)
        await session.commit()

    @staticmethod
    async def duplicate_question(session: AsyncSession, question_id: uuid.UUID) -> FormQuestion:
        result = await session.execute(
            select(FormQuestion)
            .where(FormQuestion.id == question_id)
            .options(selectinload(FormQuestion.options))
        )
        source = result.scalar_one_or_none()
        if source is None:
            raise BaseAPIException(status_code=404, detail="Question not found", error_code="QUESTION_NOT_FOUND")
        await FormTemplateService._require_draft_template(session, source.form_id)

        siblings = await session.execute(
            select(func.max(FormQuestion.display_order)).where(FormQuestion.section_id == source.section_id)
        )
        next_order = (siblings.scalar_one() or 0) + 1

        copy = FormQuestion(
            section_id=source.section_id,
            form_id=source.form_id,
            question_text=source.question_text,
            help_text=source.help_text,
            question_type=source.question_type,
            required=source.required,
            display_order=next_order,
            placeholder=source.placeholder,
            validation_config=source.validation_config,
        )
        session.add(copy)
        await session.flush()

        for option in source.options:
            session.add(FormQuestionOption(
                question_id=copy.id,
                label=option.label,
                value=option.value,
                display_order=option.display_order,
            ))

        await session.commit()
        await session.refresh(copy, attribute_names=["options"])
        return copy

    # -- Option CRUD --------------------------------------------------------

    @staticmethod
    async def add_option(
        session: AsyncSession,
        question_id: uuid.UUID,
        label: str,
        value: str | None = None,
        display_order: int = 0,
    ) -> FormQuestionOption:
        question_result = await session.execute(select(FormQuestion).where(FormQuestion.id == question_id))
        question = question_result.scalar_one_or_none()
        if question is None:
            raise BaseAPIException(status_code=404, detail="Question not found", error_code="QUESTION_NOT_FOUND")
        await FormTemplateService._require_draft_template(session, question.form_id)
        option = FormQuestionOption(
            question_id=question_id,
            label=label,
            value=value or label,
            display_order=display_order,
        )
        session.add(option)
        await session.commit()
        await session.refresh(option)
        return option

    @staticmethod
    async def update_option(
        session: AsyncSession,
        option_id: uuid.UUID,
        label: str | None = None,
        value: str | None = None,
        display_order: int | None = None,
    ) -> FormQuestionOption:
        result = await session.execute(
            select(FormQuestionOption)
            .where(FormQuestionOption.id == option_id)
            .options(selectinload(FormQuestionOption.question))
        )
        option = result.scalar_one_or_none()
        if option is None:
            raise BaseAPIException(status_code=404, detail="Option not found", error_code="OPTION_NOT_FOUND")
        await FormTemplateService._require_draft_template(session, option.question.form_id)
        if label is not None:
            option.label = label
        if value is not None:
            option.value = value
        if display_order is not None:
            option.display_order = display_order
        await session.commit()
        await session.refresh(option)
        return option

    @staticmethod
    async def delete_option(session: AsyncSession, option_id: uuid.UUID) -> None:
        result = await session.execute(
            select(FormQuestionOption)
            .where(FormQuestionOption.id == option_id)
            .options(selectinload(FormQuestionOption.question))
        )
        option = result.scalar_one_or_none()
        if option is None:
            raise BaseAPIException(status_code=404, detail="Option not found", error_code="OPTION_NOT_FOUND")
        await FormTemplateService._require_draft_template(session, option.question.form_id)
        await session.delete(option)
        await session.commit()

    # -- Submission ---------------------------------------------------------

    @staticmethod
    def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
        """
        Answer payloads reach this service two ways: from the API route,
        where `data.answers` is already `list[AnswerSubmit]` and
        `.model_dump()` keeps `question_id` as a real `uuid.UUID`; and from
        direct/test callers that pass plain dicts with a string id.
        `uuid.UUID(uuid.UUID(...))` raises, so both shapes must be handled.
        """
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)

    @staticmethod
    def _require_all_questions_answered(template: FormTemplate, answered_qids: set[uuid.UUID]) -> None:
        """
        Shared submit-time gate (P2-2): every required question on the
        template must have an answer. Used by both the unreachable
        submit=True branch of create_or_update_submission and by
        finalize_submission, the actual enforcement point - previously each
        reimplemented the same required-qid/missing-set logic independently.
        """
        required_qids = {q.id for section in template.sections for q in section.questions if q.required}
        missing = required_qids - answered_qids
        if missing:
            raise BaseAPIException(
                status_code=422,
                detail=f"Required questions not answered: {len(missing)}",
                error_code="REQUIRED_ANSWERS_MISSING",
            )

    @staticmethod
    async def create_or_update_submission(
        session: AsyncSession,
        form_id: uuid.UUID,
        visit_id: uuid.UUID,
        user_id: uuid.UUID,
        answers: list[dict[str, Any]],
        submit: bool = False,
        is_admin: bool = False,
    ) -> FormSubmission:
        template = await FormTemplateService.get_template(session, form_id)
        if template.status != FormStatus.PUBLISHED:
            if submit:
                # Unchanged pre-existing rule: finalizing a submission always
                # requires PUBLISHED, for every role (see finalize_submission,
                # the only route that actually reaches this with submit=True).
                raise BaseAPIException(status_code=400, detail="Form is not published", error_code="FORM_NOT_PUBLISHED")
            if not is_admin:
                # P1-1: an EMPLOYEE must not be able to create/update a draft
                # submission against a DRAFT/ARCHIVED template just by
                # knowing/guessing its form_id - closes the IDOR-adjacent gap
                # where this check previously only fired for submit=True.
                # ADMIN keeps the ability to test-fill a non-published form,
                # matching the existing /render preview allowance.
                raise BaseAPIException(status_code=400, detail="Form is not published", error_code="FORM_NOT_PUBLISHED")

        # Find existing draft submission for this visit+form+user
        result = await session.execute(
            select(FormSubmission).where(
                FormSubmission.form_id == form_id,
                FormSubmission.visit_id == visit_id,
                FormSubmission.submitted_by == user_id,
            )
        )
        submission = result.scalar_one_or_none()

        if submission is None:
            submission = FormSubmission(
                form_id=form_id,
                form_version=template.version,
                visit_id=visit_id,
                submitted_by=user_id,
                status=SubmissionStatus.DRAFT,
            )
            session.add(submission)
            await session.flush()
        elif submission.status == SubmissionStatus.SUBMITTED:
            raise BaseAPIException(status_code=409, detail="Submission already completed", error_code="SUBMISSION_COMPLETE")

        # Validate required questions if submitting
        if submit:
            answered_qids = {FormTemplateService._as_uuid(a["question_id"]) for a in answers if a.get("answer_value")}
            FormTemplateService._require_all_questions_answered(template, answered_qids)

        # Upsert answers
        for ans in answers:
            qid = FormTemplateService._as_uuid(ans["question_id"])
            existing_result = await session.execute(
                select(FormAnswer).where(
                    FormAnswer.submission_id == submission.id,
                    FormAnswer.question_id == qid,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                existing.answer_value = ans.get("answer_value")
            else:
                session.add(FormAnswer(
                    submission_id=submission.id,
                    question_id=qid,
                    answer_value=ans.get("answer_value"),
                ))

        if submit:
            submission.status = SubmissionStatus.SUBMITTED
            submission.submitted_at = datetime.now(tz=timezone.utc)

        await session.commit()
        await session.refresh(submission, attribute_names=["answers"])
        return submission

    @staticmethod
    async def finalize_submission(session: AsyncSession, submission_id: uuid.UUID) -> FormSubmission:
        """
        The real submit-time gate. `POST /form-submissions/{id}/submit` is the
        only reachable way a submission ever becomes SUBMITTED (no route ever
        passes `submit=True` into create_or_update_submission), so the
        "form must be published" / "required questions answered" rules have
        to live here, not just in the unreachable branch above.
        """
        submission = await FormTemplateService.get_submission(session, submission_id)
        if submission.status == SubmissionStatus.SUBMITTED:
            raise BaseAPIException(status_code=409, detail="Already submitted", error_code="ALREADY_SUBMITTED")

        template = await FormTemplateService.get_template(session, submission.form_id)
        if template.status != FormStatus.PUBLISHED:
            raise BaseAPIException(status_code=400, detail="Form is not published", error_code="FORM_NOT_PUBLISHED")

        answered_qids = {a.question_id for a in submission.answers if a.answer_value}
        FormTemplateService._require_all_questions_answered(template, answered_qids)

        submission.status = SubmissionStatus.SUBMITTED
        submission.submitted_at = datetime.now(tz=timezone.utc)
        await session.commit()
        await session.refresh(submission)
        return submission

    @staticmethod
    async def get_version_snapshot(
        session: AsyncSession, form_id: uuid.UUID, version: int,
    ) -> dict[str, Any] | None:
        """
        The immutable structure a submission was actually answered against.
        Returns None only for a submission recorded before any version of its
        form was ever published (e.g. a DRAFT save against an unpublished
        form) - callers fall back to the live template in that case.
        """
        result = await session.execute(
            select(FormTemplateVersion.snapshot).where(
                FormTemplateVersion.form_id == form_id,
                FormTemplateVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_submission(session: AsyncSession, submission_id: uuid.UUID) -> FormSubmission:
        result = await session.execute(
            select(FormSubmission)
            .where(FormSubmission.id == submission_id)
            .options(selectinload(FormSubmission.answers))
        )
        submission = result.scalar_one_or_none()
        if submission is None:
            raise BaseAPIException(status_code=404, detail="Submission not found", error_code="SUBMISSION_NOT_FOUND")
        return submission

    @staticmethod
    async def list_submissions(
        session: AsyncSession,
        form_id: uuid.UUID | None = None,
        visit_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[FormSubmission]:
        query = select(FormSubmission).options(selectinload(FormSubmission.answers))
        if form_id:
            query = query.where(FormSubmission.form_id == form_id)
        if visit_id:
            query = query.where(FormSubmission.visit_id == visit_id)
        if user_id:
            query = query.where(FormSubmission.submitted_by == user_id)
        query = query.order_by(FormSubmission.created_at.desc()).offset(skip).limit(limit)
        result = await session.execute(query)
        return result.scalars().all()


form_template_service = FormTemplateService()
