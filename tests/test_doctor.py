"""Tests for hop-doctor, the integration auditor.

Each check gets a passing case and a failing case, built as a throwaway project
tree under tmp_path. The point of these tests is guarding against false
positives as much as false negatives: a wrong FAIL is acted on by whoever ran
the tool.
"""

import json

from hop_core.doctor import Severity, discover, main, run_checks
from hop_core.doctor.checks import (
    check_docker_build_context,
    check_inline_critical,
    check_npm_dependency,
    check_python_dependency,
    check_required_settings,
    check_theme_import,
)

CSP_STRICT = 'add_header Content-Security-Policy "default-src \'self\'; style-src \'self\' \'unsafe-inline\'";'
CSP_LOOSE = 'add_header Content-Security-Policy "default-src \'self\'; script-src \'self\' \'unsafe-inline\'";'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def angular_json(inline_critical=None):
    build = {"options": {"styles": ["src/styles.scss"]}, "configurations": {"production": {}}}
    if inline_critical is not None:
        build["configurations"]["production"]["optimization"] = {
            "styles": {"inlineCritical": inline_critical}
        }
    return json.dumps({"projects": {"app": {"architect": {"build": build}}}})


def only(findings):
    """The single finding a check returned, asserting there is exactly one."""
    assert len(findings) == 1, findings
    return findings[0]


class TestPythonDependency:
    def test_local_path_fails(self, tmp_path):
        write(tmp_path / "requirements.txt", "hop-core @ file:///Users/someone/hop-core\n")
        f = only(check_python_dependency(discover(tmp_path)))
        assert f.severity is Severity.FAIL
        assert "local filesystem path" in f.summary

    def test_pinned_tag_passes(self, tmp_path):
        write(
            tmp_path / "requirements.txt",
            "hop-core @ git+https://github.com/Heretto/hop-core.git@v0.1.1\n",
        )
        assert only(check_python_dependency(discover(tmp_path))).severity is Severity.PASS

    def test_unpinned_git_warns(self, tmp_path):
        write(tmp_path / "requirements.txt", "hop-core @ git+https://github.com/Heretto/hop-core.git\n")
        f = only(check_python_dependency(discover(tmp_path)))
        assert f.severity is Severity.WARN
        assert "default branch" in f.summary

    def test_commented_line_ignored(self, tmp_path):
        write(
            tmp_path / "requirements.txt",
            "# hop-core @ file:///old/path\nhop-core @ git+https://github.com/Heretto/hop-core.git@v0.1.1\n",
        )
        assert only(check_python_dependency(discover(tmp_path))).severity is Severity.PASS

    def test_absent_skips(self, tmp_path):
        write(tmp_path / "requirements.txt", "fastapi>=0.104\n")
        assert only(check_python_dependency(discover(tmp_path))).severity is Severity.SKIP


class TestNpmDependency:
    def _frontend(self, tmp_path, spec):
        write(tmp_path / "frontend" / "angular.json", angular_json())
        write(
            tmp_path / "frontend" / "package.json",
            json.dumps({"dependencies": {"@heretto/hop-ui": spec}}, indent=2),
        )
        return discover(tmp_path)

    def test_file_path_fails(self, tmp_path):
        p = self._frontend(tmp_path, "file:../../hop-core/ui/dist/hop-ui/heretto-hop-ui-0.1.0.tgz")
        f = only(check_npm_dependency(p))
        assert f.severity is Severity.FAIL
        assert "local path" in f.summary

    def test_source_archive_fails(self, tmp_path):
        p = self._frontend(tmp_path, "https://github.com/Heretto/hop-core/archive/refs/tags/v0.1.1.tar.gz")
        f = only(check_npm_dependency(p))
        assert f.severity is Severity.FAIL
        assert "source archive" in f.summary

    def test_git_dependency_fails(self, tmp_path):
        p = self._frontend(tmp_path, "git+https://github.com/Heretto/hop-core.git#v0.1.1")
        assert only(check_npm_dependency(p)).severity is Severity.FAIL

    def test_release_asset_passes(self, tmp_path):
        p = self._frontend(
            tmp_path,
            "https://github.com/Heretto/hop-core/releases/download/v0.1.1/heretto-hop-ui-0.1.1.tgz",
        )
        assert only(check_npm_dependency(p)).severity is Severity.PASS

    def test_registry_version_passes(self, tmp_path):
        p = self._frontend(tmp_path, "^0.1.1")
        assert only(check_npm_dependency(p)).severity is Severity.PASS

    def test_no_frontend_skips(self, tmp_path):
        assert only(check_npm_dependency(discover(tmp_path))).severity is Severity.SKIP


