import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models import Task
from app.schemas.academics import TaskCreate, TaskUpdate
from app.services.academics.assessments import get_assessment
from app.services.academics.modules import get_module
from app.services.errors import Invalid, NotFound


async def list_tasks(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    module_id: uuid.UUID | None = None,
    statuses: Collection[str] = (),
) -> list[Task]:
    """The user's tasks, soonest due first (undated ones last).

    With ``module_id``, only that module's (NotFound if it isn't the user's);
    with ``statuses``, only those statuses.
    """
    query = select(Task).where(Task.user_id == user_id)
    if module_id is not None:
        await get_module(session, module_id, user_id=user_id)
        query = query.where(Task.module_id == module_id)
    if statuses:
        query = query.where(Task.status.in_(statuses))
    result = await session.scalars(query.order_by(Task.due_at.asc().nulls_last(), Task.title))
    return list(result)


async def get_task(session: AsyncSession, task_id: uuid.UUID, *, user_id: uuid.UUID) -> Task:
    task = await session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    if task is None:
        raise NotFound("Task")
    return task


async def _check_assessment(
    session: AsyncSession, assessment_id: uuid.UUID, module_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    assessment = await get_assessment(session, assessment_id, user_id=user_id)
    if assessment.module_id != module_id:
        raise Invalid("A task's assessment must be in the same module")


def _apply_status(task: Task, status: str) -> None:
    """Keep completed_at in step with status."""
    if status == "done" and task.status != "done":
        task.completed_at = clock.now()
    elif status != "done":
        task.completed_at = None
    task.status = status


async def create_task(
    session: AsyncSession, module_id: uuid.UUID, data: TaskCreate, *, user_id: uuid.UUID
) -> Task:
    await get_module(session, module_id, user_id=user_id)
    if data.assessment_id is not None:
        await _check_assessment(session, data.assessment_id, module_id, user_id=user_id)
    task = Task(user_id=user_id, module_id=module_id, **data.model_dump(exclude={"status"}))
    _apply_status(task, data.status)
    session.add(task)
    await session.commit()
    return task


async def update_task(
    session: AsyncSession, task_id: uuid.UUID, data: TaskUpdate, *, user_id: uuid.UUID
) -> Task:
    task = await get_task(session, task_id, user_id=user_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("assessment_id") is not None:
        await _check_assessment(session, changes["assessment_id"], task.module_id, user_id=user_id)
    if "status" in changes:
        _apply_status(task, changes.pop("status"))
    for name, value in changes.items():
        setattr(task, name, value)
    await session.commit()
    return task


async def delete_task(session: AsyncSession, task_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    task = await get_task(session, task_id, user_id=user_id)
    await session.delete(task)
    await session.commit()
