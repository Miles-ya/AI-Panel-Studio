from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest

from app.models import Participant


DISCUSSION_ID = "11111111-1111-1111-1111-111111111111"
OTHER_DISCUSSION_ID = "22222222-2222-2222-2222-222222222222"
MODERATOR_ID = "33333333-3333-3333-3333-333333333333"
FIRST_EXPERT_ID = "44444444-4444-4444-4444-444444444444"
SECOND_EXPERT_ID = "55555555-5555-5555-5555-555555555555"
OUTSIDER_ID = "66666666-6666-6666-6666-666666666666"


def _selection_types() -> tuple[type[Any], type[Exception]]:
    """Load the future selection boundary without making its absence a collection error."""
    llm = import_module("app.llm")
    selection = getattr(llm, "SpeakerSelectionOutput", None)
    validation_error = getattr(llm, "SpeakerSelectionOutputValidationError", None)

    assert selection is not None, "Speaker selection output is not implemented"
    assert validation_error is not None, "Speaker selection output validation is not implemented"
    assert callable(getattr(selection, "from_provider_response", None))
    assert callable(getattr(selection, "validate_for", None))
    return selection, validation_error


def _participant(*, participant_id: str, role: str, discussion_id: str = DISCUSSION_ID) -> Participant:
    return Participant(
        id=participant_id,
        discussion_id=discussion_id,
        role=role,
        name=f"公开嘉宾 {participant_id[-1]}",
        profession="公开职业",
        title="公开职务",
        stance="公开立场",
        color="#2563EB" if role == "moderator" else "#F59E0B",
        runtime_status="idle",
    )


def _public_participants() -> list[Participant]:
    return [
        _participant(participant_id=MODERATOR_ID, role="moderator"),
        _participant(participant_id=FIRST_EXPERT_ID, role="expert"),
        _participant(participant_id=SECOND_EXPERT_ID, role="expert"),
    ]


def _selection(participant_id: str, public_focus: str = "继续讨论公开目标") -> Any:
    selection, _ = _selection_types()
    return selection.from_provider_response(
        {"participant_id": participant_id, "public_focus": public_focus}
    )


def test_when_first_turn_selects_non_moderator_then_selection_is_rejected() -> None:
    _, validation_error = _selection_types()

    with pytest.raises(validation_error):
        _selection(FIRST_EXPERT_ID).validate_for(
            DISCUSSION_ID, _public_participants(), FIRST_EXPERT_ID, 0, False
        )


def test_when_selection_references_cross_discussion_participant_then_selection_is_rejected() -> None:
    _, validation_error = _selection_types()
    participants = [
        _participant(participant_id=MODERATOR_ID, role="moderator"),
        _participant(participant_id=OUTSIDER_ID, role="expert", discussion_id=OTHER_DISCUSSION_ID),
    ]

    with pytest.raises(validation_error):
        _selection(OUTSIDER_ID).validate_for(DISCUSSION_ID, participants, MODERATOR_ID, 1, False)


def test_when_other_candidates_exist_and_prior_speaker_is_selected_again_then_selection_is_rejected() -> None:
    _, validation_error = _selection_types()

    with pytest.raises(validation_error):
        _selection(FIRST_EXPERT_ID).validate_for(
            DISCUSSION_ID, _public_participants(), FIRST_EXPERT_ID, 2, False
        )


def test_when_discussion_is_stopped_then_even_a_legal_selection_is_rejected() -> None:
    _, validation_error = _selection_types()

    with pytest.raises(validation_error):
        _selection(FIRST_EXPERT_ID).validate_for(
            DISCUSSION_ID, _public_participants(), MODERATOR_ID, 1, True
        )


def test_when_public_utterance_limit_is_reached_then_selection_is_rejected() -> None:
    _, validation_error = _selection_types()

    with pytest.raises(validation_error):
        _selection(FIRST_EXPERT_ID).validate_for(
            DISCUSSION_ID, _public_participants(), MODERATOR_ID, 15, False
        )


def test_when_model_returns_a_legal_selection_then_selection_is_accepted() -> None:
    selection = _selection(FIRST_EXPERT_ID)

    selection.validate_for(DISCUSSION_ID, _public_participants(), MODERATOR_ID, 1, False)


def test_when_model_returns_non_uuid_participant_id_then_schema_rejects_it() -> None:
    selection, validation_error = _selection_types()

    with pytest.raises(validation_error):
        selection.from_provider_response(
            {"participant_id": "not-a-uuid", "public_focus": "继续讨论公开目标"}
        )


@pytest.mark.parametrize("public_focus", ["   ", "x" * 51, "公开\n关注点"])
def test_when_public_focus_is_empty_too_long_or_multiline_then_schema_rejects_it(
    public_focus: str,
) -> None:
    selection, validation_error = _selection_types()

    with pytest.raises(validation_error):
        selection.from_provider_response(
            {"participant_id": FIRST_EXPERT_ID, "public_focus": public_focus}
        )


@pytest.mark.parametrize("extra_field", ["reasoning", "chain_of_thought", "intent", "provider_metadata"])
def test_when_model_returns_hidden_or_undeclared_fields_then_schema_rejects_it(
    extra_field: str,
) -> None:
    selection, validation_error = _selection_types()
    payload = {"participant_id": FIRST_EXPERT_ID, "public_focus": "继续讨论公开目标"}
    payload[extra_field] = "not-permitted"

    with pytest.raises(validation_error):
        selection.from_provider_response(payload)
