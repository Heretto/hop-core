"""
Unit tests for DitaValidator DTD and structural validation.

Covers:
- Packaged DTD resources resolve (guards the package-data config)
- xmllint-based DTD validation (valid and invalid DITA)
- DOCTYPE injection helper
- Structural validation fallback
- auto_fix_common_issues pipeline
- Regression guard: validate_with_dtd must call xmllint when available
"""

import os

import pytest
from unittest.mock import patch

from hop_core.dita import DitaValidator


# ---------------------------------------------------------------------------
# Fixtures
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
      <ul>
        <li>Added user authentication</li>
        <li>Implemented data export</li>
      </ul>
    </section>
    <section>
      <title>Bug Fixes</title>
      <p>Fixed a memory leak in the data pipeline.</p>
    </section>
  </body>
</topic>"""

VALID_TOPIC_WITH_SHORTDESC = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="rn-2024-02">
  <title>Release Notes 2024.02</title>
  <shortdesc>Minor update with stability improvements.</shortdesc>
  <body>
    <p>No breaking changes in this release.</p>
  </body>
</topic>"""


# ---------------------------------------------------------------------------
# Packaged DTD resources (guards the package-data configuration — a silent
# omission would degrade validate_with_dtd to the weaker structural fallback)
# ---------------------------------------------------------------------------

class TestPackagedResources:
    def test_default_dtd_dir_exists(self, validator):
        assert os.path.isdir(validator.dtd_dir), (
            f"Bundled DTD directory not found: {validator.dtd_dir}"
        )

    def test_xmllint_dtds_present(self, validator):
        for topic_type, relative in DitaValidator._XMLLINT_DTD_FILES.items():
            path = os.path.join(validator.dtd_dir, relative)
            assert os.path.exists(path), (
                f"Missing bundled DTD for {topic_type!r}: {relative}"
            )

    def test_reference_dtds_present(self, validator):
        for topic_type in DitaValidator.DTD_FILES:
            assert validator._dtd_available(topic_type), (
                f"DTD not available for topic type {topic_type!r}"
            )


# ---------------------------------------------------------------------------
# _inject_system_doctype
# ---------------------------------------------------------------------------

class TestInjectSystemDoctype:
    def test_replaces_public_doctype(self, validator):
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
            '<topic id="t"><title>T</title><body/></topic>'
        )
        result = validator._inject_system_doctype(content, "topic", "/path/to/dtd.dtd")
        assert 'SYSTEM "/path/to/dtd.dtd"' in result
        assert 'PUBLIC' not in result

    def test_replaces_system_doctype(self, validator):
        content = (
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE topic SYSTEM "old.dtd">\n'
            '<topic id="t"><title>T</title><body/></topic>'
        )
        result = validator._inject_system_doctype(content, "topic", "/new/path.dtd")
        assert 'SYSTEM "/new/path.dtd"' in result
        assert "old.dtd" not in result

    def test_inserts_doctype_when_absent(self, validator):
        content = '<topic id="t"><title>T</title><body/></topic>'
        result = validator._inject_system_doctype(content, "topic", "/path/dtd.dtd")
        assert '<!DOCTYPE topic SYSTEM "/path/dtd.dtd">' in result

    def test_preserves_xml_declaration_position(self, validator):
        content = '<?xml version="1.0"?>\n<topic id="t"><title>T</title><body/></topic>'
        result = validator._inject_system_doctype(content, "topic", "/dtd.dtd")
        lines = result.strip().splitlines()
        assert lines[0].startswith("<?xml")
        assert lines[1].startswith("<!DOCTYPE")

    def test_uses_correct_topic_type(self, validator):
        content = '<concept id="c"><title>T</title><conbody/></concept>'
        result = validator._inject_system_doctype(content, "concept", "/dtd.dtd")
        assert "<!DOCTYPE concept" in result


