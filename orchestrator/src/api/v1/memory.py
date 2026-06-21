from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user, get_doc_store
from src.schemas.schemas import AdrListResponse, ProjectMemoryResponse
from src.services.document_store.store import DocumentStore

router = APIRouter(prefix="/memory", tags=["document-store"])


@router.get("/{project_id}", response_model=ProjectMemoryResponse)
async def get_project_memory(
    project_id: str,
    _: dict = Depends(get_current_user),
    store: DocumentStore = Depends(get_doc_store),
):
    mem = await store.get_memory(project_id)
    if not mem:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("No memory for this project yet")
    return mem


@router.get("/{project_id}/adrs", response_model=AdrListResponse)
async def get_adrs(
    project_id: str,
    status: str = "accepted",
    _: dict = Depends(get_current_user),
    store: DocumentStore = Depends(get_doc_store),
):
    adrs = await store.list_adrs(project_id, status_filter=status)
    return AdrListResponse(adrs=adrs)
