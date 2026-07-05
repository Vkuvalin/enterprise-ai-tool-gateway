"""Eval result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    workflow: str
    passed: bool
    failures: tuple[str, ...]
    initial_http_status: int | None
    initial_status: str | None
    final_status: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "workflow": self.workflow,
            "passed": self.passed,
            "failures": list(self.failures),
            "initial_http_status": self.initial_http_status,
            "initial_status": self.initial_status,
            "final_status": self.final_status,
        }


@dataclass(frozen=True)
class EvalSuiteResult:
    suite: str
    cases: tuple[EvalCaseResult, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "ok": self.ok,
            "cases": [case.to_dict() for case in self.cases],
        }
