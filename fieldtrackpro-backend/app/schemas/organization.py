from __future__ import annotations
from typing import List
from pydantic import BaseModel


class OrganizationProfile(BaseModel):
    organization_name: str
    operational_hub: str
    divisions: str
    contact_email: str
    contact_phone: str
    gstin: str
    timezone: str
    currency: str
    total_employees: int
    total_customers: int
    total_territories: int
    total_areas: int
    master_brands: List[str]
