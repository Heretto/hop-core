"""
Regression tests for DITA root-element enforcement.

Background
----------
Several job runs produced DITA whose root element was <section> instead of
<topic>. The cause: the AI correction / regeneration steps sometimes return
body-level content (one or more bare <section> elements) with no <topic>
wrapper. With multiple top-level elements, lxml's recovering parser silently
treats the first <section> as the document root, and callers then saved that
invalid output on a best-effort basis.

These tests lock in the fix:
1. DitaValidator.get_root_tag / has_valid_root correctly identify the root and
   reject multi-root / non-topic content.
2. DitaValidator.ensure_topic_root deterministically restores a valid <topic>
   root while preserving the body content.
3. DitaCorrectionService never returns content with an invalid root, even when
   the (mocked) AI keeps returning bare <section> elements.
"""

from dataclasses import dataclass, field
from typing import Any, Dict

import pytest

from hop_core.dita import DitaCorrectionService, DitaValidator


# ---------------------------------------------------------------------------
# Fixtures / sample content
# ---------------------------------------------------------------------------

@pytest.fixture
def validator():
    return DitaValidator()


VALID_TOPIC = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="rn-2024-01">
  <title>Release Notes 2024.01</title>
  <body>
    <section>
      <title>New Features</title>
      <p>Added single sign-on support.</p>
    </section>
  </body>
</topic>"""

# The exact failure mode: bare sections, no <topic> wrapper. Two top-level
# elements means lxml recover-mode would report the first <section> as root.
SECTION_ROOT_MULTI = """\
<section>
  <title>New Features</title>
  <p>Added single sign-on support.</p>
</section>
<section>
  <title>Bug Fixes</title>
  <p>Fixed a crash on export.</p>
</section>"""

# A single bare section (also an invalid root).
SECTION_ROOT_SINGLE = """\
<section>
  <title>Improvements</title>
  <p>Improved load times.</p>
</section>"""


@dataclass
class FakeGenerationResult:
    """Minimal result shape: DitaCorrectionService only reads ``.content``."""

    content: str
    model: str = "fake"
    usage: Dict[str, Any] = field(default_factory=dict)
    finish_reason: str = "stop"


class FakeAIService:
    """AI service stub that returns queued responses in order.

    A plain class with an ``async generate`` method — living proof that
    hop_core.dita.SupportsGenerate is satisfied structurally, with no
    inheritance or hop-core-specific base types required.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        if self._responses:
            content = self._responses.pop(0)
        else:
            content = self._responses_default()
        return FakeGenerationResult(content=content)

    @staticmethod
    def _responses_default():
        # Keep returning the broken shape to prove the deterministic safety net
        # — not the AI — is what guarantees a valid root.
        return SECTION_ROOT_MULTI


# ---------------------------------------------------------------------------
# get_root_tag / has_valid_root
# ---------------------------------------------------------------------------

class TestRootDetection:
    def test_topic_root_detected(self, validator):
        assert validator.get_root_tag(VALID_TOPIC) == "topic"

    def test_section_root_detected(self, validator):
        assert validator.get_root_tag(SECTION_ROOT_SINGLE) == "section"

    def test_topic_root_is_valid(self, validator):
        assert validator.has_valid_root(VALID_TOPIC) is True

    def test_single_section_root_is_invalid(self, validator):
        assert validator.has_valid_root(SECTION_ROOT_SINGLE) is False

    def test_multi_section_root_is_invalid(self, validator):
        # Multiple top-level elements must not be accepted just because the
        # first one parses — this is the original bug.
        assert validator.has_valid_root(SECTION_ROOT_MULTI) is False

    def test_concept_root_is_valid(self, validator):
        concept = (
            '<concept id="c1"><title>T</title><conbody><p>x</p></conbody></concept>'
        )
        assert validator.has_valid_root(concept) is True

    def test_unparseable_content_has_no_valid_root(self, validator):
        assert validator.has_valid_root("not xml <section") is False


# ---------------------------------------------------------------------------
# ensure_topic_root
# ---------------------------------------------------------------------------

