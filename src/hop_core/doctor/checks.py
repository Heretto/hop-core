"""The individual hop-doctor checks.

Each check takes a Project and returns a list of Findings. Add a check by
writing the function and appending it to REGISTRY at the bottom.

Conventions:
- FAIL only when the repository proves the thing is broken.
- WARN when it looks wrong but configuration could legitimately come from
  elsewhere (host environment, ingress, CI).
- SKIP when the inspected artifact is absent or cannot be parsed.
- Never print a secret value. Key names and lengths only.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import Finding, Project, Severity

# ---------------------------------------------------------------------------
# helpers


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _line_of(text: str, needle: str) -> int | None:
    for i, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return i
    return None


def _loc(path: Path, root: Path, line: int | None = None) -> str:
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        rel = path
    return f"{rel}:{line}" if line else str(rel)


def _load_json(path: Path) -> dict | None:
    text = _read(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# deps.python


def check_python_dependency(project: Project) -> list[Finding]:
    """hop-core must be installed from a pinned release tag, never a local path."""
    cid = "deps.python"
    searched: list[Path] = []
    for d in filter(None, (project.backend, project.root)):
        searched.extend(sorted(d.glob("requirements*.txt")))
        searched.append(d / "pyproject.toml")

    for path in searched:
        text = _read(path)
        if text is None:
            continue
        for i, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "hop-core" not in line and "hop_core" not in line:
                continue

            loc = _loc(path, project.root, i)
            if "file:" in line:
                return [
                    Finding(
                        cid,
                        Severity.FAIL,
                        "hop-core is installed from a local filesystem path",
                        "This resolves only on the machine that wrote it, and can never\n"
                        "resolve inside a Docker build, where the path is outside the\n"
                        "build context.",
                        'Use a pinned git tag, e.g. "hop-core @ '
                        'git+https://github.com/Heretto/hop-core.git@v0.1.2".',
                        loc,
                    )
                ]
            if "git+" in line:
                # A ref looks like ".git@v1.2.3" or "...@<sha>".
                if re.search(r"\.git@[^\s#]+", line):
                    return [
                        Finding(
                            cid,
                            Severity.PASS,
                            "hop-core is pinned to a git ref",
                            location=loc,
                        )
                    ]
                return [
                    Finding(
                        cid,
                        Severity.WARN,
                        "hop-core tracks the default branch instead of a release",
                        "Every fresh install may resolve to a different commit, so builds\n"
                        "are not reproducible and an upstream change can break this app\n"
                        "without anything here changing.",
                        "Append a release tag, e.g. '...hop-core.git@v0.1.2'.",
                        loc,
                    )
                ]
            return [
                Finding(
                    cid,
                    Severity.PASS,
                    "hop-core is declared as a versioned requirement",
                    location=loc,
                )
            ]

    return [
        Finding(
            cid,
            Severity.SKIP,
            "no hop-core requirement found to inspect",
            "Looked in requirements*.txt and pyproject.toml.",
        )
    ]


# ---------------------------------------------------------------------------
# deps.npm

_RELEASE_ASSET = re.compile(r"/releases/download/[^/]+/heretto-hop-ui-[^/]+\.tgz$")


def check_npm_dependency(project: Project) -> list[Finding]:
    """@heretto/hop-ui must come from a release asset, not a path or git URL."""
    cid = "deps.npm"
    if project.frontend is None:
        return [Finding(cid, Severity.SKIP, "no frontend directory detected")]

    pkg_path = project.frontend / "package.json"
    pkg = _load_json(pkg_path)
    if pkg is None:
        return [Finding(cid, Severity.SKIP, "no readable package.json", location=_loc(pkg_path, project.root))]

    spec = None
    for section in ("dependencies", "devDependencies"):
        spec = (pkg.get(section) or {}).get("@heretto/hop-ui")
        if spec:
            break
    if not spec:
        return [Finding(cid, Severity.SKIP, "@heretto/hop-ui is not a dependency here")]

    text = _read(pkg_path) or ""
    loc = _loc(pkg_path, project.root, _line_of(text, "@heretto/hop-ui"))

    if spec.startswith("file:"):
        return [
            Finding(
                cid,
                Severity.FAIL,
                "@heretto/hop-ui is installed from a local path",
                "This resolves only on one machine, and never inside a Docker build.\n"
                "It commonly points at an uncommitted build artifact, so a fresh clone\n"
                "cannot install it at all.",
                "Point it at the release asset: https://github.com/Heretto/hop-core/"
                "releases/download/<tag>/heretto-hop-ui-<version>.tgz",
                loc,
            )
        ]

    if "/archive/refs/tags/" in spec:
        return [
            Finding(
                cid,
                Severity.FAIL,
                "@heretto/hop-ui points at GitHub's source archive, which npm cannot install",
                "The auto-generated vX.Y.Z.tar.gz is not an npm package: its root is\n"
                "hop-core-X.Y.Z/ rather than package/, and it contains no build output.\n"
                "npm install fails with 'ENOENT: Could not read package.json'.",
                "Use the heretto-hop-ui-*.tgz asset attached to the release.",
                loc,
            )
        ]

    if spec.startswith("git+") or spec.startswith("github:"):
        return [
            Finding(
                cid,
                Severity.FAIL,
                "@heretto/hop-ui is declared as a git dependency, which cannot work",
                "npm cannot install from a subdirectory of a git repository, and this\n"
                "package lives in ui/. The install resolves the repository root, which\n"
                "is not the package.",
                "Use the heretto-hop-ui-*.tgz asset attached to the release.",
                loc,
            )
        ]

    if _RELEASE_ASSET.search(spec):
        return [Finding(cid, Severity.PASS, "@heretto/hop-ui comes from a release asset", location=loc)]

    return [
        Finding(
            cid,
            Severity.PASS,
            "@heretto/hop-ui is declared as a registry version",
            location=loc,
        )
    ]


# ---------------------------------------------------------------------------
# frontend.theme


def _global_styles(project: Project) -> list[Path]:
    """Global stylesheets declared in angular.json, else the conventional default."""
    assert project.frontend is not None
    ng = _load_json(project.frontend / "angular.json")
    styles: list[Path] = []
    if ng:
        for proj in (ng.get("projects") or {}).values():
            opts = ((proj.get("architect") or {}).get("build") or {}).get("options") or {}
            for entry in opts.get("styles") or []:
                name = entry if isinstance(entry, str) else entry.get("input")
                if name:
                    styles.append(project.frontend / name)
    if not styles:
        styles = [project.frontend / "src" / "styles.scss"]
    return [p for p in styles if p.is_file()]


def check_theme_import(project: Project) -> list[Finding]:
    """The theme must be imported from the package, not from hop-core's source tree."""
    cid = "frontend.theme"
    if project.frontend is None:
        return [Finding(cid, Severity.SKIP, "no frontend directory detected")]

    styles = _global_styles(project)
    if not styles:
        return [Finding(cid, Severity.SKIP, "no global stylesheet found to inspect")]

    for path in styles:
        text = _read(path) or ""
        for i, line in enumerate(text.splitlines(), start=1):
            if not re.match(r"\s*@(use|import|forward)\b", line):
                continue
            loc = _loc(path, project.root, i)
            if "@heretto/hop-ui/theme" in line:
                return [Finding(cid, Severity.PASS, "theme is imported from the package", location=loc)]
            if "hop-core" in line or "ui/src/lib/theme" in line:
                return [
                    Finding(
                        cid,
                        Severity.FAIL,
                        "the theme is imported through a path into hop-core's source tree",
                        "This resolves only when hop-core sits at one exact location on\n"
                        "disk, and never inside a Docker build. It also bypasses the\n"
                        "published package, so packaging regressions go unnoticed.",
                        "Use \"@use '@heretto/hop-ui/theme' as hop;\" "
                        "(requires @heretto/hop-ui >= 0.1.1).",
                        loc,
                    )
                ]

    return [
        Finding(
            cid,
            Severity.WARN,
            "no hop-ui theme import found in the global stylesheet",
            "Nothing renders in hop-core's design system until hop-core-theme() is\n"
            "included. If the theme is applied elsewhere, ignore this.",
            "Add \"@use '@heretto/hop-ui/theme' as hop;\" and \"@include hop.hop-core-theme();\".",
            _loc(styles[0], project.root),
        )
    ]


