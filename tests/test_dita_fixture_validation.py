"""
Static-fixture DTD validation tests.

Each test loads a known .dita file from tests/fixtures/dita/ and asserts that
the validator produces the expected outcome (valid or invalid) and, for invalid
cases, that the error messages mention the expected element or keyword.

Several invalid cases (e.g. title-after-body, step-missing-cmd) only fail under
full DTD validation, so this module requires xmllint and is skipped without it.

Adding a new test case:
  1. Drop a .dita file into tests/fixtures/dita/valid/ or invalid/.
  2. Add a row to VALID_CASES or INVALID_CASES below.
  3. Run the test suite — no other changes needed.

Fixture file comments explain exactly which DTD rule each file violates.
"""

import os
from dataclasses import dataclass

import pytest

from hop_core.dita import DitaValidator

pytestmark = pytest.mark.skipif(
    not DitaValidator._xmllint_available(),
    reason="xmllint not available in this environment (DTD-level assertions)",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "dita")
VALID_DIR    = os.path.join(FIXTURES_DIR, "valid")
INVALID_DIR  = os.path.join(FIXTURES_DIR, "invalid")


def _load(directory: str, filename: str) -> str:
    path = os.path.join(directory, filename)
    assert os.path.exists(path), f"Fixture file not found: {path}"
    with open(path, encoding="utf-8") as f:
        return f.read()


@dataclass
class ValidCase:
    filename: str
    description: str


@dataclass
class InvalidCase:
    filename: str
    description: str
    # One or more lowercase substrings that must appear in the combined error output.
    # Keeps assertions readable while tolerating minor xmllint message wording changes.
    error_keywords: tuple


# ---------------------------------------------------------------------------
# Test-case tables
# ---------------------------------------------------------------------------

VALID_CASES = [
    ValidCase("topic_minimal.dita",    "Minimal topic: title + single paragraph"),
    ValidCase("topic_full.dita",       "Full topic: shortdesc, multiple sections, ordered and unordered lists"),
    ValidCase("topic_with_note.dita",  "Topic: warning note and ordered list"),
    ValidCase("concept_minimal.dita",  "Minimal concept: title + conbody paragraph"),
    ValidCase("concept_full.dita",     "Full concept: shortdesc, multiple named sections"),
    ValidCase("task_minimal.dita",     "Minimal task: title + single step with cmd"),
    ValidCase("task_full.dita",        "Full task: prereq, context, multi-step, result, inline bold"),
    ValidCase("reference_minimal.dita","Minimal reference: title + refbody section"),
    ValidCase("reference_full.dita",   "Full reference: shortdesc, two sections, definition lists, codeph"),
]

INVALID_CASES = [
    InvalidCase(
        "topic_missing_title.dita",
        "Topic without <title> violates DTD content model",
        ("title", "topic"),
    ),
    InvalidCase(
        "topic_title_after_body.dita",
        "Title placed after body reverses required DTD order",
        ("title", "topic"),
    ),
    InvalidCase(
        "topic_unknown_element.dita",
        "<span>/<strong> are HTML inline elements undefined in the DITA DTD (use <ph>/<b>)",
        ("span", "declaration"),
    ),
    InvalidCase(
        "topic_wrong_body_element.dita",
        "<conbody> used inside <topic>; only defined in the concept DTD",
        ("conbody",),
    ),
    InvalidCase(
        "topic_empty_list.dita",
        "Empty <ul> has no <li> children, violating the DTD list content model",
        ("ul",),
    ),
    InvalidCase(
        "topic_malformed_xml.dita",
        "Unclosed <p> tag makes the document not well-formed XML",
        ("error",),   # parser / syntax error — wording varies
    ),
    InvalidCase(
        "concept_wrong_body_element.dita",
        "<body> used inside <concept>; concept requires <conbody>",
        ("concept", "body"),
    ),
    InvalidCase(
        "concept_missing_title.dita",
        "Concept without <title> violates DTD content model",
        ("title", "concept"),
    ),
    InvalidCase(
        "concept_nested_in_conbody.dita",
        "Nested <concept> inside <conbody> is not allowed by the DTD",
        ("conbody",),
    ),
    InvalidCase(
        "task_missing_title.dita",
        "Task without <title> violates DTD content model",
        ("title", "task"),
    ),
    InvalidCase(
        "task_paragraph_in_taskbody.dita",
        "<p> directly in <taskbody> violates the strict task content model",
        ("taskbody",),
    ),
    InvalidCase(
        "task_step_missing_cmd.dita",
        "<step> without <cmd> violates the step content model",
        ("cmd", "step"),
    ),
    InvalidCase(
        "reference_wrong_body_element.dita",
        "<body> used inside <reference>; reference requires <refbody>",
        ("reference", "body"),
    ),
    InvalidCase(
        "reference_missing_title.dita",
        "Reference without <title> violates DTD content model",
        ("title", "reference"),
    ),
]


# ---------------------------------------------------------------------------
# Parametrized tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def validator():
    return DitaValidator()


@pytest.mark.parametrize(
    "case",
    VALID_CASES,
    ids=[c.filename for c in VALID_CASES],
)
def test_valid_fixture(validator, case):
    """Each file in valid/ must pass DTD validation without errors."""
    content = _load(VALID_DIR, case.filename)
    valid, errors = validator.validate_with_dtd(content)
    assert valid, (
        f"{case.filename}: expected valid DITA but got errors:\n"
        + "\n".join(errors or [])
    )
    assert errors is None or errors == [], (
        f"{case.filename}: valid=True but non-empty error list: {errors}"
    )


@pytest.mark.parametrize(
    "case",
    INVALID_CASES,
    ids=[c.filename for c in INVALID_CASES],
)
def test_invalid_fixture(validator, case):
    """Each file in invalid/ must fail DTD validation with a meaningful error."""
    content = _load(INVALID_DIR, case.filename)
    valid, errors = validator.validate_with_dtd(content)

    assert not valid, (
        f"{case.filename}: expected DTD validation to fail, but it passed.\n"
        f"Description: {case.description}"
    )
    assert errors, (
        f"{case.filename}: validation failed but returned no error messages."
    )

    combined = " ".join(errors).lower()
    for keyword in case.error_keywords:
        assert keyword in combined, (
            f"{case.filename}: expected error keyword {keyword!r} not found.\n"
            f"Description: {case.description}\n"
            f"Actual errors:\n" + "\n".join(errors)
        )


# ---------------------------------------------------------------------------
# Inventory guard — fail fast if a fixture file is referenced but missing
# ---------------------------------------------------------------------------

def test_all_valid_fixtures_exist():
    """Every filename in VALID_CASES must have a corresponding file on disk."""
    missing = [
        c.filename for c in VALID_CASES
        if not os.path.exists(os.path.join(VALID_DIR, c.filename))
    ]
    assert not missing, f"Missing valid fixture files: {missing}"


def test_all_invalid_fixtures_exist():
    """Every filename in INVALID_CASES must have a corresponding file on disk."""
    missing = [
        c.filename for c in INVALID_CASES
        if not os.path.exists(os.path.join(INVALID_DIR, c.filename))
    ]
    assert not missing, f"Missing invalid fixture files: {missing}"
