from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src" / "enterprise_ai_tool_gateway"

FORBIDDEN_IMPORTS = {
    "contracts": (
        "workflow",
        "tools",
        "policy",
        "approval",
        "audit",
        "db",
        "llm",
        "mcp",
        "api",
    ),
    "workflow": (
        "tools",
        "policy",
        "approval",
        "audit",
        "db",
        "llm",
        "api",
    ),
    "tools": (
        "workflow",
        "policy",
        "approval",
        "audit",
        "db",
        "llm",
        "api",
    ),
    "policy": (
        "tools",
        "workflow",
        "approval",
        "audit",
        "db",
        "llm",
        "api",
    ),
    "approval": (
        "workflow",
        "tools",
        "policy",
        "audit",
        "db",
        "llm",
        "api",
    ),
    "audit": (
        "workflow",
        "tools",
        "policy",
        "approval",
        "db",
        "llm",
        "api",
    ),
    "db": (
        "workflow",
        "tools",
        "policy",
        "approval",
        "audit",
        "llm",
        "api",
    ),
    "access": (
        "workflow",
        "policy",
        "approval",
        "audit",
        "db",
        "llm",
        "api",
    ),
    "demo_domain": (
        "workflow",
        "tools",
        "policy",
        "approval",
        "audit",
        "db",
        "llm",
        "api",
    ),
}


def test_stage_4_and_5_packages_do_not_import_forbidden_siblings() -> None:
    violations: list[str] = []

    for package_name, forbidden_packages in FORBIDDEN_IMPORTS.items():
        package_path = SOURCE_ROOT / package_name
        for python_file in package_path.rglob("*.py"):
            source = python_file.read_text(encoding="utf-8")
            for forbidden_package in forbidden_packages:
                forbidden_import = f"enterprise_ai_tool_gateway.{forbidden_package}"
                if forbidden_import in source:
                    violations.append(
                        f"{python_file.relative_to(PROJECT_ROOT)} imports {forbidden_import}"
                    )

    assert violations == []
