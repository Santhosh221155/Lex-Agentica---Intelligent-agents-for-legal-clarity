from fastapi import APIRouter, Depends

from app.services.ingestion import verify_ingestion
from app.api.auth import get_admin_user

router = APIRouter()


@router.get("/api/verify-ingestion")
async def verify_ingestion_route(collection: str = "legal_docs", user: dict = Depends(get_admin_user)):
    return verify_ingestion(collection_name=collection)