class TestEnsureTopicRoot:
    def test_valid_topic_unchanged(self, validator):
        result = validator.ensure_topic_root(VALID_TOPIC)
        assert result == VALID_TOPIC

    def test_single_section_wrapped_in_topic(self, validator):
        result = validator.ensure_topic_root(SECTION_ROOT_SINGLE)
        assert validator.get_root_tag(result) == "topic"
        assert validator.has_valid_root(result) is True
        # Body content preserved
        assert "Improved load times." in result
        assert "<title>Improvements</title>" in result

    def test_multi_section_wrapped_in_single_topic(self, validator):
        result = validator.ensure_topic_root(SECTION_ROOT_MULTI)
        assert validator.get_root_tag(result) == "topic"
        assert validator.has_valid_root(result) is True
        # Both sections preserved under the single topic root
        assert "New Features" in result
        assert "Bug Fixes" in result
        assert "Added single sign-on support." in result
        assert "Fixed a crash on export." in result

    def test_wrapped_content_passes_structural_validation(self, validator):
        result = validator.ensure_topic_root(SECTION_ROOT_MULTI)
        valid, errors = validator.validate_structure(result)
        assert valid is True, f"Wrapped content should validate: {errors}"

    def test_wrapped_content_passes_dtd_validation_when_available(self, validator):
        if not DitaValidator._xmllint_available():
            pytest.skip("xmllint not available")
        result = validator.ensure_topic_root(SECTION_ROOT_MULTI)
        valid, errors = validator.validate_with_dtd(result)
        assert valid is True, f"Wrapped content should pass DTD validation: {errors}"

    def test_provided_id_and_title_used(self, validator):
        result = validator.ensure_topic_root(
            SECTION_ROOT_SINGLE, topic_id="rn-9-9", title="My Release"
        )
        assert 'id="rn-9-9"' in result
        assert "<title>My Release</title>" in result

    def test_invalid_id_is_sanitized_to_valid_format(self, validator):
        import re
        result = validator.ensure_topic_root(
            SECTION_ROOT_SINGLE, topic_id="123 bad id!", title="T"
        )
        m = re.search(r'<topic id="([^"]+)"', result)
        assert m, "topic root must have an id"
        topic_id = m.group(1)
        assert re.match(r'^[a-zA-Z][a-zA-Z0-9_\-]*$', topic_id), (
            f"sanitized id is not DITA-valid: {topic_id!r}"
        )

    def test_existing_body_content_unwrapped_not_double_nested(self, validator):
        """Content that already has a <body> should not gain a nested <body>."""
        content = (
            "<body><section><title>S</title><p>text</p></section></body>"
        )
        result = validator.ensure_topic_root(content)
        assert validator.get_root_tag(result) == "topic"
        # Exactly one <body> open tag
        assert result.count("<body>") == 1


# ---------------------------------------------------------------------------
# Correction service: never returns an invalid root
# ---------------------------------------------------------------------------

class TestCorrectionServiceRootEnforcement:
    async def test_section_root_correction_yields_topic_root(self, validator):
        """When the AI 'fixes' content by returning bare sections, the service
        must still return valid <topic>-rooted DITA."""
        ai = FakeAIService([SECTION_ROOT_MULTI])
        service = DitaCorrectionService(ai_service=ai, validator=validator)

        content, is_valid, log = await service.correct_validation_errors(
            VALID_TOPIC.replace("<title>Release Notes 2024.01</title>", ""),  # break it: no title
            max_attempts=2,
        )

        assert validator.get_root_tag(content) == "topic", (
            "Corrected output must have a <topic> root, never <section>.\n" + content
        )
        assert validator.has_valid_root(content) is True
        assert is_valid, "Wrapped/corrected content should validate. Log:\n" + "\n".join(log)

    async def test_full_flow_never_returns_section_root(self, validator):
        """validate_and_correct_with_ai must never hand back a <section> root,
        even if every AI response is body-level content."""
        ai = FakeAIService([])  # always returns the broken multi-section shape
        service = DitaCorrectionService(ai_service=ai, validator=validator)

        broken = "<section><title>S</title><p>only a section, no topic</p></section>"
        content, is_valid, log = await service.validate_and_correct_with_ai(
            broken,
            original_prompt="Generate DITA release notes.",
            max_cycles=2,
        )

        assert validator.get_root_tag(content) != "section", (
            "Pipeline returned a <section> root — the original bug.\n" + content
        )
        assert validator.has_valid_root(content) is True
        assert is_valid

    async def test_identity_preserved_when_wrapper_stripped(self, validator):
        """If the AI strips the wrapper, the rebuilt topic keeps the original
        id and title."""
        ai = FakeAIService([SECTION_ROOT_MULTI])
        service = DitaCorrectionService(ai_service=ai, validator=validator)

        # Valid-XML but DTD-invalid topic (unknown element) to force a correction,
        # carrying a distinctive id/title we expect to survive.
        broken = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<topic id="keep-this-id">\n'
            '  <title>Keep This Title</title>\n'
            '  <body><bogustag>x</bogustag></body>\n'
            '</topic>'
        )
        content, is_valid, log = await service.correct_validation_errors(
            broken, max_attempts=2
        )
        assert validator.has_valid_root(content)
        assert 'id="keep-this-id"' in content
        assert "Keep This Title" in content


