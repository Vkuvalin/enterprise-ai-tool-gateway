from __future__ import annotations

import json

import pytest

from enterprise_ai_tool_gateway.contracts.enums import RequestType
from enterprise_ai_tool_gateway.llm import ProviderSchemaValidationError
from enterprise_ai_tool_gateway.llm.structured_output import (
    extract_json_object,
    parse_llm_decision_payload,
)


def _decision_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "request_type": "UNKNOWN",
        "domain_template": "UNKNOWN",
        "confidence": 0.7,
        "risk_level": "LOW",
        "requires_approval": False,
        "missing_fields": [],
        "proposed_tool_calls": [],
        "user_facing_summary": "Safe summary.",
        "reason_codes": ["TEST"],
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_plain_json_object_is_accepted() -> None:
    parsed = parse_llm_decision_payload(_decision_json())

    assert parsed.request_type is RequestType.UNKNOWN


def test_fenced_json_block_is_accepted() -> None:
    raw = f"```json\n{_decision_json()}\n```"

    parsed = parse_llm_decision_payload(raw)

    assert parsed.reason_codes == ["TEST"]


def test_fenced_json_block_with_surrounding_text_is_accepted() -> None:
    raw = f"model explanation before\n```json\n{_decision_json()}\n```\nmodel explanation after"

    parsed = parse_llm_decision_payload(raw)

    assert parsed.request_type is RequestType.UNKNOWN


def test_text_around_one_balanced_json_object_is_accepted() -> None:
    raw = f"prefix {_decision_json()} suffix"

    parsed = parse_llm_decision_payload(raw)

    assert parsed.request_type is RequestType.UNKNOWN


def test_text_wrapped_array_containing_one_valid_object_is_rejected() -> None:
    raw = f"prefix [{_decision_json()}] suffix"

    with pytest.raises(ProviderSchemaValidationError):
        parse_llm_decision_payload(raw)


@pytest.mark.parametrize(
    ("raw", "reason_code"),
    [
        ("", "empty_response"),
        ("no json here", "no_json_object"),
        ('{"request_type":}', "invalid_json"),
        (f"{_decision_json()} {_decision_json()}", "multiple_json_objects"),
        ("[]", "non_object_json_root"),
        ('{"request_type":"UNKNOWN"}', "llm_decision_schema_invalid"),
        (_decision_json(request_type="NOT_A_REQUEST_TYPE"), "llm_decision_schema_invalid"),
    ],
)
def test_invalid_outputs_are_rejected(raw: str, reason_code: str) -> None:
    with pytest.raises(ProviderSchemaValidationError) as exc_info:
        parse_llm_decision_payload(raw)

    assert exc_info.value.reason_code == reason_code


def test_multiple_fenced_blocks_are_rejected() -> None:
    raw = f"```json\n{_decision_json()}\n```\n```json\n{_decision_json()}\n```"

    with pytest.raises(ProviderSchemaValidationError) as exc_info:
        extract_json_object(raw)

    assert exc_info.value.reason_code == "multiple_fenced_json_blocks"


def test_fenced_json_block_plus_raw_json_object_is_rejected() -> None:
    raw = f"```json\n{_decision_json()}\n```\nextra {_decision_json()}"

    with pytest.raises(ProviderSchemaValidationError) as exc_info:
        extract_json_object(raw)

    assert exc_info.value.reason_code == "multiple_json_objects"


@pytest.mark.parametrize(
    "raw",
    [
        '{"request_type":"UNKNOWN",}',
        '{// comment\n"request_type":"UNKNOWN"}',
        "request_type: UNKNOWN",
    ],
)
def test_no_fuzzy_repair_is_attempted(raw: str) -> None:
    with pytest.raises(ProviderSchemaValidationError):
        parse_llm_decision_payload(raw)


def test_unknown_tool_proposal_is_preserved_for_runtime_validation() -> None:
    raw = _decision_json(
        request_type="ACCESS_REQUEST",
        domain_template="ACCESS",
        risk_level="MEDIUM",
        requires_approval=True,
        proposed_tool_calls=[
            {
                "name": "delete_access_grant",
                "arguments": {"employee_id": "emp-001"},
                "requires_approval": True,
            }
        ],
    )

    parsed = parse_llm_decision_payload(raw)

    assert parsed.proposed_tool_calls[0].name == "delete_access_grant"
