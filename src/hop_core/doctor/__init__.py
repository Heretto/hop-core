"""hop-doctor — audit an application built on hop-core for known integration failures.

Run it from the root of a consuming project:

    hop-doctor              # human-readable report
    hop-doctor --json       # machine-readable, for agents and CI

Every check corresponds to an item in AGENTS.md and to a failure that has
actually happened in a real hop-core app. The checks are deliberately
conservative: FAIL means "this is broken", WARN means "this looks wrong but I
cannot prove it from the repository alone", and SKIP means "not applicable or
not determinable here". A false FAIL is worse than a missing check, because
callers act on it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

__all__ = [
    "Severity",
    "Finding",
    "Project",
    "discover",
    "run_checks",
    "main",
]


class Severity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class Finding:
    """One check result.

    `check` is a stable dotted id (e.g. "deps.npm") so callers can match on it
    without parsing prose. `location` is "path:line" or "path" when known.
    """

    check: str
    severity: Severity
    summary: str
    detail: str = ""
    fix: str = ""
    location: str | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class Project:
    """Where the interesting parts of a consuming project live.

    Layouts vary, so every path is optional; checks SKIP rather than FAIL when
    the thing they inspect is absent.
    """

    root: Path
    backend: Path | None = None
    frontend: Path | None = None


_BACKEND_MARKERS = ("requirements.txt", "settings.py", "pyproject.toml")
_BACKEND_CANDIDATES = (".", "backend", "api", "server", "app")
_FRONTEND_CANDIDATES = (".", "frontend", "web", "client", "ui")


def discover(root: Path, backend: Path | None = None, frontend: Path | None = None) -> Project:
    """Locate the backend and frontend directories under `root`.

    Explicit overrides win. Otherwise the backend is the first candidate holding
    a recognisable Python marker, and the frontend is the first holding
    angular.json (falling back to a one-level-deep search).
    """
    root = root.resolve()

    if backend is None:
        for rel in _BACKEND_CANDIDATES:
            cand = root / rel
            if cand.is_dir() and any((cand / m).is_file() for m in _BACKEND_MARKERS):
                backend = cand
                break

    if frontend is None:
        for rel in _FRONTEND_CANDIDATES:
            cand = root / rel
            if cand.is_dir() and (cand / "angular.json").is_file():
                frontend = cand
                break
        else:
            # One level deep, for repos that nest apps (apps/web, packages/ui, ...).
            for cand in sorted(p.parent for p in root.glob("*/*/angular.json")):
                frontend = cand
                break

    return Project(root=root, backend=backend, frontend=frontend)


def run_checks(project: Project) -> list[Finding]:
    """Run every registered check and return the findings in registry order."""
    from . import checks

    findings: list[Finding] = []
    for check in checks.REGISTRY:
        try:
            findings.extend(check(project))
        except Exception as exc:  # a broken check must not sink the whole run
            findings.append(
                Finding(
                    check=getattr(check, "check_id", check.__name__),
                    severity=Severity.SKIP,
                    summary="check raised an unexpected error",
                    detail=f"{type(exc).__name__}: {exc}",
                    fix="Please report this with the project layout that triggered it.",
                )
            )
    return findings


_LABEL = {
    Severity.PASS: "PASS",
    Severity.WARN: "WARN",
    Severity.FAIL: "FAIL",
    Severity.SKIP: "SKIP",
}


def _render(findings: list[Finding], project: Project) -> str:
    lines: list[str] = []
    lines.append(f"hop-doctor — {project.root}")
    if project.backend:
        lines.append(f"  backend:  {_rel(project.backend, project.root)}")
    if project.frontend:
        lines.append(f"  frontend: {_rel(project.frontend, project.root)}")
    lines.append("")

    group = ""
    for f in findings:
        g = f.check.split(".", 1)[0]
        if g != group:
            group = g
            lines.append(group)
        lines.append(f"  {_LABEL[f.severity]}  {f.summary}")
        if f.location:
            lines.append(f"        at {f.location}")
        if f.detail:
            for line in f.detail.splitlines():
                lines.append(f"        {line}")
        if f.fix and f.severity in (Severity.FAIL, Severity.WARN):
            lines.append(f"        Fix: {f.fix}")

    counts = _counts(findings)
    lines.append("")
    lines.append(
        ", ".join(
            f"{counts[s]} {word}"
            for s, word in (
                (Severity.FAIL, "failed"),
                (Severity.WARN, "warning"),
                (Severity.PASS, "passed"),
                (Severity.SKIP, "skipped"),
            )
            if counts[s]
        )
        or "no checks ran"
    )
    return "\n".join(lines)


def _rel(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root)
        return str(rel) if str(rel) != "." else "."
    except ValueError:
        return str(path)


def _counts(findings: list[Finding]) -> dict[Severity, int]:
    return {s: sum(1 for f in findings if f.severity is s) for s in Severity}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hop-doctor",
        description="Audit an application built on hop-core for known integration failures.",
    )
    parser.add_argument("--path", default=".", help="project root (default: current directory)")
    parser.add_argument("--backend", help="backend directory, if auto-detection gets it wrong")
    parser.add_argument("--frontend", help="frontend directory, if auto-detection gets it wrong")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--strict", action="store_true", help="exit non-zero on warnings as well as failures"
    )
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        print(f"hop-doctor: not a directory: {root}", file=sys.stderr)
        return 2

    project = discover(
        root,
        backend=Path(args.backend) if args.backend else None,
        frontend=Path(args.frontend) if args.frontend else None,
    )
    findings = run_checks(project)
    counts = _counts(findings)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(project.root),
                    "backend": _rel(project.backend, project.root) if project.backend else None,
                    "frontend": _rel(project.frontend, project.root) if project.frontend else None,
                    "findings": [f.as_dict() for f in findings],
                    "summary": {s.value: counts[s] for s in Severity},
                },
                indent=2,
            )
        )
    else:
        print(_render(findings, project))

    if counts[Severity.FAIL]:
        return 1
    if args.strict and counts[Severity.WARN]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