# ---------------------------------------------------------------------------
# frontend.inline_critical

_CSP_FILE_GLOBS = ("*.conf", "*.py", "*.ts", "*.js", "*.html", "*.yml", "*.yaml")
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".venv", "venv", "__pycache__", ".angular"}


def _find_csp(root: Path) -> tuple[Path, int, str] | None:
    """Find the first in-repo Content-Security-Policy definition."""
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not any(path.match(g) for g in _CSP_FILE_GLOBS):
            continue
        text = _read(path)
        if not text or "Content-Security-Policy" not in text:
            continue
        line = _line_of(text, "Content-Security-Policy") or 1
        return path, line, text
    return None


def _script_sources(csp_text: str) -> str | None:
    """The effective script-src value from a blob of text containing a policy.

    Falls back to default-src, per CSP semantics. Works on both single-line
    policies (nginx) and adjacent concatenated string literals (Python), because
    a directive and its values sit together in the source text.
    """
    for directive in ("script-src", "default-src"):
        # Stop at ';' (next directive) or '"' (end of the policy string), but
        # allow single quotes: CSP keywords are written 'self', 'unsafe-inline'.
        m = re.search(rf"\b{directive}\b([^;\"]*)", csp_text)
        if m:
            return m.group(1)
    return None


def _inline_critical_enabled(ng: dict) -> bool | None:
    """Whether inlineCritical is effectively on for the production build."""
    for proj in (ng.get("projects") or {}).values():
        build = (proj.get("architect") or {}).get("build") or {}
        conf = (build.get("configurations") or {}).get("production")
        if conf is None:
            continue
        opt = conf.get("optimization", build.get("options", {}).get("optimization"))
        if opt is None:
            return True  # Angular's default for production is full optimization
        if opt is False:
            return False
        if opt is True:
            return True
        if isinstance(opt, dict):
            styles = opt.get("styles")
            if styles is False:
                return False
            if isinstance(styles, dict):
                return bool(styles.get("inlineCritical", True))
            return True
    return None


