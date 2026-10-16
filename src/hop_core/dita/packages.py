"""Checking an uploaded DTD package and indexing the document types it defines.

A package is a zip of DITA grammar files — shells (``.dtd``), modules
(``.mod``, ``.ent``) — with an OASIS XML catalog mapping public IDs to files.
:func:`process_package` takes it through six steps, reporting progress as it
goes, and returns a :class:`PackageReport`:

1. **Received** — size checks.
2. **Unpack** — safe extraction: no paths outside the target, file-count and
   size limits.
3. **Find XML catalog** — the catalog nearest the root, following
   ``nextCatalog``; duplicate public IDs are warnings.
4. **Resolve references** — every catalog entry, and every external
   parameter entity a grammar file declares, must point at a file.
5. **Compile** — index the document types: each shell's root element, and
   whether it is a standard OASIS type or a specialization of one, read from
   the ``class`` attributes the modules declare.
6. **Test-parse** — load each shell with xmllint to prove it compiles.

A problem that leaves nothing usable (no catalog, no shells, an unsafe zip)
raises :class:`PackageError`; anything else is a :class:`PackageIssue` warning
that does not block the set from being used.
"""

import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from lxml import etree

from hop_core.dita.grammar import DtdSet, xmllint_profile

STEPS = (
    ("received", "Upload received"),
    ("unpack", "Unpack archive"),
    ("catalog", "Find XML catalog"),
    ("resolve", "Resolve references"),
    ("compile", "Compile grammars"),
    ("test", "Test-parse each document type"),
)

MAX_FILES = 5000
MAX_UNPACKED_BYTES = 500 * 1024 * 1024
GRAMMAR_SUFFIXES = (".dtd", ".mod", ".ent")
_CATALOG_NS = "urn:oasis:names:tc:entity:xmlns:xml:catalog"
_IGNORED_PARTS = ("__MACOSX",)

Progress = Callable[[int, str], None]   # (step index 0-5, detail)


class PackageError(Exception):
    """The package cannot be used at all. ``step`` is the index it failed at."""

    def __init__(self, message: str, step: int, report: Optional["PackageReport"] = None):
        super().__init__(message)
        self.message = message
        self.step = step
        # What was learned before failing — the warnings often explain it.
        self.report = report


@dataclass
class PackageIssue:
    title: str
    detail: str = ""
    file: Optional[str] = None
    line: Optional[int] = None
    severity: str = "warning"


@dataclass
class DocumentType:
    name: str            # "API Reference"
    root: str            # "apiRef"
    public_id: str       # "-//ACME//DTD DITA API Reference//EN"
    shell: str           # path of the shell, relative to the package root
    kind: str            # "base" (an OASIS document type) or "specialized"
    aliases: List[str] = field(default_factory=list)   # every public ID naming this shell
    specializes: Optional[str] = None   # "reference", for a specialization
    parses: bool = True  # False when the test-parse could not load the shell


