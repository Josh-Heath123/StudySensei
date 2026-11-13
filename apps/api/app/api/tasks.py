import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import Task
from app.schemas.academics import TaskCreate, TaskOut, TaskStatus, TaskUpdate
from app.services.academics import tasks

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    session: SessionDep,
    user: CurrentUser,
    status: Annotated[list[TaskStatus], Query()] = [],  # noqa: B006 (FastAPI copies it)
) -> list[Task]:
    """Your tasks across all modules, soonest due first (undated last).

    Repeat ``status`` to keep only those statuses, e.g. ``?status=todo&status=in_progress``.
    """
    return await tasks.list_tasks(session, user_id=user.id, statuses=status)


@router.get("/modules/{module_id}/tasks", response_model=list[TaskOut])
async def list_module_tasks(
    module_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[Task]:
    """The module's tasks, soonest due first (undated last)."""
    return await tasks.list_tasks(session, user_id=user.id, module_id=module_id)


@router.post(
    "/modules/{module_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED
)
async def create_task(
    module_id: uuid.UUID, data: TaskCreate, session: SessionDep, user: CurrentUser
) -> Task:
    return await tasks.create_task(session, module_id, data, user_id=user.id)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Task:
    return await tasks.get_task(session, task_id, user_id=user.id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID, data: TaskUpdate, session: SessionDep, user: CurrentUser
) -> Task:
    """Setting status to "done" records completed_at; any other status clears it."""
    return await tasks.update_task(session, task_id, data, user_id=user.id)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await tasks.delete_task(session, task_id, user_id=user.id)
