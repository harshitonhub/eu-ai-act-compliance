"""Enforces .claude/rules/architecture.md: 'Deterministic business rules must not be
delegated to an LLM.' Legal knowledge modules must never import the LLM layer.
"""

import ast
from pathlib import Path

DETERMINISTIC_PACKAGES = ["legal", "obligations", "gaps", "review", "retrieval", "reporting"]
SRC = Path(__file__).resolve().parents[1] / "src"


def _imported_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_deterministic_packages_never_import_llm_layer():
    violations = []
    for package in DETERMINISTIC_PACKAGES:
        package_dir = SRC / package
        if not package_dir.exists():
            continue
        for py_file in package_dir.rglob("*.py"):
            for module in _imported_modules(py_file):
                if module == "src.llm" or module.startswith("src.llm."):
                    violations.append(f"{py_file.relative_to(SRC.parent)} imports {module}")

    assert not violations, "Deterministic packages must not import the LLM layer:\n" + "\n".join(
        violations
    )


def test_llm_interface_has_no_references_outside_src_llm():
    """Consumers outside src/llm must import the public surface (`src.llm`), not reach
    into `src.llm.interface` directly -- see src/llm/__init__.py.
    """
    violations = []
    for py_file in SRC.rglob("*.py"):
        if py_file.is_relative_to(SRC / "llm"):
            continue
        for module in _imported_modules(py_file):
            if module == "src.llm.interface":
                violations.append(str(py_file.relative_to(SRC.parent)))

    assert not violations, "src.llm.interface referenced outside src/llm/:\n" + "\n".join(violations)
