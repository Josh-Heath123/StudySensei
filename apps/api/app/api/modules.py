import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import Module
from app.schemas.academics import ModuleCreate, ModuleOut, ModuleUpdate
from app.services import materials
from app.services.academics import modules
from app.storage.base import Storage
from app.storage.local import get_storage

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get("", response_model=list[ModuleOut])
async def list_modules(session: SessionDep, user: CurrentUser) -> list[Module]:
    return await modules.list_modules(session, user_id=user.id)


@router.post("", response_model=ModuleOut, status_code=status.HTTP_201_CREATED)
async def create_module(data: ModuleCreate, session: SessionDep, user: CurrentUser) -> Module:
    return await modules.create_module(session, data, user_id=user.id)


@router.get("/{module_id}", response_model=ModuleOut)
async def get_module(module_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Module:
    return await modules.get_module(session, module_id, user_id=user.id)


@router.patch("/{module_id}", response_model=ModuleOut)
async def update_module(
    module_id: uuid.UUID, data: ModuleUpdate, session: SessionDep, user: CurrentUser
) -> Module:
    return await modules.update_module(session, module_id, data, user_id=user.id)


@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    storage: Annotated[Storage, Depends(get_storage)],
) -> None:
    """Deletes the module with all its topics, assessments, tasks and materials."""
    # Materials first, so their files go too (the database cascade can't delete files).
    await materials.delete_module_materials(session, storage, module_id, user_id=user.id)
    await modules.delete_module(session, module_id, user_id=user.id)
