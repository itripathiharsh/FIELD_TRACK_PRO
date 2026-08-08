from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    """Basic application health check."""
    return {"status": "UP", "service": "FieldTrack Pro API"}


@router.get("/health/db", tags=["health"])
async def db_health_check(db: AsyncSession = Depends(get_db)):
    """Database connectivity health check."""
    try:
        result = await db.execute(text("SELECT 1"))
        row = result.scalar()
        if row == 1:
            return {"status": "UP", "database": "connected"}
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database query returned unexpected result"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failure"
        )
