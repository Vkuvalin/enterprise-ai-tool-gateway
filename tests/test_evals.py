from __future__ import annotations

import json
from dataclasses import replace

from enterprise_ai_tool_gateway.evals import acceptance_cases, run_cases, run_suite
from enterprise_ai_tool_gateway.llm import StaticDecisionProvider


REQUIRED_CASE_IDS = {
    "access_completed",
    "access_approval_approved",
    "access_approval_rejected",
    "access_missing_input",
    "access_manual_review_unknown_system",
    "access_rejected_forbidden",
    "access_failed_validation_unknown_tool",
    "procurement_completed",
    "procurement_approval_approved",
    "procurement_approval_rejected",
    "procurement_missing_input",
    "procurement_manual_review_total_mismatch_or_budget",
    "procurement_rejected_blocked_vendor_or_restricted_item",
    "procurement_failed_validation_unknown_tool",
    "maintenance_completed",
    "maintenance_approval_approved",
    "maintenance_approval_rejected",
    "maintenance_missing_input",
    "maintenance_manual_review_safety_or_critical_asset",
    "maintenance_rejected_forbidden",
    "maintenance_failed_validation_unknown_tool",
}


def test_acceptance_suite_contains_required_21_cases() -> None:
    cases = acceptance_cases()

    assert len(cases) == 21
    assert {case.case_id for case in cases} == REQUIRED_CASE_IDS


def test_eval_runner_passes_for_deterministic_setup() -> None:
    result = run_suite()

    assert result.ok
    assert result.total == 21
    assert result.passed == 21


def test_eval_runner_fails_when_expected_status_is_wrong() -> None:
    case = acceptance_cases()[0]
    wrong_case = replace(case, expected_status="REJECTED")

    result = run_cases([wrong_case])

    assert not result.ok
    assert result.failed == 1
    assert result.cases[0].failures


def test_json_result_is_serializable() -> None:
    result = run_cases([acceptance_cases()[0]])

    encoded = json.dumps(result.to_dict(), sort_keys=True)

    assert '"ok": true' in encoded


def test_eval_cases_use_only_mock_or_static_offline_providers() -> None:
    for case in acceptance_cases():
        for provider in case.provider_overrides.values():
            assert isinstance(provider, StaticDecisionProvider)
            assert provider.__class__.__module__ == "enterprise_ai_tool_gateway.llm.static"
