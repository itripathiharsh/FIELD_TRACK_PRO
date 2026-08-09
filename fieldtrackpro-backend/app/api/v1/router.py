from fastapi import APIRouter
from app.api.v1 import (
    health,
    auth,
    users,
    territories,
    employees,
    customers,
    visits,
    geo,
    media,
    signatures,
    reports,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(territories.router)
api_router.include_router(employees.router)
api_router.include_router(customers.router)
api_router.include_router(visits.router)
api_router.include_router(geo.router)
api_router.include_router(media.router)
api_router.include_router(signatures.router)
api_router.include_router(reports.router)
