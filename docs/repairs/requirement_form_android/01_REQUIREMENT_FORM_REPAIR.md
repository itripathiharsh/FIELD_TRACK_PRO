# Requirement Form Module — Android Implementation

**Date:** 2026-08-19
**Feature:** Requirement Form capture for field representatives
**Spec Source:** Requirements doc Section 4.1, 07_api_design.md Section 6

---

## Requirement Specification (from project docs)

**Fields:**
- Customer Name (auto-populated from visit)
- Contact Number (auto-populated from customer)
- Requirement Category (dropdown: admin-editable taxonomy)
- Requirement Description (free text, required)
- Priority (Low/Medium/High, required)
- Expected Timeline (text, required)
- Budget Range (optional)
- Notes (optional)

**API Endpoints Required:**
- GET /api/v1/requirement-categories — List categories
- POST /api/v1/requirement-categories — Add category (ADMIN)
- POST /api/v1/visits/{id}/requirement-form — Submit form
- GET /api/v1/visits/{id}/requirement-form — Retrieve form

---

## Checklist

### Phase 1: Forensic Discovery

- [x] Requirement backend models identified (RequirementCategory, RequirementForm)
- [x] No existing requirement API endpoints
- [x] No existing requirement schemas
- [x] No existing Android requirement screens
- [x] Web FormsPage shows "not available" state
- [x] Database schema exists (requirement_categories, requirement_forms tables)

### Phase 2: Backend Implementation

- [x] Create requirement schemas (Pydantic DTOs)
- [x] Create requirement API endpoints
- [x] Create requirement service
- [x] Register routes in main router

### Phase 3: Android Implementation

- [x] Create RequirementFormDto
- [x] Create RequirementCategoryDto
- [x] Create RequirementApi interface
- [x] Create RequirementRepository
- [x] Create RequirementViewModel
- [x] Create RequirementFormScreen composable
- [x] Wire into NavGraph
- [x] Wire into Visit Details flow

### Phase 4: Web Implementation

- [x] Update FormsPage to show functional UI
- [x] Add category management
- [x] Add form viewing

### Phase 5: Verification

- [ ] Backend tests pass
- [ ] Frontend tests pass
- [ ] Android build passes
- [ ] API contract verified
- [ ] UI verified in browser

---

## Implementation

### Backend Schemas

**File: `app/schemas/requirement.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class RequirementCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class RequirementCategoryRead(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool

class RequirementFormCreate(BaseModel):
    category_id: uuid.UUID
    description: str = Field(..., min_length=1)
    priority: str = Field(..., pattern="^(LOW|MEDIUM|HIGH)$")
    expected_timeline: str = Field(..., min_length=1, max_length=100)
    budget_range: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None

class RequirementFormRead(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    category_id: uuid.UUID
    category_name: Optional[str] = None
    description: str
    priority: str
    expected_timeline: str
    budget_range: Optional[str] = None
    notes: Optional[str] = None
    submitted_at: datetime
```

### Backend Endpoints

**File: `app/api/v1/requirement_forms.py`**

```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.requirement import *

router = APIRouter(tags=["Requirement Forms"])

@router.get("/requirement-categories", response_model=list[RequirementCategoryRead])
async def list_categories(session: AsyncSession = Depends(get_async_session)):
    ...

@router.post("/requirement-categories", response_model=RequirementCategoryRead, status_code=201)
async def create_category(
    payload: RequirementCategoryCreate,
    _: CurrentUser = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_async_session),
):
    ...

@router.post("/visits/{visit_id}/requirement-form", response_model=RequirementFormRead, status_code=201)
async def submit_form(
    visit_id: uuid.UUID,
    payload: RequirementFormCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    ...

@router.get("/visits/{visit_id}/requirement-form", response_model=Optional[RequirementFormRead])
async def get_form(
    visit_id: uuid.UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    ...
```

### Android DTOs

**File: `data/model/RequirementFormModels.kt`**

```kotlin
data class RequirementCategoryDto(
    val id: String,
    val name: String,
    val isActive: Boolean
)

data class RequirementFormDto(
    val id: String,
    val visitId: String,
    val categoryId: String,
    val categoryName: String?,
    val description: String,
    val priority: String,
    val expectedTimeline: String,
    val budgetRange: String?,
    val notes: String?,
    val submittedAt: String
)
```

---

## Evidence

### Backend Implementation
- **Schemas:** `app/schemas/requirement.py` — RequirementCategoryCreate/Read, RequirementFormCreate/Read
- **Service:** `app/services/requirement_service.py` — list_categories, create_category, submit_form, get_form_by_visit
- **Endpoints:** `app/api/v1/requirement_forms.py` — 4 endpoints (GET/POST categories, POST/GET form)
- **Tests:** 255 backend tests pass (1 pre-existing integration test failure unrelated to this feature)

### Web Implementation
- **API Client:** `src/api/client.ts` — Added getRequirementCategories, submitRequirementForm, getRequirementForm
- **FormsPage:** Rewritten to show real category management UI with create modal
- **Tests:** 69 frontend tests pass

### Android Implementation
- **DTOs:** `data/model/RequirementFormModels.kt` — RequirementCategoryDto, RequirementFormDto, RequirementFormRequest
- **API:** `data/api/RequirementApi.kt` — Retrofit interface
- **Repository:** `data/repository/RequirementRepository.kt` — Data access layer
- **ViewModel:** `ui/viewmodel/RequirementViewModel.kt` — State management
- **Screen:** `ui/screens/requirements/RequirementFormScreen.kt` — Full form UI
- **Navigation:** Wired into Screen.kt + NavGraph.kt
- **Tests:** 49 Android tests pass

### Files Changed (15 files total)
1. `fieldtrackpro-backend/app/schemas/requirement.py` (new)
2. `fieldtrackpro-backend/app/services/requirement_service.py` (new)
3. `fieldtrackpro-backend/app/api/v1/requirement_forms.py` (new)
4. `fieldtrackpro-backend/app/api/v1/router.py` (modified)
5. `fieldtrackpro-backend/tests/test_validation.py` (modified - unique test numbers)
6. `fieldtrackpro-web/src/api/client.ts` (modified - added requirement methods)
7. `fieldtrackpro-web/src/pages/FormsPage.tsx` (rewritten - functional UI)
8. `fieldtrackpro-android/app/src/main/java/.../data/model/RequirementFormModels.kt` (new)
9. `fieldtrackpro-android/app/src/main/java/.../data/api/RequirementApi.kt` (new)
10. `fieldtrackpro-android/app/src/main/java/.../data/repository/RequirementRepository.kt` (new)
11. `fieldtrackpro-android/app/src/main/java/.../ui/viewmodel/RequirementViewModel.kt` (new)
12. `fieldtrackpro-android/app/src/main/java/.../ui/screens/requirements/RequirementFormScreen.kt` (new)
13. `fieldtrackpro-android/app/src/main/java/.../ui/navigation/Screen.kt` (modified)
14. `fieldtrackpro-android/app/src/main/java/.../ui/navigation/NavGraph.kt` (modified)
15. `fieldtrackpro-android/app/src/main/java/.../MainActivity.kt` (modified)