def check_inline_critical(project: Project) -> list[Finding]:
    """Angular's inlineCritical defeats a strict CSP, silently disabling all CSS."""
    cid = "frontend.inline_critical"
    if project.frontend is None:
        return [Finding(cid, Severity.SKIP, "no frontend directory detected")]

    ng_path = project.frontend / "angular.json"
    ng = _load_json(ng_path)
    if ng is None:
        return [Finding(cid, Severity.SKIP, "no readable angular.json")]

    enabled = _inline_critical_enabled(ng)
    if enabled is None:
        return [Finding(cid, Severity.SKIP, "no production build configuration found")]

    if not enabled:
        return [
            Finding(
                cid,
                Severity.PASS,
                "inlineCritical is disabled, so the stylesheet loads without an inline handler",
                location=_loc(ng_path, project.root),
            )
        ]

    found = _find_csp(project.root)
    if found is None:
        return [
            Finding(
                cid,
                Severity.PASS,
                "inlineCritical is enabled, but no in-repo CSP was found",
                "If a proxy, ingress or CDN adds a Content-Security-Policy that omits\n"
                "'unsafe-inline' for scripts, the stylesheet will silently never apply.\n"
                "See AGENTS.md section 4.",
                location=_loc(ng_path, project.root),
            )
        ]

    csp_path, csp_line, csp_text = found
    sources = _script_sources(csp_text)
    if sources is not None and "unsafe-inline" in sources:
        return [
            Finding(
                cid,
                Severity.PASS,
                "inlineCritical is enabled and the CSP permits inline scripts",
                location=_loc(ng_path, project.root),
            )
        ]

    return [
        Finding(
            cid,
            Severity.FAIL,
            "inlineCritical is enabled but the CSP blocks the handler that applies the stylesheet",
            "Angular loads the real stylesheet inert (media=\"print\") and activates it\n"
            "with an inline onload handler. This CSP does not allow inline scripts, so\n"
            "the handler never runs: the stylesheet downloads with HTTP 200 and is\n"
            "never applied. Only the inlined critical subset takes effect, which omits\n"
            "the mat-icon font rule — so icons render as their ligature names and\n"
            "component styles are subtly wrong.\n"
            f"CSP found at {_loc(csp_path, project.root, csp_line)}",
            'Set optimization.styles.inlineCritical = false on the production '
            "configuration. Do not add 'unsafe-inline' to script-src instead.",
            _loc(ng_path, project.root),
        )
    ]


# ---------------------------------------------------------------------------
# docker.build_context


def check_docker_build_context(project: Project) -> list[Finding]:
    """Every compose build context must actually contain a Dockerfile."""
    cid = "docker.build_context"
    compose_files = [
        p
        for pattern in ("docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml")
        for p in sorted(project.root.glob(pattern))
    ]
    if not compose_files:
        return [Finding(cid, Severity.SKIP, "no compose file found")]

    try:
        import yaml  # type: ignore
    except ImportError:
        return [
            Finding(
                cid,
                Severity.SKIP,
                "PyYAML is not installed, so the compose file was not parsed",
                fix='Install the extra: pip install "hop-core[doctor]"',
            )
        ]

    findings: list[Finding] = []
    for compose in compose_files:
        text = _read(compose)
        if text is None:
            continue
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            findings.append(
                Finding(cid, Severity.SKIP, "compose file is not valid YAML", str(exc), location=_loc(compose, project.root))
            )
            continue

        services = (doc.get("services") or {}) if isinstance(doc, dict) else {}
        for name, svc in services.items():
            if not isinstance(svc, dict) or "build" not in svc:
                continue
            build = svc["build"]
            if isinstance(build, str):
                context, dockerfile = build, "Dockerfile"
            elif isinstance(build, dict):
                context = build.get("context", ".")
                dockerfile = build.get("dockerfile", "Dockerfile")
            else:
                continue

            target = (compose.parent / context / dockerfile).resolve()
            loc = _loc(compose, project.root, _line_of(text, f"{name}:"))
            if target.is_file():
                findings.append(
                    Finding(cid, Severity.PASS, f"service '{name}' has a Dockerfile at its build context", location=loc)
                )
            else:
                findings.append(
                    Finding(
                        cid,
                        Severity.FAIL,
                        f"service '{name}' builds from a context with no Dockerfile",
                        f"Expected {_loc(target, project.root)}.\n"
                        "docker compose up fails immediately with 'failed to read dockerfile'.",
                        "Add the Dockerfile, or point the build context at the directory that has one.",
                        loc,
                    )
                )
    return findings or [Finding(cid, Severity.SKIP, "no compose service builds from a context")]


