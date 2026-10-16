"""DTD sets, and how to run xmllint against them.

A :class:`DtdSet` is a directory of DITA grammar files plus a map from root
element to the *document-type shell* that validates it. hop-core bundles the
OASIS DITA 1.3 technical-content set; an organization's own set (a
specialization, a constrained shell) is just another ``DtdSet`` pointing at a
different directory. Shells are used exactly as they are — nothing is
generated or rewritten — so an uploaded set validates the way its authors
wrote it.

What the installed libxml2 needs to load DITA grammar varies by version,
measured against every bundled shell:

- **< 2.11**: its entity-loop heuristic misfires on the SVG domain
  ("Detected an entity reference loop" in ``svgDomain.mod``). ``--huge`` turns
  the heuristic off and the full shells validate.
- **2.11**: caps entity amplification below what DITA needs, and its xmllint
  has no option to raise the cap — ``--huge`` does not lift it. DTD validation
  is impossible there; callers fall back to structural checks.
- **≥ 2.12**: same cap, but ``--max-ampl`` raises it (DITA needs about 7×).
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)

_BUNDLED_ROOT = Path(__file__).parent / "resources" / "org.oasis-open.dita.v1_3"

# Root element -> shell, for the bundled OASIS DITA 1.3 technical content.
_OASIS_SHELLS: Dict[str, str] = {
    "topic": "dtd/technicalContent/dtd/topic.dtd",
    "concept": "dtd/technicalContent/dtd/concept.dtd",
    "task": "dtd/technicalContent/dtd/task.dtd",
    "reference": "dtd/technicalContent/dtd/reference.dtd",
    "troubleshooting": "dtd/technicalContent/dtd/troubleshooting.dtd",
    "glossentry": "dtd/technicalContent/dtd/glossentry.dtd",
    "glossgroup": "dtd/technicalContent/dtd/glossgroup.dtd",
}

# The OASIS shells need about 7x; 20 leaves room for larger specializations
# while still stopping a runaway expansion.
MAX_AMPLIFICATION = 20


@dataclass(frozen=True)
class DtdSet:
    """A directory of DITA grammar files and the shell for each root element."""

    root: Path
    shells: Mapping[str, str]
    name: str = "DITA"
    # An OASIS XML catalog resolving the public IDs the shells use. Uploaded
    # sets rely on one; the bundled set resolves by relative path and has none.
    catalog: Optional[Path] = None
    # Public ID -> shell, so content whose DOCTYPE names one is validated
    # against exactly that shell rather than whichever shares its root.
    public_ids: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def oasis_dita_1_3(cls, root: Optional[Path] = None) -> "DtdSet":
        """The OASIS DITA 1.3 technical-content shells bundled with hop-core."""
        return cls(root=Path(root or _BUNDLED_ROOT), shells=dict(_OASIS_SHELLS), name="OASIS DITA 1.3")

    def shell_path(self, root_element: str) -> Optional[Path]:
        """The shell DTD for ``root_element``, or None if the set has none
        (or its file is missing)."""
        relative = self.shells.get(root_element)
        if relative is None:
            return None
        path = (Path(self.root) / relative).resolve()
        return path if path.is_file() else None

    def shell_for_public_id(self, public_id: str) -> Optional[Path]:
        relative = self.public_ids.get(public_id)
        if relative is None:
            return None
        path = (Path(self.root) / relative).resolve()
        return path if path.is_file() else None


@dataclass(frozen=True)
class XmllintProfile:
    """How to run the installed xmllint against DITA grammar."""

    libxml_version: int  # e.g. 21502 for 2.15.2
    args: List[str] = field(default_factory=list)
    usable: bool = True
    reason: str = ""

    @classmethod
    def for_version(cls, version: int) -> "XmllintProfile":
        if version >= 21200:
            return cls(version, ["--max-ampl", str(MAX_AMPLIFICATION)])
        if version >= 21100:
            return cls(version, usable=False, reason=(
                "libxml2 2.11 caps entity amplification below what the DITA DTDs need "
                "and its xmllint cannot raise the cap; use libxml2 2.10 or earlier, or 2.12 or later"
            ))
        return cls(version, ["--huge"])


_profile_cache: Dict[str, Optional[XmllintProfile]] = {}


def xmllint_profile() -> Optional[XmllintProfile]:
    """The installed xmllint's profile, or None when xmllint is not installed."""
    if "profile" not in _profile_cache:
        try:
            result = subprocess.run(["xmllint", "--version"], capture_output=True, text=True, timeout=5)
            match = re.search(r"libxml version (\d+)", result.stderr + result.stdout)
            profile = XmllintProfile.for_version(int(match.group(1)) if match else 0)
            if not profile.usable:
                logger.warning("xmllint cannot validate DITA here: %s", profile.reason)
            _profile_cache["profile"] = profile
        except (FileNotFoundError, subprocess.TimeoutExpired):
            _profile_cache["profile"] = None
    return _profile_cache["profile"]
