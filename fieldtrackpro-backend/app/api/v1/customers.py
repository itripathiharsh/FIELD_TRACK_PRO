"""
Customers router — /api/v1/customers
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.account import AccountSummary, HistoryPage
from app.schemas.customer import (
    CustomerCreate,
    CustomerMapLocation,
    CustomerProspectCreate,
    CustomerRead,
    CustomerUpdate,
)
from app.schemas.customer_prospect import (
    CustomerProspectRead,
    CustomerProspectRejectRequest,
    CustomerProspectSubmitResponse,
    CustomerProspectUpdate,
)
from app.models.customer_prospect import ProspectStatus
from app.schemas.customer_requirement import (
    CustomerRequirementCreate,
    CustomerRequirementRead,
)
from app.schemas.invoice import InvoiceRead
from app.schemas.location_proposal import (
    LocationProposalCreate,
    LocationProposalRead,
)
from app.schemas.media import OrderRead
from app.services import (
    account_service,
    customer_prospect_service,
    customer_requirement_service,
    customer_service,
    invoice_service,
    location_proposal_service,
    media_service,
    outlet_link_service,  # release 2.1.0: ledgers of the physical outlet
    outlet_proof_service,  # live outlet proof: additive CustomerRead fields
)

router = APIRouter(prefix="/customers", tags=["customers"])

DbSession = Annotated[AsyncSession, Depends(get_async_session)]
AdminOnly = Depends(require_role(Role.ADMIN))
AnyAuth = Depends(require_role(Role.ADMIN, Role.EMPLOYEE))


@router.post("", response_model=CustomerRead, status_code=201, dependencies=[AdminOnly])
async def create_customer(
    data: CustomerCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    customer = await customer_service.create_customer(data, current_user.id, session)
    return CustomerRead.from_model(customer)


@router.post("/prospect", response_model=CustomerProspectSubmitResponse, status_code=201, dependencies=[AnyAuth])
async def create_customer_prospect(
    data: CustomerProspectCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Field sales: submit a new outlet with brands, requirement, and GPS pin.

    An ADMIN caller still gets the outlet created immediately (unchanged). An
    EMPLOYEE caller's submission is held as a CustomerProspect for admin
    review instead - nothing is created yet; see POST /customers/prospects/{id}/approve.
    """
    if current_user.has_global_scope:
        customer = await customer_service.create_customer_prospect(data, current_user, session)
        return CustomerProspectSubmitResponse(
            status="CREATED",
            message="Outlet created.",
            customer=CustomerRead.from_model(customer),
        )

    prospect = await customer_prospect_service.submit_prospect(data, current_user, session)
    return CustomerProspectSubmitResponse(
        status="PENDING_APPROVAL",
        message="Submitted for admin approval. The outlet will appear once approved.",
        prospect_id=prospect.id,
    )


@router.get("/prospects", response_model=list[CustomerProspectRead], dependencies=[AnyAuth])
async def list_customer_prospects(
    current_user: CurrentUser,
    session: DbSession,
    status: ProspectStatus | None = Query(default=None),
):
    """ADMIN sees every submission; EMPLOYEE sees only their own."""
    prospects = await customer_prospect_service.list_prospects(session, current_user, status)
    reads = [CustomerProspectRead.from_model(p) for p in prospects]
    return await outlet_proof_service.attach_outlet_proofs(session, reads)


