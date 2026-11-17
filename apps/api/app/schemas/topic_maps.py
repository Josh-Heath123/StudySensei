"""Topic maps (decision 0006): the AI's output shapes, and the API's status response.

AI output is saved only after it passes these models (``complete_json`` validates and
repairs once). Limits are part of the contract the model is shown.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

TopicName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
OneSentence = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
PageList = Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=200)]
# Short references the merge prompt gives proposals and existing topics ("M2.3", "E5").
Ref = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]


# --- extract_topics: one material ---------------------------------------------------


class ProposedSubtopic(BaseModel):
    name: TopicName
    description: OneSentence = Field(description="One sentence saying what it covers.")
    pages: PageList = Field(description="Page numbers in this material that cover it.")


class ProposedTopic(ProposedSubtopic):
    subtopics: list[ProposedSubtopic] = Field(default_factory=list, max_length=10)


class MaterialTopics(BaseModel):
    """What one material covers: topics, each with at most 10 subtopics (two levels)."""

    topics: list[ProposedTopic] = Field(max_length=40)


# --- merge_topics: one module -------------------------------------------------------


class MergedSubtopic(BaseModel):
    existing: Ref | None = Field(
        default=None, description='An existing topic\'s id ("E3") when this node is it.'
    )
    name: TopicName
    description: OneSentence
    sources: list[Ref] = Field(
        default_factory=list,
        max_length=60,
        description='The proposal ids ("M2.3", "M2.3.1") merged into this node.',
    )


class MergedTopic(MergedSubtopic):
    subtopics: list[MergedSubtopic] = Field(default_factory=list, max_length=15)


class ModuleTopicMap(BaseModel):
    """The module's tree: chapters or big themes at the top, subtopics under each."""

    topics: list[MergedTopic] = Field(max_length=25)


# --- API ---------------------------------------------------------------------------


class TopicMapStatus(BaseModel):
    # Materials whose topics can be extracted (allow_ai on, and a kind that teaches).
    eligible: int
    # Of those, how many have a proposal.
    analysed: int
    # extract_topics jobs waiting or running for the module.
    pending: int
    # Eligible materials whose last extraction failed for good.
    failed: int
    # A merge_topics job is waiting or running.
    merging: bool
    # When a job held back by AI rate limits or quotas will next run, if any.
    waiting_until: datetime | None
    # The latest failure's message (safe to show), if any.
    last_error: str | None
    # When the module's topics were last merged from proposals.
    merged_at: datetime | None
