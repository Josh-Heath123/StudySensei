"""SQLAlchemy models. Import every model here so Alembic sees it."""

from app.models.academics import Assessment, AssessmentTopic, Module, Task, Topic
from app.models.ai import AIUsage
from app.models.base import Base
from app.models.jobs import Job
from app.models.materials import Chunk, Material, MaterialPage
from app.models.sessions import SessionEvent, SessionTopicRating, StudySession
from app.models.topic_maps import ChunkTopic, TopicPage, TopicProposal
from app.models.user import User

__all__ = [
    "AIUsage",
    "Assessment",
    "AssessmentTopic",
    "Base",
    "Chunk",
    "ChunkTopic",
    "Job",
    "Material",
    "MaterialPage",
    "Module",
    "SessionEvent",
    "SessionTopicRating",
    "StudySession",
    "Task",
    "Topic",
    "TopicPage",
    "TopicProposal",
    "User",
]
