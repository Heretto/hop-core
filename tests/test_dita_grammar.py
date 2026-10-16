"""DTD validation uses each root element's full technical-content shell, on
every libxml2 that can load DITA grammar, and any DtdSet — not just the
bundled one."""

from pathlib import Path
from unittest.mock import patch

import pytest

from hop_core.dita.grammar import DtdSet, XmllintProfile
from hop_core.dita.validator import DitaValidator

needs_xmllint = pytest.mark.skipif(
    not DitaValidator._xmllint_available(),
    reason="no xmllint able to load DITA grammar in this environment",
)


@pytest.fixture
def validator():
    return DitaValidator()


# ── The reported bug: topics were validated against the base DTD ──────────────

DOMAIN_INLINES = {
    # element: (domain, fragment)
    "codeph": ("programming", "<p>a unique topic <codeph>id</codeph> on the root</p>"),
    "codeblock": ("programming", "<codeblock>x = 1</codeblock>"),
    "uicontrol": ("ui", "<p>Click <uicontrol>Save</uicontrol>.</p>"),
    "filepath": ("software", "<p>Edit <filepath>/etc/hosts</filepath>.</p>"),
    "cmdname": ("software", "<p>Run <cmdname>ls</cmdname>.</p>"),
}


@needs_xmllint
@pytest.mark.parametrize("element", sorted(DOMAIN_INLINES))
def test_topic_accepts_technical_content_domains(validator, element):
    _, fragment = DOMAIN_INLINES[element]
    valid, errors = validator.validate_with_dtd(
        f'<topic id="t"><title>T</title><body>{fragment}</body></topic>')
    assert valid, errors


def test_topic_is_validated_against_the_technical_content_shell(validator):
    """What DTD_FILES claims is what xmllint gets — no silent base fallback."""
    shell = validator._dtd_path_for_xmllint("topic")
    assert shell.endswith("dtd/technicalContent/dtd/topic.dtd")
    assert shell == str(validator.dtd_set.root.resolve() / validator.DTD_FILES["topic"])


# ── Every root element against its own shell ──────────────────────────────────

VALID = {
    "topic": '<topic id="t"><title>T</title><body><p><codeph>x</codeph></p></body></topic>',
    "concept": '<concept id="c"><title>C</title><conbody><p><uicontrol>u</uicontrol></p></conbody></concept>',
    "task": '<task id="k"><title>K</title><taskbody><steps><step><cmd>Run <cmdname>ls</cmdname></cmd></step></steps></taskbody></task>',
    "reference": '<reference id="r"><title>R</title><refbody><section><p><filepath>/x</filepath></p></section></refbody></reference>',
    "troubleshooting": '<troubleshooting id="t"><title>T</title><troublebody><condition><p>c</p></condition>'
                       '<troubleSolution><cause><p>x</p></cause></troubleSolution></troublebody></troubleshooting>',
    "glossentry": '<glossentry id="g"><glossterm>T</glossterm><glossdef>D <codeph>x</codeph></glossdef></glossentry>',
    "glossgroup": '<glossgroup id="gg"><title>G</title><glossentry id="g"><glossterm>T</glossterm>'
                  '<glossdef>D</glossdef></glossentry></glossgroup>',
}


@needs_xmllint
@pytest.mark.parametrize("root", sorted(VALID))
def test_each_root_validates_against_its_own_shell(validator, root):
    valid, errors = validator.validate_with_dtd(VALID[root])
    assert valid, errors
    assert validator._dtd_path_for_xmllint(root).endswith(f"technicalContent/dtd/{root}.dtd")


@needs_xmllint
@pytest.mark.parametrize("root", sorted(VALID))
def test_each_root_still_rejects_undeclared_elements(validator, root):
    # Put an undeclared element inside the first block that allows content.
    anchor = next(a for a in ("<p>", "<cmd>", "<glossdef>") if a in VALID[root])
    broken = VALID[root].replace(anchor, anchor + "<bogus>x</bogus>", 1)
    valid, errors = validator.validate_with_dtd(broken)
    assert not valid
    assert any("bogus" in e for e in errors)


# ── libxml2 versions ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("version,args,usable", [
    (20914, ["--huge"], True),             # Debian bookworm: loop heuristic misfires on SVG
    (21004, ["--huge"], True),
    (21108, [], False),                    # 2.11: amplification cap, no way to raise it
    (21210, ["--max-ampl", "20"], True),
    (21502, ["--max-ampl", "20"], True),
])
def test_profile_per_libxml_version(version, args, usable):
    profile = XmllintProfile.for_version(version)
    assert profile.args == args and profile.usable is usable


def test_unusable_xmllint_falls_back_to_structural_validation(validator):
    with patch("hop_core.dita.validator.xmllint_profile", return_value=XmllintProfile.for_version(21108)):
        valid, errors = validator.validate_with_dtd(VALID["topic"])
    assert valid, errors  # structural checks pass a well-formed topic


@needs_xmllint
def test_runs_xmllint_with_the_profile_and_without_system_catalogs(validator):
    with patch("hop_core.dita.validator.subprocess.run", wraps=__import__("subprocess").run) as run:
        validator.validate_with_dtd(VALID["topic"])
    args = run.call_args[0][0]
    assert args[:2] == ["xmllint", "--nocatalogs"] and "--valid" in args


# ── Other DTD sets (the seam custom uploads will use) ─────────────────────────

CUSTOM_SHELL = """<!ELEMENT topic (title, body)>
<!ATTLIST topic id ID #REQUIRED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT body (note)*>
<!ELEMENT note (#PCDATA)>
"""


@needs_xmllint
def test_validates_against_a_supplied_dtd_set(tmp_path: Path):
    (tmp_path / "shells").mkdir()
    (tmp_path / "shells" / "mytopic.dtd").write_text(CUSTOM_SHELL)
    custom = DitaValidator(dtd_set=DtdSet(root=tmp_path, shells={"topic": "shells/mytopic.dtd"}, name="Custom"))

    ok, errors = custom.validate_with_dtd('<topic id="t"><title>T</title><body><note>n</note></body></topic>')
    assert ok, errors
    # A <p> is valid DITA, but not in this grammar — so the custom set is what ran.
    ok, errors = custom.validate_with_dtd('<topic id="t"><title>T</title><body><p>x</p></body></topic>')
    assert not ok and any("p" in e for e in errors)
    assert custom.DTD_FILES == {"topic": "shells/mytopic.dtd"}


def test_dtd_dir_still_selects_a_copy_of_the_bundled_layout():
    bundled = DtdSet.oasis_dita_1_3().root
    v = DitaValidator(dtd_dir=bundled)
    assert v.dtd_set.root == bundled and v._dtd_available("concept")
