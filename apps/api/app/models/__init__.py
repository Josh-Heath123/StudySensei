"""SQLAlchemy models. Import every model here so Alembic sees it."""

from app.models.academics import Assessment, AssessmentTopic, Module, Task, Topic
from app.models.base import Base
from app.models.jobs import Job
from app.models.materials import Material, MaterialPage
from app.models.sessions import SessionEvent, SessionTopicRating, StudySession
from app.models.user import User

__all__ = [
    "Assessment",
    "AssessmentTopic",
    "Base",
    "Job",
    "Material",
    "MaterialPage",
    "Module",
    "SessionEvent",
    "SessionTopicRating",
    "StudySession",
    "Task",
    "Topic",
    "User",
]