class TestThemeImport:
    def _styles(self, tmp_path, content):
        write(tmp_path / "frontend" / "angular.json", angular_json())
        write(tmp_path / "frontend" / "src" / "styles.scss", content)
        return discover(tmp_path)

    def test_source_tree_path_fails(self, tmp_path):
        p = self._styles(tmp_path, "@use '../../../hop-core/ui/src/lib/theme/index' as hop;\n")
        f = only(check_theme_import(p))
        assert f.severity is Severity.FAIL
        assert "source tree" in f.summary

    def test_package_import_passes(self, tmp_path):
        p = self._styles(tmp_path, "@use '@heretto/hop-ui/theme' as hop;\n@include hop.hop-core-theme();\n")
        assert only(check_theme_import(p)).severity is Severity.PASS

    def test_missing_theme_warns(self, tmp_path):
        p = self._styles(tmp_path, "body { margin: 0; }\n")
        assert only(check_theme_import(p)).severity is Severity.WARN


class TestInlineCritical:
    def _project(self, tmp_path, inline_critical, csp=None):
        write(tmp_path / "frontend" / "angular.json", angular_json(inline_critical))
        write(tmp_path / "frontend" / "src" / "styles.scss", "")
        if csp:
            write(tmp_path / "frontend" / "nginx.conf", csp)
        return discover(tmp_path)

    def test_enabled_with_strict_csp_fails(self, tmp_path):
        # The strict policy allows 'unsafe-inline' for STYLES only, which is the
        # exact shape that misleads people into thinking scripts are permitted.
        p = self._project(tmp_path, None, CSP_STRICT)
        f = only(check_inline_critical(p))
        assert f.severity is Severity.FAIL
        assert "blocks the handler" in f.summary

    def test_disabled_passes(self, tmp_path):
        p = self._project(tmp_path, False, CSP_STRICT)
        assert only(check_inline_critical(p)).severity is Severity.PASS

    def test_enabled_with_permissive_csp_passes(self, tmp_path):
        p = self._project(tmp_path, None, CSP_LOOSE)
        assert only(check_inline_critical(p)).severity is Severity.PASS

    def test_enabled_without_csp_passes_with_a_caveat(self, tmp_path):
        f = only(check_inline_critical(self._project(tmp_path, None)))
        assert f.severity is Severity.PASS
        assert "no in-repo CSP" in f.summary

    def test_explicit_true_with_strict_csp_fails(self, tmp_path):
        p = self._project(tmp_path, True, CSP_STRICT)
        assert only(check_inline_critical(p)).severity is Severity.FAIL


class TestDockerBuildContext:
    def test_missing_dockerfile_fails(self, tmp_path):
        write(tmp_path / "docker-compose.yml", "services:\n  backend:\n    build: ./backend\n")
        (tmp_path / "backend").mkdir()
        findings = check_docker_build_context(discover(tmp_path))
        if findings[0].severity is Severity.SKIP:  # PyYAML absent
            return
        assert any(f.severity is Severity.FAIL and "backend" in f.summary for f in findings)

    def test_present_dockerfile_passes(self, tmp_path):
        write(tmp_path / "docker-compose.yml", "services:\n  backend:\n    build: ./backend\n")
        write(tmp_path / "backend" / "Dockerfile", "FROM python:3.12-slim\n")
        findings = check_docker_build_context(discover(tmp_path))
        if findings[0].severity is Severity.SKIP:
            return
        assert all(f.severity is Severity.PASS for f in findings)

    def test_image_only_service_skips(self, tmp_path):
        write(tmp_path / "docker-compose.yml", "services:\n  db:\n    image: postgres:16\n")
        assert only(check_docker_build_context(discover(tmp_path))).severity is Severity.SKIP

    def test_no_compose_skips(self, tmp_path):
        assert only(check_docker_build_context(discover(tmp_path))).severity is Severity.SKIP


