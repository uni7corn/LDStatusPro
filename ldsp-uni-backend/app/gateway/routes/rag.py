"""RAG gateway routes — placeholder."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/gateway/rag", tags=["rag"])


@router.post("/query")
async def rag_query():
    return {
        "success": True,
        "data": {"message": "RAG query not yet implemented"},
    }


@router.post("/ingest")
async def rag_ingest():
    return {
        "success": True,
        "data": {"message": "RAG ingest not yet implemented"},
    }
