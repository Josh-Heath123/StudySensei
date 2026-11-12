import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Module
from app.schemas.academics import ModuleCreate, ModuleUpdate
from app.services.errors import Conflict, NotFound


async def list_modules(session: AsyncSession, *, user_id: uuid.UUID) -> list[Module]:
    result = await session.scalars(
        select(Module).where(Module.user_id == user_id).order_by(Module.code)
    )
    return list(result)


async def get_module(session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID) -> Module:
    module = await session.scalar(
        select(Module).where(Module.id == module_id, Module.user_id == user_id)
    )
    if module is None:
        raise NotFound("Module")
    return module


async def _ensure_code_free(
    session: AsyncSession, code: str, *, user_id: uuid.UUID, except_id: uuid.UUID | None = None
) -> None:
    query = select(Module.id).where(Module.user_id == user_id, Module.code == code)
    if except_id is not None:
        query = query.where(Module.id != except_id)
    if await session.scalar(query) is not None:
        raise Conflict(f"You already have a module with code {code}")


async def create_module(session: AsyncSession, data: ModuleCreate, *, user_id: uuid.UUID) -> Module:
    await _ensure_code_free(session, data.code, user_id=user_id)
    module = Module(user_id=user_id, **data.model_dump())
    session.add(module)
    await session.commit()
    return module


async def update_module(
    session: AsyncSession, module_id: uuid.UUID, data: ModuleUpdate, *, user_id: uuid.UUID
) -> Module:
    module = await get_module(session, module_id, user_id=user_id)
    changes = data.model_dump(exclude_unset=True)
    if "code" in changes:
        await _ensure_code_free(session, changes["code"], user_id=user_id, except_id=module.id)
    for field, value in changes.items():
        setattr(module, field, value)
    await session.commit()
    return module


async def delete_module(session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    """Deletes the module and, through FK cascades, its topics, assessments and tasks."""
    module = await get_module(session, module_id, user_id=user_id)
    await session.delete(module)
    await session.commit()