# ---------------------------------------------------------------------------
# DTD validation via xmllint
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not DitaValidator._xmllint_available(),
    reason="xmllint not available in this environment",
)
class TestDTDValidation:
    def test_valid_topic_passes(self, validator):
        valid, errors = validator.validate_with_dtd(VALID_TOPIC)
        assert valid is True
        assert errors is None

    def test_valid_topic_with_shortdesc_passes(self, validator):
        valid, errors = validator.validate_with_dtd(VALID_TOPIC_WITH_SHORTDESC)
        assert valid is True
        assert errors is None

    def test_missing_id_attribute_fails(self, validator):
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic>
  <title>Missing ID</title>
  <body><p>text</p></body>
</topic>"""
        valid, errors = validator.validate_with_dtd(content)
        assert valid is False
        assert errors
        assert any("id" in e.lower() for e in errors)

    def test_missing_title_fails(self, validator):
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="t">
  <body><p>No title here</p></body>
</topic>"""
        valid, errors = validator.validate_with_dtd(content)
        assert valid is False
        assert errors

    def test_unknown_element_in_body_fails(self, validator):
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="t">
  <title>Test</title>
  <body>
    <unknowntag>invalid DITA element</unknowntag>
  </body>
</topic>"""
        valid, errors = validator.validate_with_dtd(content)
        assert valid is False
        assert errors
        assert any("unknowntag" in e for e in errors)

    def test_html_element_in_body_fails(self, validator):
        """HTML elements like <span> are not valid DITA."""
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="t">
  <title>Test</title>
  <body>
    <span>html span tag</span>
  </body>
</topic>"""
        valid, errors = validator.validate_with_dtd(content)
        assert valid is False
        assert errors

    def test_inline_element_directly_in_body_fails(self, validator):
        """Inline elements like <b> must be inside a block element, not directly in <body>."""
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="t">
  <title>Test</title>
  <body>
    <b>bold directly in body</b>
  </body>
</topic>"""
        valid, errors = validator.validate_with_dtd(content)
        assert valid is False
        assert errors

    def test_malformed_xml_fails(self, validator):
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<topic id="t">
  <title>Unclosed
  <body><p>text</p></body>
</topic>"""
        valid, errors = validator.validate_with_dtd(content)
        assert valid is False
        assert errors

    def test_auto_detect_topic_type(self, validator):
        """validate_with_dtd auto-detects root element type."""
        valid, errors = validator.validate_with_dtd(VALID_TOPIC)
        assert valid is True

    def test_returns_error_list_not_string(self, validator):
        """Errors must be a list of strings, not a single string."""
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<topic id="t">
  <title>Test</title>
  <body><unknowntag/></body>
</topic>"""
        valid, errors = validator.validate_with_dtd(content)
        assert valid is False
        assert isinstance(errors, list)
        assert all(isinstance(e, str) for e in errors)


# ---------------------------------------------------------------------------
# Fallback to structural validation when xmllint is absent
# ---------------------------------------------------------------------------

class TestStructuralFallback:
    """validate_with_dtd must fall back to structural validation when xmllint is unavailable."""

    def test_falls_back_when_xmllint_unavailable(self, validator):
        with patch.object(DitaValidator, "_xmllint_available", return_value=False):
            # Reset the class-level cache so the mock takes effect
            DitaValidator._XMLLINT_AVAILABLE = None
            with patch.object(validator, "_validate_with_xmllint", return_value=(None, None)):
                valid, errors = validator.validate_with_dtd(VALID_TOPIC)
                # Structural validation should pass for a well-formed topic
                assert valid is True

    def test_structural_validates_valid_topic(self, validator):
        valid, errors = validator.validate_structure(VALID_TOPIC)
        assert valid is True

    def test_structural_catches_missing_id(self, validator):
        content = """\
<?xml version="1.0" encoding="UTF-8"?>
<topic>
  <title>No ID</title>
  <body><p>text</p></body>
