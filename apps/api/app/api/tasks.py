import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models import Task
from app.schemas.academics import TaskCreate, TaskOut, TaskUpdate
from app.services.academics import tasks

router = APIRouter(tags=["tasks"])


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    session: SessionDep,
    user: CurrentUser,
    module_id: uuid.UUID | None = None,
    assessment_id: uuid.UUID | None = None,
) -> list[Task]:
    """Your tasks, soonest due first (undated last), optionally filtered."""
    return await tasks.list_tasks(
        session, user_id=user.id, module_id=module_id, assessment_id=assessment_id
    )


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