# ---------------------------------------------------------------------------
# settings.required

_REQUIRED = ("APP_SECRET_KEY", "JWT_SECRET_KEY", "ENCRYPTION_KEY", "DATABASE_URL")
_PLACEHOLDER = re.compile(r"^(change[-_ ]?me|your[-_ ]|xxx|todo|placeholder|example)", re.I)


def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.split("#", 1)[0].strip().strip("'\"")
    return out


def check_required_settings(project: Project) -> list[Finding]:
    """HopCoreSettings has required fields with no defaults.

    Values may legitimately come from the host environment or a secret manager,
    so anything absent here is a WARN rather than a FAIL. A present-but-invalid
    value is a FAIL, because that is provable.
    """
    cid = "settings.required"
    candidates = [d / ".env" for d in filter(None, (project.backend, project.root))]
    env_path = next((p for p in candidates if p.is_file()), None)

    if env_path is None:
        examples = [p for d in filter(None, (project.backend, project.root)) for p in [d / ".env.example"] if p.is_file()]
        return [
            Finding(
                cid,
                Severity.WARN,
                "no .env file found",
                "hop-core requires APP_SECRET_KEY, JWT_SECRET_KEY, ENCRYPTION_KEY and\n"
                "DATABASE_URL, none of which have defaults. If they come from the\n"
                "environment or a secret manager, this is fine."
                + (f"\nTemplate available at {_loc(examples[0], project.root)}." if examples else ""),
                "Copy the template to .env and generate secrets with 'openssl rand -hex 32'.",
            )
        ]

    env = _parse_env(_read(env_path) or "")
    text = _read(env_path) or ""
    findings: list[Finding] = []

    missing = [k for k in _REQUIRED if not env.get(k)]
    if missing:
        findings.append(
            Finding(
                cid,
                Severity.WARN,
                f"required setting(s) absent or empty in .env: {', '.join(missing)}",
                "These have no defaults in HopCoreSettings; the app will not start unless\n"
                "they are supplied some other way (host environment, compose, secrets).",
                "Set them, generating secrets with 'openssl rand -hex 32'.",
                _loc(env_path, project.root),
            )
        )

    placeholders = [k for k in _REQUIRED if env.get(k) and _PLACEHOLDER.match(env[k])]
    if placeholders:
        findings.append(
            Finding(
                cid,
                Severity.WARN,
                f"setting(s) still hold template values: {', '.join(placeholders)}",
                fix="Replace them with real generated values.",
                location=_loc(env_path, project.root),
            )
        )

    enc = env.get("ENCRYPTION_KEY")
    if enc and len(enc) < 16:
        findings.append(
            Finding(
                cid,
                Severity.FAIL,
                f"ENCRYPTION_KEY is too short ({len(enc)} characters, minimum 16)",
                "hop-core derives the credential encryption key from this value and\n"
                "rejects anything shorter.",
                "Generate a new one with 'openssl rand -hex 32'. Note that changing it\n"
                "later makes existing encrypted rows unreadable.",
                _loc(env_path, project.root, _line_of(text, "ENCRYPTION_KEY")),
            )
        )

    if not _is_git_ignored(env_path, project.root):
        findings.append(
            Finding(
                cid,
                Severity.WARN,
                ".env does not appear to be git-ignored",
                "It holds secrets, including ENCRYPTION_KEY, which cannot be rotated\n"
                "without losing access to existing encrypted data.",
                "Add '.env' to .gitignore.",
                _loc(env_path, project.root),
            )
        )

    if not findings:
        findings.append(
            Finding(cid, Severity.PASS, "required settings are present in .env", location=_loc(env_path, project.root))
        )
    return findings


def _is_git_ignored(path: Path, root: Path) -> bool:
    """True if git reports the path as ignored. Assumes ignored when git cannot say."""
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return True  # no git, or not a repository — do not cry wolf
    return proc.returncode == 0


# ---------------------------------------------------------------------------

REGISTRY = (
    check_python_dependency,
    check_npm_dependency,
    check_theme_import,
    check_inline_critical,
    check_docker_build_context,
    check_required_settings,
)