# ---------------------------------------------------------------------------
# Loop-until-valid behavior and safety cap
# ---------------------------------------------------------------------------

# Well-formed XML, valid <topic> root, but DTD/structurally invalid (no <title>).
# The deterministic layer (auto_fix + ensure_topic_root) cannot fix this, so it
# forces the correction loop to keep calling the LLM.
NO_TITLE_TOPIC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<topic id="t"><body><p>missing title</p></body></topic>'
)

VALID_FIXED_TOPIC = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
    '<topic id="t"><title>Now Valid</title><body><p>fixed content</p></body></topic>'
)


class TestLoopUntilValid:
    async def test_loops_back_through_llm_until_valid(self, validator):
        """Invalid DITA is recoverable: the loop keeps calling the LLM until a
        response validates. It must NOT give up after one attempt."""
        # Two invalid responses, then a valid one on the third call.
        ai = FakeAIService([NO_TITLE_TOPIC, NO_TITLE_TOPIC, VALID_FIXED_TOPIC])
        service = DitaCorrectionService(ai_service=ai, validator=validator)

        content, is_valid, log = await service.validate_and_correct_with_ai(
            NO_TITLE_TOPIC, max_iterations=5
        )

        assert is_valid, "Loop should eventually produce valid DITA.\n" + "\n".join(log)
        assert "Now Valid" in content
        assert ai.calls == 3, f"Expected 3 LLM calls (valid on 3rd), got {ai.calls}"

    async def test_safety_cap_is_respected_and_does_not_loop_forever(self, validator):
        """When the LLM never produces valid output, the loop stops at the cap
        rather than looping forever — and reports is_valid=False."""
        ai = FakeAIService([])  # always returns the invalid no-title topic shape

        # Make the default response the persistently-invalid topic.
        ai._responses = [NO_TITLE_TOPIC] * 100
        service = DitaCorrectionService(ai_service=ai, validator=validator)

        content, is_valid, log = await service.validate_and_correct_with_ai(
            NO_TITLE_TOPIC, max_iterations=3  # no original_prompt → no regeneration escalation
        )

        assert is_valid is False, "Persistently-invalid content should report is_valid=False"
        assert ai.calls == 3, f"Loop must stop at the cap (3), made {ai.calls} calls"
        # Even on failure the safety net keeps a valid <topic> root (never <section>).
        assert validator.get_root_tag(content) == "topic"
        assert any("safety cap" in line.lower() for line in log)

    async def test_max_cycles_alias_still_accepted(self, validator):
        """Backward-compat: the old max_cycles kwarg maps to max_iterations."""
        ai = FakeAIService([NO_TITLE_TOPIC, VALID_FIXED_TOPIC])
        service = DitaCorrectionService(ai_service=ai, validator=validator)

        content, is_valid, log = await service.validate_and_correct_with_ai(
            NO_TITLE_TOPIC, max_cycles=4
        )
        assert is_valid
        assert ai.calls == 2

    async def test_deterministic_fix_needs_no_llm_call(self, validator):
        """A section-root (wrapper stripped) is fixed deterministically — the
        loop should not need to call the LLM at all."""
        ai = FakeAIService([])
        service = DitaCorrectionService(ai_service=ai, validator=validator)

        content, is_valid, log = await service.validate_and_correct_with_ai(
            SECTION_ROOT_SINGLE, max_iterations=5
        )
        assert is_valid
        assert validator.get_root_tag(content) == "topic"
        assert ai.calls == 0, f"No LLM call expected, made {ai.calls}"
