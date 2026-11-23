"""Topic mastery (ADR 0027): computed on read by ``services/mastery``. An estimate of how well
the student knows a topic now; never an exam prediction."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.services.mastery.formula import Mastery
from app.services.mastery.load import TopicMastery


class MasteryComponentsOut(BaseModel):
    # M: mean FSRS recall now over the active items reviewed (null if none).
    recall: float | None
    # A: the recency-weighted share of attempts right (null with no attempts).
    accuracy: float | None
    # P: the rating mapped to 0..1 (0.5 unrated).
    prior: float
    # w = n / (n + 3): how much the attempts count against the prior.
    weight: float
    # g = m / (m + 3), m the items reviewed: how much of recall's 0.6 share it carries.
    recall_weight: float


class MasterySamplesOut(BaseModel):
    items_reviewed: int
    items_active: int
    attempts: int
    quiz_answers: int
    reviews: int
    days_spanned: int
    rating_source: Literal["session", "starting", "subtopics", "none"]


class TopicMasteryOut(BaseModel):
    topic_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    # 0..1. Always an estimate; with fewer than 3 attempts the status is "not_enough" and the
    # UI shows the basis sentence instead of the value.
    value: float
    label: Literal["estimated"] = "estimated"
    status: Literal["not_enough", "estimated"]
    band: Literal["weak", "developing", "strong"]
    components: MasteryComponentsOut
    samples: MasterySamplesOut
    # One sentence, written by code, with every number labelled.
    basis: str


class ModuleMasteryOut(BaseModel):
    module_id: uuid.UUID
    # When it was computed.
    at: datetime
    # Every topic, in tree order (a parent before its children).
    topics: list[TopicMasteryOut]


def topic_mastery_out(found: TopicMastery) -> TopicMasteryOut:
    m: Mastery = found.mastery
    c, s = m.components, m.samples
    return TopicMasteryOut(
        topic_id=found.topic_id,
        parent_id=found.parent_id,
        name=found.name,
        value=m.value,
        status=m.status,
        band=m.band,
        components=MasteryComponentsOut(
            recall=c.recall,
            accuracy=c.accuracy,
            prior=c.prior,
            weight=c.weight,
            recall_weight=c.recall_weight,
        ),
        samples=MasterySamplesOut(
            items_reviewed=s.items_reviewed,
            items_active=s.items_active,
            attempts=s.attempts,
            quiz_answers=s.quiz_answers,
            reviews=s.reviews,
            days_spanned=s.days_spanned,
            rating_source=s.rating_source,
        ),
        basis=m.basis,
    )