@router.get("/prospects/{prospect_id}", response_model=CustomerProspectRead, dependencies=[AnyAuth])
async def get_customer_prospect(
    prospect_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    prospect = await customer_prospect_service.get_prospect(prospect_id, current_user, session)
    read = CustomerProspectRead.from_model(prospect)
    await outlet_proof_service.attach_outlet_proofs(session, [read])
    return read


@router.patch("/prospects/{prospect_id}", response_model=CustomerProspectRead, dependencies=[AdminOnly])
async def update_customer_prospect(
    prospect_id: uuid.UUID,
    data: CustomerProspectUpdate,
    session: DbSession,
):
    """Admin can correct fields (typo, outlet code) on a PENDING submission before approving."""
    prospect = await customer_prospect_service.update_prospect(prospect_id, data, session)
    return CustomerProspectRead.from_model(prospect)


@router.post("/prospects/{prospect_id}/approve", response_model=CustomerRead, dependencies=[AdminOnly])
async def approve_customer_prospect(
    prospect_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    customer = await customer_prospect_service.approve_prospect(prospect_id, current_user, session)
    read = CustomerRead.from_model(customer)
    await outlet_proof_service.enrich_customer_reads(session, [read])
    return read


@router.post("/prospects/{prospect_id}/reject", response_model=CustomerProspectRead, dependencies=[AdminOnly])
async def reject_customer_prospect(
    prospect_id: uuid.UUID,
    data: CustomerProspectRejectRequest,
    current_user: CurrentUser,
    session: DbSession,
):
    prospect = await customer_prospect_service.reject_prospect(prospect_id, data.reason, current_user, session)
    return CustomerProspectRead.from_model(prospect)


@router.post("/{customer_id}/mark-tally-entry-done", response_model=CustomerRead, dependencies=[AdminOnly])
async def mark_customer_tally_entry_done(
    customer_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    """Admin confirms they've manually added this approved outlet to TallyPrime."""
    customer = await customer_prospect_service.mark_tally_entry_done(customer_id, current_user, session)
    read = CustomerRead.from_model(customer)
    await outlet_proof_service.enrich_customer_reads(session, [read])
    return read


@router.get("", response_model=list[CustomerRead], dependencies=[AnyAuth])
async def list_customers(
    response: Response,
    current_user: CurrentUser,
    session: DbSession,
    search: str | None = Query(default=None, description="Search by name, outlet/DMS code, address, or contact"),
    territory_id: uuid.UUID | None = Query(default=None),
    area_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=5000),
    include_merged: bool = Query(default=False, description="Admin only: also list customers merged into an outlet"),
):
    """
    An ADMIN sees the full outlet directory. An EMPLOYEE sees only outlets in
    their scope (assigned, on one of their visits, or in an Area they cover).
    The one exception is the off-beat / ad-hoc visit picker: a `search` of 3+
    characters also matches other outlets, returned REDACTED (no contact,
    GST, brands or staff). An unlinked employee account gets an empty list.
    Returns X-Total-Count header for scalable server-side pagination.
    """
    customers, total_count, in_scope = await customer_service.list_customers(
        session, current_user, territory_id, skip, limit, area_id, search,
        include_merged=include_merged and current_user.has_global_scope,
    )
    response.headers["X-Total-Count"] = str(total_count)
    out = []
    for c in customers:
        read = CustomerRead.from_model(c)
        if in_scope is not None and c.id not in in_scope:
            # Ad-hoc / off-beat directory search hit: id, name, code, address,
            # coordinates only. No contact numbers, tax ids, brands or staff.
            read = customer_service.redact_customer_read(read)
        out.append(read)
    # Live outlet proof summary fields, only for outlets the caller may fully see.
    await outlet_proof_service.enrich_customer_reads(
        session, [r for r in out if in_scope is None or r.id in in_scope]
    )
    await outlet_link_service.enrich_ledger_summary(session, [r for r in out if in_scope is None or r.id in in_scope])
    return out


@router.get("/map-locations", response_model=list[CustomerMapLocation], dependencies=[AnyAuth])
async def list_customer_map_locations(
    session: DbSession,
    current_user: CurrentUser,
    territory_id: uuid.UUID | None = Query(default=None),
    area_id: uuid.UUID | None = Query(default=None),
):
    """
    Dedicated lightweight geo-coordinates endpoint for maps (WEB-CUST-002).
    Returns coordinates, radius, and status for customer map markers
    (ADMIN: all; EMPLOYEE: only outlets in their scope).
    """
    customers = await customer_service.list_customer_map_locations(
        session, territory_id, area_id, current_user
    )
    out = []
    for c in customers:
        lat, lng = customer_service.extract_coords(c.location)
        out.append(
            CustomerMapLocation(
                id=c.id,
                name=c.name,
                outlet_code=c.outlet_code,
                address=c.address,
                contact_person=c.contact_person,
                contact_number=c.contact_number,
                latitude=lat,
                longitude=lng,
                geofence_radius_m=c.geofence_radius_m or 75,
                location_status=getattr(c, "location_status", "VERIFIED") or "VERIFIED",
                territory_id=c.territory_id,
                area_id=c.area_id,
            )
        )
    return out


@router.get("/{customer_id}", response_model=CustomerRead, dependencies=[AnyAuth])
async def get_customer(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """
    An EMPLOYEE may only view an outlet in their scope (assigned / on their
    visits / in a covered Area) - the same rule as account/invoices/orders.
    """
    await customer_service.assert_employee_can_view_customer(customer_id, current_user, session)
    customer = await customer_service.get_customer(customer_id, session)
    read = CustomerRead.from_model(customer)
    await outlet_proof_service.enrich_customer_reads(session, [read])
    await outlet_link_service.enrich_ledger_summary(session, [read], with_ledgers=True)
    return read


@router.patch("/{customer_id}", response_model=CustomerRead, dependencies=[AdminOnly])
async def update_customer(
    customer_id: uuid.UUID, data: CustomerUpdate, session: DbSession
):
    customer = await customer_service.update_customer(customer_id, data, session)
    read = CustomerRead.from_model(customer)
    await outlet_proof_service.enrich_customer_reads(session, [read])
    return read


@router.get("/{customer_id}/account", response_model=AccountSummary, dependencies=[AnyAuth])
async def get_customer_account(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """
    Outlet Account panel: outstanding/due/overdue, days outstanding,
    collection status, recent invoices/payments, brand-wise totals.

    An EMPLOYEE may only view this for an outlet they have a visit assigned
    to (see account_service.assert_employee_can_view_account) - an ADMIN can
    view any outlet's account.
    """
    return await account_service.get_account_summary(customer_id, current_user, session)


@router.get("/{customer_id}/history", response_model=HistoryPage, dependencies=[AnyAuth])
async def get_customer_history(
    customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession,
    limit: int = Query(default=200, ge=1, le=1000), offset: int = Query(default=0, ge=0),
):
    """Full Tally account history of the physical outlet across all its ledgers (release 2.1.0)."""
    return await account_service.get_account_history(customer_id, current_user, session, limit, offset)


@router.get("/{customer_id}/invoices", response_model=list[InvoiceRead], dependencies=[AnyAuth])
async def list_customer_invoices(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """Full invoice history for an outlet, each annotated with real calculated aging."""
    await account_service.assert_employee_can_view_account(customer_id, current_user, session)
    invoices = await invoice_service.list_invoices_for_customer(customer_id, session)
    return [await invoice_service.to_invoice_read(inv, session) for inv in invoices]


@router.get("/{customer_id}/orders", response_model=list[OrderRead], dependencies=[AnyAuth])
async def list_customer_orders(customer_id: uuid.UUID, current_user: CurrentUser, session: DbSession):
    """Every order captured on this outlet, across its full visit history (P2-B)."""
    return await media_service.list_customer_orders(customer_id, current_user, session)


@router.post("/{customer_id}/location-proposals", response_model=LocationProposalRead, status_code=201, dependencies=[AnyAuth])
async def propose_customer_location(
    customer_id: uuid.UUID,
    data: LocationProposalCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Employee / Admin: Propose corrected GPS coordinates for an existing customer.
    Creates a pending location proposal without altering official coordinates until approved.
    """
    await customer_service.assert_employee_can_view_customer(customer_id, current_user, session)
    return await location_proposal_service.create_location_proposal(
        customer_id=customer_id,
        data=data,
        current_user=current_user,
        session=session,
    )


@router.get("/{customer_id}/location-proposals", response_model=list[LocationProposalRead], dependencies=[AnyAuth])
async def list_customer_location_proposals(
    customer_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    List location proposals for a customer. ADMIN: full audit trail.
    EMPLOYEE: only the proposals they submitted, and only for outlets in their scope.
    """
    await customer_service.assert_employee_can_view_customer(customer_id, current_user, session)
    return await location_proposal_service.list_location_proposals(
        session=session,
        status="ALL",
        customer_id=customer_id,
        submitted_by=current_user.id if not current_user.has_global_scope else None,
    )


@router.get("/{customer_id}/requirements", response_model=list[CustomerRequirementRead], dependencies=[AnyAuth])
async def list_customer_requirements(
    customer_id: uuid.UUID,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    List requirements for a customer. ADMIN: all. EMPLOYEE: only those they
    created, and only for outlets in their scope.
    """
    await customer_service.assert_employee_can_view_customer(customer_id, current_user, session)
    return await customer_requirement_service.list_requirements_for_customer(
        customer_id=customer_id,
        session=session,
        created_by=current_user.id if not current_user.has_global_scope else None,
    )


@router.post("/{customer_id}/requirements", response_model=CustomerRequirementRead, status_code=201, dependencies=[AnyAuth])
async def create_customer_requirement(
    customer_id: uuid.UUID,
    data: CustomerRequirementCreate,
    current_user: CurrentUser,
    session: DbSession,
):
    """
    Add a business opportunity / requirement for a customer.
    """
    return await customer_requirement_service.create_requirement(
        customer_id=customer_id,
        data=data,
        current_user=current_user,
        session=session,
    )
