"""SQLAlchemy models. Import every model here so Alembic sees it."""

from app.models.academics import Assessment, AssessmentTopic, Module, Task, Topic
from app.models.base import Base
from app.models.user import User

__all__ = ["Assessment", "AssessmentTopic", "Base", "Module", "Task", "Topic", "User"]
