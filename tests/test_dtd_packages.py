"""Processing uploaded DTD packages: unpacking safely, reading the catalog,
resolving references, indexing document types, and test-parsing them."""

import io
import stat
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from hop_core.dita.grammar import XmllintProfile
from hop_core.dita.packages import STEPS, PackageError, process_package, unpack
from hop_core.dita.validator import DitaValidator
from tests.fixtures.dtd_packages import acme_package, oasis_package

needs_xmllint = pytest.mark.skipif(
    not DitaValidator._xmllint_available(), reason="no xmllint able to load DITA grammar here")


def zip_of(tmp: Path, files: dict, name="pkg.zip", symlink=None) -> Path:
    archive = tmp / name
    with zipfile.ZipFile(archive, "w") as zf:
        for path, text in files.items():
            zf.writestr(path, text)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    return archive


CATALOG = '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">{}</catalog>'


def package_issues(report):
    """The package's own issues — not the note that this server can't test-parse."""
    return [i for i in report.issues if i.title != "Document types were not test-parsed"]


# ── Real packages ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def oasis(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("oasis")
    steps = []
    report = process_package(oasis_package(tmp), tmp / "unpacked", lambda i, d: steps.append((i, d)))
    return report, tmp / "unpacked", steps


@pytest.fixture(scope="module")
def acme(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("acme")
    return process_package(acme_package(tmp), tmp / "unpacked"), tmp / "unpacked"


class TestOasisPackage:
    def test_indexes_every_oasis_document_type_without_warnings(self, oasis):
        report, _, _ = oasis
        assert report.based_on == "DITA 1.3"
        assert package_issues(report) == []
        assert report.public_id_count == report.resolved_count == report.reference_count
        roots = {d.root for d in report.document_types}
        assert {"topic", "concept", "task", "reference", "glossentry", "map", "bookmap", "dita"} <= roots
        assert all(d.kind == "base" for d in report.document_types)

    def test_display_names_and_public_ids(self, oasis):
        concept = next(d for d in oasis[0].document_types if d.root == "concept")
        assert concept.name == "Concept"
        assert concept.public_id == "-//OASIS//DTD DITA Concept//EN"   # the unversioned alias
        assert "-//OASIS//DTD DITA 1.3 Concept//EN" in concept.aliases

    def test_composite_shell_has_the_dita_root(self, oasis):
        assert next(d for d in oasis[0].document_types if d.name == "Composite").root == "dita"

    def test_shared_roots_prefer_the_shell_named_after_them(self, oasis):
        report, root, _ = oasis
        shells = report.dtd_set(root).shells
        assert shells["topic"].endswith("technicalContent/dtd/topic.dtd")   # not basetopic.dtd
        assert shells["task"].endswith("technicalContent/dtd/task.dtd")     # not generalTask/machineryTask

    def test_progress_runs_through_all_six_steps(self, oasis):
        steps = oasis[2]
        assert sorted({i for i, _ in steps}) == list(range(len(STEPS)))
        assert [i for i, _ in steps] == sorted(i for i, _ in steps)

    @needs_xmllint
    def test_every_document_type_loads(self, oasis):
        assert all(d.parses for d in oasis[0].document_types)

    @needs_xmllint
    def test_validates_with_the_package(self, oasis):
        report, root, _ = oasis
        v = DitaValidator(dtd_set=report.dtd_set(root))
        assert v.validate_with_dtd('<topic id="t"><title>T</title><body><p><codeph>x</codeph></p></body></topic>')[0]
        assert v.validate_with_dtd('<map><title>M</title><topicref href="a.dita"/></map>')[0]
        assert v.validate_with_dtd('<dita><topic id="a"><title>A</title></topic></dita>')[0]

    @needs_xmllint
    def test_doctype_public_id_selects_its_exact_shell(self, oasis):
        report, root, _ = oasis
        v = DitaValidator(dtd_set=report.dtd_set(root))
        body = '<topic id="t"><title>T</title><body><p><codeph>x</codeph></p></body></topic>'
        assert v.validate_with_dtd(body)[0]
        # The Base Topic shell has no programming domain, so the same content fails there.
        ok, errors = v.validate_with_dtd(
            '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Base Topic//EN" "basetopic.dtd">' + body)
        assert not ok and any("codeph" in e for e in errors)


class TestSpecializedPackage:
    def test_specialization_is_indexed_with_its_parent(self, acme):
        report, _ = acme
        api = next(d for d in report.document_types if d.root == "apiRef")
        assert (api.name, api.kind, api.specializes) == ("API Reference", "specialized", "reference")
        assert api.public_id == "-//ACME//DTD DITA API Reference//EN"

    def test_reports_the_two_problems_with_file_and_line(self, acme):
        issues = {i.title: i for i in package_issues(acme[0])}
        assert set(issues) == {"Public ID listed twice in the catalog",
                               "Unresolved parameter entity %acme-hazard-d-dec;"}
        dup = issues["Public ID listed twice in the catalog"]
        assert (dup.file, dup.line) == ("catalog.xml", 5) and "first entry, on line 4" in dup.detail
        hazard = issues["Unresolved parameter entity %acme-hazard-d-dec;"]
        assert (hazard.file, hazard.line) == ("acme/acmeExtras.ent", 2)

    @needs_xmllint
    def test_specialized_content_validates_through_the_catalog(self, acme):
        report, root = acme
        v = DitaValidator(dtd_set=report.dtd_set(root))
        assert v.validate_with_dtd(
            '<apiRef id="a"><title>API</title><refbody><section><p><codeph>get()</codeph></p></section></refbody></apiRef>')[0]
        ok, _ = v.validate_with_dtd('<apiRef id="a"><title>API</title><conbody/></apiRef>')
        assert not ok


# ── Unpacking ─────────────────────────────────────────────────────────────────

class TestUnpack:
    @pytest.mark.parametrize("name", ["../evil.dtd", "/etc/evil.dtd", "a/../../evil.dtd"])
    def test_rejects_paths_outside_the_package(self, tmp_path, name):
        with pytest.raises(PackageError, match="unsafe path") as exc:
            unpack(zip_of(tmp_path, {name: "x"}), tmp_path / "out")
        assert exc.value.step == 1
        assert not (tmp_path / "evil.dtd").exists()

    def test_rejects_symlinks(self, tmp_path):
        with pytest.raises(PackageError, match="symbolic link"):
            unpack(zip_of(tmp_path, {"a.dtd": "x"}, symlink="link.dtd"), tmp_path / "out")

    def test_rejects_too_many_files(self, tmp_path):
        with pytest.raises(PackageError, match="limit is 2"):
            unpack(zip_of(tmp_path, {f"{i}.dtd": "x" for i in range(3)}), tmp_path / "out", max_files=2)

    def test_rejects_oversized_contents(self, tmp_path):
        with pytest.raises(PackageError, match="unpacks to more than"):
            unpack(zip_of(tmp_path, {"a.dtd": "x" * 2_000_000}), tmp_path / "out", max_bytes=1_000_000)

    def test_skips_macos_clutter(self, tmp_path):
        count = unpack(zip_of(tmp_path, {"a.dtd": "x", "__MACOSX/._a.dtd": "x", ".DS_Store": "x"}),
                       tmp_path / "out")
        assert count == 1

    def test_not_a_zip(self, tmp_path):
        bad = tmp_path / "x.zip"
        bad.write_bytes(b"not a zip")
        with pytest.raises(PackageError, match="not a zip"):
            unpack(bad, tmp_path / "out")


# ── Whole-package failures and warnings ───────────────────────────────────────

class TestPipeline:
    def test_no_grammar_files(self, tmp_path):
        with pytest.raises(PackageError, match=r"No \.dtd") as exc:
            process_package(zip_of(tmp_path, {"readme.txt": "hi"}), tmp_path / "out")
        assert exc.value.step == 1

    def test_no_catalog_fails_at_the_catalog_step_with_the_partial_report(self, tmp_path):
        with pytest.raises(PackageError, match="No XML catalog found in the zip.") as exc:
            process_package(zip_of(tmp_path, {"a.dtd": "<!ELEMENT a EMPTY>"}), tmp_path / "out")
        assert exc.value.step == 2
        assert exc.value.report.file_count == 1

    def test_missing_chained_catalog_is_a_warning(self, tmp_path):
        files = {"catalog.xml": CATALOG.format(
                     '<public publicId="-//X//DTD DITA Thing//EN" uri="thing.dtd"/>'
                     '<nextCatalog catalog="missing/catalog.xml"/>'),
                 "thing.dtd": "<!ELEMENT thing EMPTY>"}
        with pytest.raises(PackageError) as exc:   # no topic types: fails at compile
            process_package(zip_of(tmp_path, files), tmp_path / "out")
        assert any(i.title == "A chained catalog is missing" for i in exc.value.report.issues)

    def test_own_entries_win_over_chained_catalogs(self, tmp_path):
        from hop_core.dita.packages import _check_duplicates, read_catalog
        root = tmp_path / "pkg"
        (root / "sub").mkdir(parents=True)
        (root / "catalog.xml").write_text(CATALOG.format(
            '<nextCatalog catalog="sub/catalog.xml"/><public publicId="-//X//ELEMENTS A//EN" uri="mine.mod"/>'))
        (root / "sub" / "catalog.xml").write_text(CATALOG.format(
            '<public publicId="-//X//ELEMENTS A//EN" uri="theirs.mod"/>'))
        issues = []
        public = _check_duplicates(read_catalog(root / "catalog.xml", root, issues), issues)
        assert public["-//X//ELEMENTS A//EN"].target.name == "mine.mod"

    def test_commented_and_unused_declarations_are_not_warnings(self, tmp_path):
        from hop_core.dita.packages import resolve_references
        root = tmp_path / "pkg"
        root.mkdir()
        (root / "a.ent").write_text(
            '<!-- Typical invocation:\n <!ENTITY % shown PUBLIC "-//X//ENTITIES Shown//EN" "shown.ent">\n%shown; -->\n'
            '<!ENTITY % unused PUBLIC "-//X//ENTITIES Unused//EN" "unused.ent">\n'
            '<!ENTITY % used PUBLIC "-//X//ENTITIES Used//EN" "used.ent">\n%used;\n')
        issues = []
        resolve_references(root, {}, [], issues, lambda done, total: None)
        assert [i.title for i in issues] == ["Unresolved parameter entity %used;"]
        assert issues[0].line == 5   # comments keep their line breaks

    @needs_xmllint
    def test_shell_that_cannot_load_is_marked_and_warned(self, tmp_path):
        src = acme_package(tmp_path, problems=False)
        broken = tmp_path / "broken.zip"
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(broken, "w") as zout:
            for item in zin.infolist():
                if item.filename != "acme/apiRef.mod":   # the shell's own module goes missing
                    zout.writestr(item, zin.read(item.filename))
            zout.writestr("acme/apiRef.mod", '<!ENTITY % apiRef "apiRef">\n<!ATTLIST apiRef %global-atts; '
                                             'class CDATA "- topic/topic reference/reference apiRef/apiRef ">\n'
                                             '<!ELEMENT apiRef (%undefined-entity;)>\n')
        report = process_package(broken, tmp_path / "out")
        api = next(d for d in report.document_types if d.root == "apiRef")
        assert api.parses is False
        assert any(i.title == "Document type API Reference could not be loaded" for i in report.issues)
        assert "apiRef" not in report.dtd_set(tmp_path / "out").shells

    def test_without_xmllint_types_are_indexed_but_not_test_parsed(self, tmp_path):
        with patch("hop_core.dita.packages.xmllint_profile", return_value=None):
            report = process_package(acme_package(tmp_path, problems=False), tmp_path / "out")
        assert any(i.title == "Document types were not test-parsed" for i in report.issues)
        assert all(d.parses for d in report.document_types)

    def test_unusable_xmllint_says_why(self, tmp_path):
        with patch("hop_core.dita.packages.xmllint_profile", return_value=XmllintProfile.for_version(21108)):
            report = process_package(acme_package(tmp_path, problems=False), tmp_path / "out")
        warning = next(i for i in report.issues if i.title == "Document types were not test-parsed")
        assert "2.11" in warning.detail
