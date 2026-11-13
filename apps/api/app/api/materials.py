import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.db import SessionDep
from app.models import Material
from app.schemas.materials import MaterialKind, MaterialOut, MaterialUpdate
from app.services import materials
from app.services.errors import TooLarge
from app.storage.base import Storage
from app.storage.local import get_storage

router = APIRouter(tags=["materials"])

StorageDep = Annotated[Storage, Depends(get_storage)]
# Room for the multipart boundaries and the other form fields.
_FORM_OVERHEAD = 64 * 1024


@router.post(
    "/modules/{module_id}/materials",
    response_model=MaterialOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_material(
    module_id: uuid.UUID,
    request: Request,
    file: Annotated[UploadFile, File(description="PDF, PPTX, DOCX, MD, TXT, PNG or JPG")],
    kind: Annotated[MaterialKind, Form()],
    session: SessionDep,
    user: CurrentUser,
    storage: StorageDep,
    title: Annotated[str | None, Form(max_length=200)] = None,
    allow_ai: Annotated[bool, Form()] = True,
) -> Material:
    """Upload one file (at most 50 MB) to the module and queue it for processing.

    The same file twice in one module is a 409; a wrong type is a 415.
    """
    limit = get_settings().max_upload_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit + _FORM_OVERHEAD:
        raise TooLarge(f"Files can be at most {limit // (1024 * 1024)} MB.")
    return await materials.upload_material(
        session,
        storage,
        module_id,
        user_id=user.id,
        source=file.file,
        filename=file.filename or "",
        kind=kind,
        title=title,
        allow_ai=allow_ai,
        max_bytes=limit,
    )


@router.get("/modules/{module_id}/materials", response_model=list[MaterialOut])
async def list_materials(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[Material]:
    """The module's materials, newest first."""
    return await materials.list_materials(session, module_id, user_id=user.id)


@router.get("/materials/{material_id}", response_model=MaterialOut)
async def get_material(material_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Material:
    return await materials.get_material(session, material_id, user_id=user.id)


@router.patch("/materials/{material_id}", response_model=MaterialOut)
async def update_material(
    material_id: uuid.UUID, data: MaterialUpdate, session: SessionDep, user: CurrentUser
) -> Material:
    """Change the title, the kind or whether AI may process it."""
    return await materials.update_material(session, material_id, data, user_id=user.id)


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: uuid.UUID, session: SessionDep, user: CurrentUser, storage: StorageDep
) -> None:
    """Delete the material (its file too, unless another of your modules has the same file)."""
    await materials.delete_material(session, storage, material_id, user_id=user.id)


@router.post("/materials/{material_id}/retry", response_model=MaterialOut)
async def retry_material(
    material_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> Material:
    """Queue a failed material for processing again."""
    return await materials.retry_material(session, material_id, user_id=user.id)