@dataclass
class PackageReport:
    file_count: int = 0
    grammar_file_count: int = 0
    catalog: Optional[str] = None
    public_id_count: int = 0
    resolved_count: int = 0
    reference_count: int = 0
    based_on: Optional[str] = None
    document_types: List[DocumentType] = field(default_factory=list)
    issues: List[PackageIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def dtd_set(self, root: Path, name: str = "DITA") -> DtdSet:
        """The validation grammar this package provides, unpacked at ``root``.

        Several shells can share a root element (``task`` is the root of Task,
        General Task and Machinery Task). By root, the shell named after it
        wins — ``topic.dtd`` over ``basetopic.dtd`` — and content whose
        DOCTYPE names a public ID is validated against exactly that shell.
        """
        usable = [d for d in self.document_types if d.parses]
        ranked = sorted(usable, key=lambda d: (PurePosixPath(d.shell).stem.lower() != d.root.lower(), d.shell))
        shells: Dict[str, str] = {}
        for doc_type in ranked:
            shells.setdefault(doc_type.root, doc_type.shell)
        public_ids = {alias: d.shell for d in usable for alias in (d.aliases or [d.public_id])}
        return DtdSet(root=root, shells=shells, name=name, public_ids=public_ids,
                      catalog=(root / self.catalog) if self.catalog else None)


# ── 2. Unpack ─────────────────────────────────────────────────────────────────

def _member_path(name: str) -> Optional[PurePosixPath]:
    path = PurePosixPath(name.replace("\\", "/"))
    if not path.parts or any(p in _IGNORED_PARTS for p in path.parts):
        return None
    if path.name.startswith("._") or path.name == ".DS_Store":
        return None
    return path


def unpack(archive: Path, dest: Path, max_files: int = MAX_FILES,
           max_bytes: int = MAX_UNPACKED_BYTES) -> int:
    """Extract ``archive`` into ``dest`` safely; returns the number of files.

    Rejects absolute paths, ``..`` segments and symlinks rather than skipping
    them — a package that tries to write outside its folder is not one to
    half-trust.
    """
    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile:
        raise PackageError("The upload is not a zip file.", 1)
    dest = dest.resolve()
    with zf:
        members = [m for m in zf.infolist() if not m.is_dir() and _member_path(m.filename)]
        if len(members) > max_files:
            raise PackageError(f"The zip holds {len(members)} files; the limit is {max_files}.", 1)
        if sum(m.file_size for m in members) > max_bytes:
            raise PackageError(f"The zip unpacks to more than {max_bytes // (1024 * 1024)} MB.", 1)
        for member in members:
            rel = _member_path(member.filename)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise PackageError(f"The zip contains a symbolic link ({member.filename}).", 1)
            if rel.is_absolute() or ".." in rel.parts:
                raise PackageError(f"The zip contains an unsafe path ({member.filename}).", 1)
            target = (dest / rel.as_posix()).resolve()
            if dest not in target.parents:
                raise PackageError(f"The zip contains an unsafe path ({member.filename}).", 1)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return len(members)


# ── 3. Catalog ────────────────────────────────────────────────────────────────

@dataclass
class _Entry:
    kind: str        # "public" | "system" | "uri"
    key: str         # the public ID, system ID or URI name
    target: Path     # absolute
    file: str        # catalog file, relative to the package root
    line: int


def find_catalog(root: Path) -> Optional[Path]:
    """The catalog nearest the package root (``catalog.xml``, any case)."""
    found = [p for p in root.rglob("*") if p.is_file() and p.name.lower() == "catalog.xml"]
    if not found:
        return None
    return min(found, key=lambda p: (len(p.relative_to(root).parts), str(p)))


def read_catalog(catalog: Path, root: Path, issues: List[PackageIssue]) -> List[_Entry]:
    """Every entry reachable from ``catalog``, following ``nextCatalog``.

    A catalog's own entries come before anything reached through its
    ``nextCatalog`` elements, whatever order they appear in — chained catalogs
    are only consulted when the current one has no match.
    """
    entries: List[_Entry] = []
    seen: set = set()

    def rel(p: Path) -> str:
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return str(p)

    def walk(path: Path) -> None:
        path = path.resolve()
        if path in seen:
            return
        seen.add(path)
        try:
            tree = etree.parse(str(path), etree.XMLParser(resolve_entities=False, no_network=True,
                                                          load_dtd=False))
        except (etree.XMLSyntaxError, OSError) as exc:
            issues.append(PackageIssue("A catalog could not be read", str(exc), rel(path)))
            return

        chained: List[Tuple[Path, int, str]] = []

        def visit(el, base: Path) -> None:
            for child in el:
                if not isinstance(child.tag, str):
                    continue
                name = etree.QName(child).localname
                xml_base = child.get("{http://www.w3.org/XML/1998/namespace}base")
                child_base = (base / xml_base) if xml_base else base
                if name == "group":
                    visit(child, child_base)
                elif name == "nextCatalog":
                    chained.append((child_base / (child.get("catalog") or ""), child.sourceline or 0,
                                    child.get("catalog") or ""))
                elif name in ("public", "system", "uri"):
                    key = child.get({"public": "publicId", "system": "systemId", "uri": "name"}[name])
                    target = child.get("uri")
                    if key and target:
                        entries.append(_Entry(name, key.strip(), (child_base / target).resolve(),
                                              rel(path), child.sourceline or 0))

        root_el = tree.getroot()
        xml_base = root_el.get("{http://www.w3.org/XML/1998/namespace}base")
        visit(root_el, (path.parent / xml_base) if xml_base else path.parent)
        for next_path, line, written in chained:
            if next_path.is_file():
                walk(next_path)
            else:
                issues.append(PackageIssue(
                    "A chained catalog is missing",
                    f"nextCatalog points to {written}, which is not in the zip.",
                    rel(path), line))

    walk(catalog)
    return entries


def _check_duplicates(entries: List[_Entry], issues: List[PackageIssue]) -> Dict[str, _Entry]:
    """First entry per public ID wins, as catalog resolution does."""
    by_id: Dict[str, _Entry] = {}
    for entry in entries:
        if entry.kind != "public":
            continue
        first = by_id.get(entry.key)
        if first is None:
            by_id[entry.key] = entry
        elif first.target != entry.target:
            issues.append(PackageIssue(
                "Public ID listed twice in the catalog",
                f"{entry.key} points to two files. Hop used the first entry, on line {first.line}.",
                entry.file, entry.line))
    return by_id


# ── 4. Resolve ────────────────────────────────────────────────────────────────

_PARAM_ENTITY = re.compile(
    r'<!ENTITY\s+%\s*([\w.:-]+)\s+(?:PUBLIC\s+(["\'])(.*?)\2\s*(?:(["\'])(.*?)\4)?|SYSTEM\s+(["\'])(.*?)\6)',
    re.S,
)


_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _read_grammar(path: Path) -> str:
    """A grammar file with comments blanked out (newlines kept, so line
    numbers still point at the original). DTD comments routinely show
    "typical invocation" examples that are not declarations."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _grammar_files(root: Path) -> List[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in GRAMMAR_SUFFIXES)


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def resolve_references(root: Path, public: Dict[str, _Entry], entries: List[_Entry],
                       issues: List[PackageIssue], progress: Callable[[int, int], None]) -> Tuple[int, int]:
    """Check catalog targets and every external parameter entity.

    Returns ``(resolved, total)`` over the catalog's public IDs, which is the
    count the progress display shows.
    """
    total = len(public)
    resolved = 0
    for index, entry in enumerate(public.values(), 1):
        if entry.target.is_file():
            resolved += 1
        else:
            issues.append(PackageIssue(
                "A catalog entry points to a missing file",
                f"{entry.key} → {entry.target.name}", entry.file, entry.line))
        if index % 25 == 0 or index == total:
            progress(resolved, total)

    for entry in entries:
        if entry.kind == "system" and not entry.target.is_file():
            issues.append(PackageIssue("A catalog entry points to a missing file",
                                       f"{entry.key} → {entry.target.name}", entry.file, entry.line))

    system_ids = {e.key for e in entries if e.kind == "system" and e.target.is_file()}
    texts = {path: _read_grammar(path) for path in _grammar_files(root)}
    # A declaration nothing uses is harmless: SVG's flat DTD, for one, declares
    # module entities for files it inlines instead of shipping.
    used = {name for text in texts.values() for name in re.findall(r"%([\w.:-]+);", text)}
    for path, text in texts.items():
        for m in _PARAM_ENTITY.finditer(text):
            name = m.group(1)
            if name not in used:
                continue
            public_id = m.group(3)
            system_id = m.group(5) if public_id is not None else m.group(7)
            if public_id and public_id in public and public[public_id].target.is_file():
                continue
            if system_id and (system_id in system_ids or (path.parent / system_id).is_file()):
                continue
            issues.append(PackageIssue(
                f"Unresolved parameter entity %{name};",
                "Neither its public ID nor its file can be found, so whatever it declares "
                "isn't available. Documents that use it will fail validation.",
                path.relative_to(root).as_posix(), _line_at(text, m.start())))
    return resolved, total


# ── 5. Compile: index the document types ──────────────────────────────────────

_CLASS_ATTR = re.compile(r'<!ATTLIST\s+([\w.:-]+)\s[^>]*?\bclass\s+CDATA\s+"([^"]+)"', re.S)
_TYPE_CLASS = re.compile(r"^-\s+(?:topic/topic|map/map)\b")
_DITA_VERSION = re.compile(r"DITA\s+(1\.[0-9x])")


def _type_classes(files: Iterable[Path]) -> Dict[str, List[str]]:
    """Element -> its class tokens, for every topic or map type declared."""
    out: Dict[str, List[str]] = {}
    for path in files:
        text = _read_grammar(path)
        for element, value in _CLASS_ATTR.findall(text):
            if _TYPE_CLASS.match(value):
                tokens = value.split()[1:]
                if tokens and tokens[-1].split("/")[-1] == element:
                    out.setdefault(element, tokens)
    return out


def _referenced_files(shell: Path, public: Dict[str, _Entry], depth: int = 0) -> List[Path]:
    """The modules a shell pulls in, following shells that include other
    shells (``glossary.dtd`` is ``glossentry.dtd`` under another name)."""
    text = _read_grammar(shell)
    files: List[Path] = []
    for m in _PARAM_ENTITY.finditer(text):
        public_id = m.group(3)
        system_id = m.group(5) if public_id is not None else m.group(7)
        if public_id and public_id in public and public[public_id].target.is_file():
            target = public[public_id].target
        elif system_id and (shell.parent / system_id).is_file():
            target = (shell.parent / system_id).resolve()
        else:
            continue
        files.append(target)
        if target.suffix.lower() == ".dtd" and depth < 3:
            files.extend(_referenced_files(target, public, depth + 1))
    return files


def _display_name(public_id: str, root: str) -> str:
    m = re.match(r"-//[^/]+//DTD\s+(.*?)//[A-Z]{2}$", public_id)
    name = m.group(1) if m else root
    name = re.sub(r"^DITA\s+", "", name)
    name = re.sub(r"^1\.[0-9x]\s+", "", name)
    return name or root


def _preferred_public_id(ids: List[str]) -> str:
    """Of a shell's aliases, the one without a version number (as authors write)."""
    unversioned = [i for i in ids if not re.search(r"DITA\s+1\.[0-9x]\s", i)]
    return min(unversioned or ids, key=len)


def index_document_types(root: Path, public: Dict[str, _Entry],
                         issues: List[PackageIssue]) -> Tuple[List[DocumentType], Optional[str]]:
    shells: Dict[Path, List[str]] = {}
    for public_id, entry in public.items():
        if "//DTD " in public_id and entry.target.is_file() and entry.target.suffix.lower() == ".dtd":
            shells.setdefault(entry.target, []).append(public_id)

    versions = [v for ids in shells.values() for i in ids for v in _DITA_VERSION.findall(i)]
    based_on = f"DITA {max(v for v in versions if v != '1.x')}" if any(v != "1.x" for v in versions) else None

    document_types: List[DocumentType] = []
    for shell, ids in sorted(shells.items(), key=lambda kv: str(kv[0])):
        classes = _type_classes(_referenced_files(shell, public))
        if not classes and re.search(r"<!ELEMENT\s", _read_grammar(shell)):
            continue  # a standalone, non-topic grammar such as DITAVAL
        if not classes:
            issues.append(PackageIssue(
                "A shell defines no topic or map type",
                "None of the modules it includes declares a topic or map type, so it was skipped.",
                shell.relative_to(root).as_posix()))
            continue
        stem = shell.stem.lower()
        if re.search(r"<!ELEMENT\s+dita\s", _read_grammar(shell)):
            # A composite shell: <dita> wraps any number of topics.
            root_element = "dita"
        else:
            root_element = next((e for e in classes if e.lower() == stem), None)
        if root_element is None:
            # The most specialized type the shell integrates is its document type.
            root_element = max(classes, key=lambda e: len(classes[e]))
        tokens = classes.get(root_element, [])
        public_id = _preferred_public_id(ids)
        standard = public_id.startswith("-//OASIS//")
        parent = tokens[-2].split("/")[-1] if len(tokens) >= 2 else None
        document_types.append(DocumentType(
            name=_display_name(public_id, root_element),
            root=root_element,
            public_id=public_id,
            shell=shell.relative_to(root).as_posix(),
            kind="base" if standard else "specialized",
            specializes=None if standard else parent,
            aliases=sorted(ids),
        ))
    return document_types, based_on


# ── 6. Test-parse ─────────────────────────────────────────────────────────────

_LOAD_FAILURE = re.compile(
    r"parser error|failed to load|entity reference loop|amplification|Could not load|"
    r"No declaration for element (\S+)",
)


def test_parse(root: Path, catalog: Optional[Path], document_types: List[DocumentType],
               issues: List[PackageIssue], progress: Callable[[int, int], None]) -> bool:
    """Load every shell with xmllint. Returns False when xmllint can't run here."""
    profile = xmllint_profile()
    if profile is None or not profile.usable:
        issues.append(PackageIssue(
            "Document types were not test-parsed",
            "xmllint is not available on this server"
            + (f" ({profile.reason})" if profile and profile.reason else "")
            + ", so the shells were indexed but not loaded. Validation falls back to structural checks."))
        return False

    env = dict(os.environ)
    args = ["xmllint", "--noout", "--valid", *profile.args]
    if catalog is not None:
        env["XML_CATALOG_FILES"] = catalog.resolve().as_uri()
        args.append("--catalogs")
    else:
        args.append("--nocatalogs")

    with tempfile.TemporaryDirectory() as tmp:
        for index, doc_type in enumerate(document_types, 1):
            sample = Path(tmp) / f"{doc_type.root}.xml"
            shell = (root / doc_type.shell).resolve()
            sample.write_text(
                f'<!DOCTYPE {doc_type.root} SYSTEM "{shell.as_uri()}">\n<{doc_type.root} id="sample"/>\n',
                encoding="utf-8")
            result = subprocess.run([*args, str(sample)], capture_output=True, text=True,
                                    timeout=60, env=env)
            # A bare root breaks content models — expected. Anything that means
            # the grammar itself did not load is not.
            failures = [line for line in result.stderr.splitlines() if _LOAD_FAILURE.search(line)]
            if failures:
                doc_type.parses = False
                issues.append(PackageIssue(
                    f"Document type {doc_type.name} could not be loaded",
                    failures[0].replace(str(Path(tmp)) + "/", "").replace(str(root.resolve()) + "/", "")[:300],
                    doc_type.shell))
            progress(index, len(document_types))
    return True


# ── The pipeline ──────────────────────────────────────────────────────────────

def process_package(archive: Path, dest: Path, progress: Optional[Progress] = None) -> PackageReport:
    """Run all six steps on ``archive``, unpacking it into ``dest``.

    Raises :class:`PackageError` (carrying the partial report) when the
    package leaves nothing usable.
    """
    report = PackageReport()
    try:
        return _process(archive, dest, report, progress)
    except PackageError as exc:
        exc.report = report
        raise


def _process(archive: Path, dest: Path, report: PackageReport, progress: Optional[Progress]) -> PackageReport:
    say = progress or (lambda step, detail: None)
    size = archive.stat().st_size
    say(0, f"{size / (1024 * 1024):.1f} MB")

    report.file_count = unpack(archive, dest)
    grammar = _grammar_files(dest)
    report.grammar_file_count = len(grammar)
    if not grammar:
        raise PackageError("No .dtd, .mod or .ent files found in the zip.", 1)
    say(1, f"{report.file_count} files: {len(grammar)} grammar files")

    catalog = find_catalog(dest)
    if catalog is None:
        raise PackageError("No XML catalog found in the zip.", 2)
    report.catalog = catalog.relative_to(dest).as_posix()
    entries = read_catalog(catalog, dest, report.issues)
    public = _check_duplicates(entries, report.issues)
    report.public_id_count = len(public)
    if not public:
        raise PackageError("The XML catalog maps no public IDs.", 2)
    say(2, f"{report.catalog} · {report.public_id_count} public IDs")

    report.resolved_count, report.reference_count = resolve_references(
        dest, public, entries, report.issues,
        lambda done, total: say(3, f"{done} of {total} resolved"))
    say(3, f"{report.resolved_count} of {report.reference_count} resolved")

    report.document_types, report.based_on = index_document_types(dest, public, report.issues)
    if not report.document_types:
        raise PackageError("The catalog lists no document-type shells (public IDs containing \"//DTD\").", 4)
    specialized = sum(1 for d in report.document_types if d.kind == "specialized")
    say(4, f"{len(report.document_types)} document types · {specialized} specialized")

    test_parse(dest, catalog, report.document_types, report.issues,
               lambda done, total: say(5, f"{done} of {total} parsed"))
    if not any(d.parses for d in report.document_types):
        raise PackageError("None of the document types could be loaded. See the warnings for why.", 5)
    say(5, f"{sum(d.parses for d in report.document_types)} of {len(report.document_types)} load")
    return report
