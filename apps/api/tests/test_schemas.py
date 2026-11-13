"""Update schemas: omitted fields are left alone, explicit null only clears nullable fields."""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.academics import (
    AssessmentUpdate,
    ModuleCreate,
    ModuleUpdate,
    TaskUpdate,
    TopicUpdate,
)

# (schema, a required column that must not be nulled, a nullable column that may be)
CASES: list[tuple[type[BaseModel], str, str | None]] = [
    (ModuleUpdate, "name", "semester"),
    (ModuleUpdate, "code", None),
    (ModuleUpdate, "colour", None),
    (TopicUpdate, "name", "description"),
    (AssessmentUpdate, "title", "due_at"),
    (AssessmentUpdate, "kind", "weight"),
    (AssessmentUpdate, "status", "notes"),
    (TaskUpdate, "title", "assessment_id"),
    (TaskUpdate, "status", "due_at"),
]


@pytest.mark.parametrize(("schema", "required", "nullable"), CASES)
def test_explicit_null_rejected_for_required_fields(
    schema: type[BaseModel], required: str, nullable: str | None
) -> None:
    with pytest.raises(ValidationError, match=f"{required} cannot be null"):
        schema.model_validate({required: None})

    if nullable is not None:
        data: dict[str, Any] = schema.model_validate({nullable: None}).model_dump(
            exclude_unset=True
        )
        assert data == {nullable: None}


def test_omitted_fields_stay_unset() -> None:
    assert ModuleUpdate.model_validate({}).model_dump(exclude_unset=True) == {}


def test_module_codes_are_upper_cased() -> None:
    assert ModuleCreate(code=" cos330 ", name="X").code == "COS330"
    assert ModuleUpdate(code="cos301").code == "COS301"


def test_topic_ids_cannot_be_null_but_can_be_empty() -> None:
    with pytest.raises(ValidationError, match="topic_ids cannot be null"):
        AssessmentUpdate.model_validate({"topic_ids": None})
    assert AssessmentUpdate.model_validate({"topic_ids": []}).topic_ids == []


@pytest.mark.parametrize("schema", [AssessmentUpdate, TaskUpdate])
def test_dates_need_a_timezone(schema: type[BaseModel]) -> None:
    with pytest.raises(ValidationError, match="timezone"):
        schema.model_validate({"due_at": "2026-11-28T09:00:00"})
    assert schema.model_validate({"due_at": "2026-11-28T09:00:00+02:00"})
