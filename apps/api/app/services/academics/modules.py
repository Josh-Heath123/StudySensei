import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


@asynccontextmanager
async def _code_must_be_unique(
    session: AsyncSession, code: str, existing: Module | None = None
) -> AsyncIterator[None]:
    """Run a change in a SAVEPOINT; a duplicate (user_id, code) becomes a Conflict.

    The unique constraint is the only check, so two concurrent requests can't
    both slip past a "does it exist?" query. Rolling back just the savepoint
    keeps the rest of the session usable; ``existing`` (the module being
    updated) is reloaded so the caller never holds an expired object.
    """
    try:
        async with session.begin_nested():
            yield
            await session.flush()
    except IntegrityError as exc:
        if "uq_modules_user_code" not in str(exc.orig):
            raise
        if existing is not None:
            await session.refresh(existing)
        raise Conflict(f"You already have a module with the code {code}.") from exc


async def create_module(session: AsyncSession, data: ModuleCreate, *, user_id: uuid.UUID) -> Module:
    module = Module(user_id=user_id, **data.model_dump())
    async with _code_must_be_unique(session, data.code):
        session.add(module)
    await session.commit()
    return module


async def update_module(
    session: AsyncSession, module_id: uuid.UUID, data: ModuleUpdate, *, user_id: uuid.UUID
) -> Module:
    module = await get_module(session, module_id, user_id=user_id)
    async with _code_must_be_unique(session, data.code or module.code, existing=module):
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(module, field, value)
    await session.commit()
    return module


async def delete_module(session: AsyncSession, module_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    """Deletes the module and, through FK cascades, its topics, assessments and tasks."""
    module = await get_module(session, module_id, user_id=user_id)
    await session.delete(module)
    await session.commit()
