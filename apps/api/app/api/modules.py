import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import Module
from app.schemas.academics import ModuleCreate, ModuleOut, ModuleUpdate
from app.services.academics import modules

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
async def delete_module(module_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    """Deletes the module with all its topics, assessments and tasks."""
    await modules.delete_module(session, module_id, user_id=user.id)
