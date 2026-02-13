from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check():
    from src.db.models import async_session
    from sqlalchemy import text
    
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not ready", "error": str(e)}
