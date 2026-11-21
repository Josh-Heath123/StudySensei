"""SQLAlchemy models. Import every model here so Alembic sees it."""

from app.models.academics import Assessment, AssessmentTopic, Module, Task, Topic
from app.models.ai import AIUsage
from app.models.base import Base
from app.models.jobs import Job
from app.models.materials import Chunk, Material, MaterialPage
from app.models.planning import AvailabilityException, AvailabilityRule
from app.models.plans import PlanBlock, PlanVersion
from app.models.reminders import CalendarFeed, PushSubscription, ReminderSent
from app.models.sessions import SessionEvent, SessionTopicRating, StudySession
from app.models.topic_maps import ChunkTopic, TopicPage, TopicProposal, TopicReview, TopicUnlink
from app.models.tutor import Conversation, Message, MessageSource
from app.models.user import User

__all__ = [
    "AIUsage",
    "Assessment",
    "AssessmentTopic",
    "AvailabilityException",
    "AvailabilityRule",
    "Base",
    "CalendarFeed",
    "Chunk",
    "ChunkTopic",
    "Conversation",
    "Job",
    "Material",
    "MaterialPage",
    "Message",
    "MessageSource",
    "Module",
    "PlanBlock",
    "PlanVersion",
    "PushSubscription",
    "ReminderSent",
    "SessionEvent",
    "SessionTopicRating",
    "StudySession",
    "Task",
    "Topic",
    "TopicPage",
    "TopicProposal",
    "TopicReview",
    "TopicUnlink",
    "User",
]