class TestRequiredSettings:
    def test_no_env_warns(self, tmp_path):
        f = only(check_required_settings(discover(tmp_path)))
        assert f.severity is Severity.WARN
        assert "no .env" in f.summary

    def test_complete_env_passes(self, tmp_path):
        write(tmp_path / ".gitignore", ".env\n")
        write(
            tmp_path / ".env",
            "APP_SECRET_KEY=" + "a" * 32 + "\n"
            "JWT_SECRET_KEY=" + "b" * 32 + "\n"
            "ENCRYPTION_KEY=" + "c" * 32 + "\n"
            "DATABASE_URL=sqlite:///./app.db\n",
        )
        severities = {f.severity for f in check_required_settings(discover(tmp_path))}
        assert Severity.FAIL not in severities

    def test_short_encryption_key_fails(self, tmp_path):
        write(
            tmp_path / ".env",
            "APP_SECRET_KEY=x\nJWT_SECRET_KEY=y\nENCRYPTION_KEY=tooshort\nDATABASE_URL=sqlite:///a.db\n",
        )
        findings = check_required_settings(discover(tmp_path))
        assert any(f.severity is Severity.FAIL and "too short" in f.summary for f in findings)

    def test_missing_keys_warn_not_fail(self, tmp_path):
        # Values may come from the host environment, so absence is not provable breakage.
        write(tmp_path / ".env", "DATABASE_URL=sqlite:///a.db\n")
        findings = check_required_settings(discover(tmp_path))
        assert any(f.severity is Severity.WARN and "absent or empty" in f.summary for f in findings)
        assert not any(f.severity is Severity.FAIL for f in findings)

    def test_secret_values_are_never_reported(self, tmp_path):
        secret = "SUPERSECRETVALUE0000000000000000"
        write(tmp_path / ".env", f"ENCRYPTION_KEY={secret}\n")
        blob = json.dumps([f.as_dict() for f in check_required_settings(discover(tmp_path))])
        assert secret not in blob

    def test_placeholder_value_warns(self, tmp_path):
        write(
            tmp_path / ".env",
            "APP_SECRET_KEY=change-me-32-chars-minimum\n"
            "JWT_SECRET_KEY=" + "b" * 32 + "\n"
            "ENCRYPTION_KEY=" + "c" * 32 + "\n"
            "DATABASE_URL=sqlite:///a.db\n",
        )
        findings = check_required_settings(discover(tmp_path))
        assert any("template values" in f.summary for f in findings)


class TestDiscovery:
    def test_finds_nested_backend_and_frontend(self, tmp_path):
        write(tmp_path / "backend" / "requirements.txt", "fastapi\n")
        write(tmp_path / "frontend" / "angular.json", angular_json())
        p = discover(tmp_path)
        assert p.backend == tmp_path / "backend"
        assert p.frontend == tmp_path / "frontend"

    def test_explicit_overrides_win(self, tmp_path):
        write(tmp_path / "svc" / "requirements.txt", "fastapi\n")
        p = discover(tmp_path, backend=tmp_path / "svc")
        assert p.backend == tmp_path / "svc"


class TestCli:
    def _broken_project(self, tmp_path):
        write(tmp_path / "requirements.txt", "hop-core @ file:///somewhere/hop-core\n")
        write(tmp_path / "frontend" / "angular.json", angular_json())
        write(tmp_path / "frontend" / "src" / "styles.scss", "@use '@heretto/hop-ui/theme' as hop;\n")

    def test_exit_1_on_failure(self, tmp_path):
        self._broken_project(tmp_path)
        assert main(["--path", str(tmp_path)]) == 1

    def test_exit_0_on_clean_project(self, tmp_path):
        write(tmp_path / "requirements.txt", "hop-core @ git+https://github.com/Heretto/hop-core.git@v0.1.1\n")
        assert main(["--path", str(tmp_path)]) == 0

    def test_strict_promotes_warnings(self, tmp_path):
        write(tmp_path / "requirements.txt", "hop-core @ git+https://github.com/Heretto/hop-core.git\n")
        assert main(["--path", str(tmp_path)]) == 0
        assert main(["--path", str(tmp_path), "--strict"]) == 1

    def test_json_output_is_valid_and_structured(self, tmp_path, capsys):
        self._broken_project(tmp_path)
        main(["--path", str(tmp_path), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["fail"] >= 1
        assert all({"check", "severity", "summary"} <= set(f) for f in payload["findings"])

    def test_missing_directory_exits_2(self, tmp_path):
        assert main(["--path", str(tmp_path / "nope")]) == 2

    def test_every_check_runs(self, tmp_path):
        ids = {f.check.split(".", 1)[0] for f in run_checks(discover(tmp_path))}
        assert ids == {"deps", "frontend", "docker", "settings"}