</topic>"""
        valid, errors = validator.validate_structure(content)
        assert valid is False
        assert errors
        assert any("id" in e.lower() for e in errors)

    def test_structural_catches_missing_title(self, validator):
        content = '<topic id="t"><body><p>text</p></body></topic>'
        valid, errors = validator.validate_structure(content)
        assert valid is False
        assert errors

    def test_structural_catches_missing_body(self, validator):
        content = '<topic id="t"><title>Title only</title></topic>'
        valid, errors = validator.validate_structure(content)
        assert valid is False
        assert errors

    def test_structural_catches_section_without_title(self, validator):
        content = """\
<topic id="t">
  <title>T</title>
  <body>
    <section><p>No section title</p></section>
  </body>
</topic>"""
        valid, errors = validator.validate_structure(content)
        assert valid is False
        assert any("section" in e.lower() and "title" in e.lower() for e in errors)

    def test_structural_catches_empty_list(self, validator):
        content = """\
<topic id="t">
  <title>T</title>
  <body>
    <ul></ul>
  </body>
</topic>"""
        valid, errors = validator.validate_structure(content)
        assert valid is False
        assert any("li" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# auto_fix_common_issues + validate_with_dtd pipeline
# ---------------------------------------------------------------------------

class TestAutoFixPipeline:
    def test_adds_xml_declaration(self, validator):
        content = '<topic id="t"><title>T</title><body><p>x</p></body></topic>'
        fixed = validator.auto_fix_common_issues(content)
        assert fixed.startswith("<?xml")

    def test_adds_doctype(self, validator):
        content = '<topic id="t"><title>T</title><body><p>x</p></body></topic>'
        fixed = validator.auto_fix_common_issues(content)
        assert "<!DOCTYPE topic" in fixed

    def test_escapes_bare_ampersands(self, validator):
        content = '<topic id="t"><title>T</title><body><p>A &amp; B &amp; C</p></body></topic>'
        fixed = validator.auto_fix_common_issues(content)
        # Already escaped ones must not be double-escaped
        assert "&amp;amp;" not in fixed
        assert "&amp;" in fixed

    def test_fixes_numeric_id(self, validator):
        content = '<topic id="123abc"><title>T</title><body/></topic>'
        fixed = validator.auto_fix_common_issues(content)
        # ID must start with a letter after fixing
        import re
        m = re.search(r'id="([^"]+)"', fixed)
        assert m and m.group(1)[0].isalpha()

    @pytest.mark.skipif(
        not DitaValidator._xmllint_available(),
        reason="xmllint not available",
    )
    def test_fixed_content_passes_dtd_validation(self, validator):
        """Content missing XML decl and DOCTYPE should validate after auto_fix."""
        bare = """\
<topic id="release-notes">
  <title>Release Notes</title>
  <body>
    <section>
      <title>Changes</title>
      <p>Some improvements were made.</p>
    </section>
  </body>
</topic>"""
        fixed = validator.auto_fix_common_issues(bare)
        valid, errors = validator.validate_with_dtd(fixed)
        assert valid is True, f"Errors after auto_fix: {errors}"


# ---------------------------------------------------------------------------
# Regression: validate_with_dtd uses xmllint when available
# ---------------------------------------------------------------------------

class TestValidateWithDTDUsesXmllint:
    def test_xmllint_called_when_available(self, validator):
        """Regression guard: ensure xmllint path is taken, not just structural."""
        with patch.object(
            validator, "_validate_with_xmllint", return_value=(True, None)
        ) as mock_xmllint:
            with patch.object(DitaValidator, "_xmllint_available", return_value=True):
                valid, errors = validator.validate_with_dtd(VALID_TOPIC)
        mock_xmllint.assert_called_once()
        assert valid is True

    def test_structural_called_when_xmllint_returns_none(self, validator):
        """When _validate_with_xmllint returns (None, None), structural is used."""
        with patch.object(
            validator, "_validate_with_xmllint", return_value=(None, None)
        ):
            with patch.object(
                validator, "validate_structure", return_value=(True, None)
            ) as mock_struct:
                valid, errors = validator.validate_with_dtd(VALID_TOPIC)
        mock_struct.assert_called_once()
        assert valid is True
