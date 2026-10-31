"""FIX 1 regression: the shipped `.env.example` must agree with the code.

The README tells Windows users to `copy ..\\.env.example .env`. If the
template pinned an old rule-engine version, every documented fresh install
would silently run out-of-date rule semantics and stamp assessments/hashes
with the wrong version. These tests pin the template to the code default and
prove that a copied template actually loads the intended version through the
real Settings machinery.
"""
import re
import shutil
from pathlib import Path

from app.config import BACKEND_DIR, REPO_ROOT, Settings, get_settings

TEMPLATE = REPO_ROOT / ".env.example"
CODE_DEFAULT = Settings.model_fields["rule_engine_version"].default


def _template_value(key: str) -> str:
    text = TEMPLATE.read_text()
    m = re.search(rf"^{re.escape(key)}=(.+)$", text, re.M)
    assert m, f"{key} missing from .env.example"
    return m.group(1).strip()


# 10a. template and code default agree
def test_env_example_rule_engine_version_matches_code_default():
    assert CODE_DEFAULT == "1.1.0", "code is expected to implement rules v1.1.0"
    assert _template_value("INSTITRACE_RULE_ENGINE_VERSION") == CODE_DEFAULT, (
        ".env.example (the documented install source) must ship the actual "
        "current rule-engine version"
    )


# 10b. fresh-install simulation: copy the template to .env exactly as the
# README instructs, then load settings FROM THAT FILE and confirm the engine
# evaluation machinery receives the intended version.
def test_copied_env_example_loads_intended_version(tmp_path, monkeypatch):
    fake_root = tmp_path
    shutil.copy(TEMPLATE, fake_root / ".env.example")
    shutil.copy(fake_root / ".env.example", fake_root / ".env")

    # settings built with the repo-root .env search path pointed at the copy
    (fake_root / "backend").mkdir()
    monkeypatch.setenv("INSTITRACE_RULE_ENGINE_VERSION", "")  # ensure no shell override
    monkeypatch.delenv("INSTITRACE_RULE_ENGINE_VERSION", raising=False)

    from pydantic_settings import SettingsConfigDict

    class FreshInstall(Settings):
        model_config = SettingsConfigDict(
            env_prefix="INSTITRACE_",
            env_file=[str(fake_root / ".env")],
            env_file_encoding="utf-8",
            extra="ignore",
        )

    loaded = FreshInstall()
    assert loaded.rule_engine_version == "1.1.0", (
        "documented fresh install must load the intended rule-engine version"
    )
    assert loaded.rule_engine_version == get_settings().rule_engine_version, (
        "installed copy must agree with the running application's version"
    )


# 10c. the loaded version is what actually drives assessments and hashes:
# two evaluations differing ONLY by version must produce different evidence
# fingerprints, so version discipline cannot silently drift.
def test_loaded_version_is_part_of_every_evidence_fingerprint():
    from app.services.matching_service import compute_evidence_hash

    evidence = dict(
        relationship_type="POTENTIAL_SAME_INCIDENT",
        supporting=[{"rule": "R1_SHARED_INCIDENT_REFERENCE", "detail": "INC-1"}],
        conflicting=[], missing=[], score=4,
    )
    h_current = compute_evidence_hash(**evidence, rule_version=get_settings().rule_engine_version)
    h_old = compute_evidence_hash(**evidence, rule_version="1.0.0")
    assert h_current != h_old
    assert get_settings().rule_engine_version == "1.1.0"


# 10d. .env hygiene: files must be git-IGNORED and untracked, never ABSENT.
# A documented install copies .env.example -> .env locally, so asserting that
# .env does not exist produced false failures on correct installations. The
# real security property is: the file is ignored by Git and never tracked.
def test_env_files_are_ignored_and_not_committed():
    import subprocess

    gitignore = REPO_ROOT / ".gitignore"
    assert gitignore.exists(), ".gitignore must exist"
    patterns = gitignore.read_text()
    assert ".env" in patterns, ".env must be in .gitignore"
    assert "*.env.local" in patterns, "*.env.local must be in .gitignore"

    if not (REPO_ROOT / ".git").exists():
        # ZIP-extracted source without git metadata: the .gitignore policy
        # above is all that can be verified.
        return

    # neither env file may be TRACKED (present in tracked files)
    tracked = subprocess.run(
        ["git", "ls-files", "--", ".env", "backend/.env"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert tracked == [], f".env files must never be tracked by git: {tracked}"

    # and the ignore policy must actually match them
    for env_path in (".env", "backend/.env"):
        probe = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", env_path],
            cwd=REPO_ROOT,
        )
        assert probe.returncode == 0, f"{env_path} is not covered by .gitignore"
