"""Builders for DTD package zips used by the DTD-set tests.

``oasis_package`` zips the bundled OASIS DITA 1.3 grammar the way a customer
would upload it. ``acme_package`` adds a genuine specialization — ``apiRef``,
a specialization of ``reference`` — whose shell lives in another folder and
reaches the OASIS modules only through the catalog, as real packages do.
With ``problems=True`` it also carries the two warnings the admin UI shows:
an unresolvable domain entity and a public ID listed twice.
"""

import shutil
import zipfile
from pathlib import Path

from hop_core.dita.grammar import DtdSet

OASIS_DTD = DtdSet.oasis_dita_1_3().root / "dtd"

API_REF_MOD = """<!-- Acme API reference: a specialization of reference. -->
<!ENTITY % apiRef "apiRef">
<!ENTITY % apiRef.content
  "((%title;), (%titlealts;)?, (%abstract; | %shortdesc;)?, (%prolog;)?, (%refbody;)?, (%related-links;)?)">
<!ENTITY % apiRef.attributes
  "id ID #REQUIRED %conref-atts; %select-atts; %localization-atts; outputclass CDATA #IMPLIED">
<!ELEMENT apiRef %apiRef.content;>
<!ATTLIST apiRef %apiRef.attributes; %arch-atts; domains CDATA "&included-domains;">
<!ATTLIST apiRef %global-atts; class CDATA "- topic/topic reference/reference apiRef/apiRef ">
"""

HAZARD_EXTRAS = """<!-- Acme extras. The hazard domain file was never added to the package. -->
<!ENTITY % acme-hazard-d-dec
  PUBLIC "-//ACME//ENTITIES DITA Hazard Domain//EN"
         "acmeHazardDomain.ent"
>%acme-hazard-d-dec;
"""


def _zip(source: Path, archive: Path) -> Path:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(source).as_posix())
    return archive


def oasis_package(tmp: Path) -> Path:
    src = tmp / "oasis-src"
    shutil.copytree(OASIS_DTD, src / "dtd")
    return _zip(src, tmp / "oasis.zip")


def acme_package(tmp: Path, problems: bool = True) -> Path:
    src = tmp / "acme-src"
    shutil.copytree(OASIS_DTD, src / "dtd")
    acme = src / "acme"
    acme.mkdir()
    shell = (OASIS_DTD / "technicalContent/dtd/reference.dtd").read_text(encoding="utf-8")
    shell = shell.replace(
        ">%reference-type;",
        '>%reference-type;\n\n<!ENTITY % apiRef-type\n'
        '  PUBLIC "-//ACME//ELEMENTS DITA API Reference//EN"\n         "apiRef.mod"\n>%apiRef-type;',
        1,
    )
    (acme / "apiRef.dtd").write_text(shell, encoding="utf-8")
    (acme / "apiRef.mod").write_text(API_REF_MOD, encoding="utf-8")
    entries = [
        '  <public publicId="-//ACME//DTD DITA API Reference//EN" uri="acme/apiRef.dtd"/>',
        '  <public publicId="-//ACME//ELEMENTS DITA API Reference//EN" uri="acme/apiRef.mod"/>',
    ]
    if problems:
        (acme / "acmeExtras.ent").write_text(HAZARD_EXTRAS, encoding="utf-8")
        (acme / "apiRef-old.mod").write_text(API_REF_MOD, encoding="utf-8")
        entries.append('  <public publicId="-//ACME//ELEMENTS DITA API Reference//EN" uri="acme/apiRef-old.mod"/>')
    (src / "catalog.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">\n'
        + "\n".join(entries)
        + '\n  <nextCatalog catalog="dtd/catalog.xml"/>\n</catalog>\n',
        encoding="utf-8",
    )
    return _zip(src, tmp / "acme.zip")
