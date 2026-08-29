"""Maintenance-only reproducible package and install verification for both Skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


class ReleaseError(ValueError):
    """Raised when source, package, or installation digests diverge."""


ALLOWED_SKILLS = {"meme-template-image-producer", "meme-template-json-compiler"}
IGNORED_NAMES = {".DS_Store", "__pycache__"}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _release(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / "release.json").read_text(encoding="utf-8"))


def _source_revision(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", revision) else None


def _git_worktree_dirty(repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError("source root is not a readable Git worktree")
    return bool(result.stdout)


def _skill_files(repo_root: Path, skill_name: str) -> list[Path]:
    if skill_name not in ALLOWED_SKILLS:
        raise ReleaseError("unknown Skill")
    skill_root = repo_root / "skills" / skill_name
    if not (skill_root / "SKILL.md").is_file():
        raise ReleaseError("Skill source is incomplete")
    files = []
    for path in skill_root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in IGNORED_NAMES for part in path.relative_to(skill_root).parts) or path.suffix == ".pyc":
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(skill_root).as_posix())


def build_manifest(
    repo_root: Path, skill_name: str, *, allow_uncommitted: bool = False
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    release_path = repo_root / "release.json"
    release = _release(repo_root)
    if release.get("skills", {}).get(skill_name) is None:
        raise ReleaseError("release.json does not version this Skill")
    skill_root = repo_root / "skills" / skill_name
    entries = []
    for path in _skill_files(repo_root, skill_name):
        content = path.read_bytes()
        entries.append({
            "path": path.relative_to(skill_root).as_posix(),
            "byteLength": len(content),
            "sha256": _sha256(content),
        })
    tree_digest = _sha256(_canonical_json({"files": entries}))
    revision = _source_revision(repo_root)
    dirty = _git_worktree_dirty(repo_root)
    if not allow_uncommitted and (revision is None or dirty):
        raise ReleaseError("formal build requires a committed, clean, fully tracked worktree")
    manifest = {
        "schemaVersion": 1,
        "skillName": skill_name,
        "skillVersion": release["skills"][skill_name],
        "releaseVersion": release["releaseVersion"],
        "sourceRevision": revision or "maintenance-uncommitted",
        "sourceTreeSha256": tree_digest,
        "releaseJsonSha256": _sha256(release_path.read_bytes()),
        "files": entries,
    }
    if allow_uncommitted:
        manifest["maintenanceOnly"] = True
        manifest["sourceWasDirty"] = dirty
    return manifest


def _zip_entry(name: str, content: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o444) << 16
    return info, content


def build_skill_package(
    repo_root: Path,
    skill_name: str,
    output_dir: Path,
    *,
    allow_uncommitted: bool = False,
) -> tuple[Path, str]:
    """Build a create-once, byte-reproducible standalone Skill zip."""

    repo_root = Path(repo_root).resolve()
    output_dir = Path(output_dir).resolve()
    manifest = build_manifest(repo_root, skill_name, allow_uncommitted=allow_uncommitted)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{skill_name}-{manifest['skillVersion']}.zip"
    skill_root = repo_root / "skills" / skill_name
    with tempfile.NamedTemporaryFile(prefix=f".{skill_name}.", suffix=".zip", dir=output_dir, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            info, content = _zip_entry("release-manifest.json", _canonical_json(manifest))
            archive.writestr(info, content)
            for entry in manifest["files"]:
                content = (skill_root / entry["path"]).read_bytes()
                info, content = _zip_entry(f"{skill_name}/{entry['path']}", content)
                archive.writestr(info, content)
        encoded = temporary.read_bytes()
        if target.exists():
            if target.read_bytes() != encoded:
                raise ReleaseError("release package content conflict")
            return target, _sha256(encoded)
        os.replace(temporary, target)
        return target, _sha256(encoded)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_package(package_path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    with zipfile.ZipFile(package_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "release-manifest.json" not in names:
            raise ReleaseError("package has duplicate entries or no manifest")
        manifest = json.loads(archive.read("release-manifest.json"))
        skill_name = manifest.get("skillName")
        if skill_name not in ALLOWED_SKILLS:
            raise ReleaseError("package names an unknown Skill")
        expected_names = {"release-manifest.json"} | {
            f"{skill_name}/{entry['path']}" for entry in manifest.get("files", [])
        }
        if set(names) != expected_names:
            raise ReleaseError("package file set differs from its manifest")
        content_by_path: dict[str, bytes] = {}
        for entry in manifest["files"]:
            relative = PurePosixPath(entry["path"])
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ReleaseError("package contains an unsafe path")
            content = archive.read(f"{skill_name}/{entry['path']}")
            if len(content) != entry["byteLength"] or _sha256(content) != entry["sha256"]:
                raise ReleaseError("package file digest mismatch")
            content_by_path[entry["path"]] = content
        if _sha256(_canonical_json({"files": manifest["files"]})) != manifest["sourceTreeSha256"]:
            raise ReleaseError("package source tree digest mismatch")
        return manifest, content_by_path


def install_skill_package(
    package_path: Path,
    install_root: Path,
    *,
    expected_package_sha256: str,
) -> tuple[Path, Path]:
    """Install a verified package into a read-only version directory."""

    package_path = Path(package_path).resolve()
    actual_package_sha = _sha256(package_path.read_bytes())
    if actual_package_sha != expected_package_sha256:
        raise ReleaseError("package digest does not match the trusted expected digest")
    manifest, files = _read_package(package_path)
    install_root = Path(install_root).resolve()
    install_root.mkdir(parents=True, exist_ok=True)
    target = install_root / manifest["skillName"] / manifest["skillVersion"]
    if target.exists():
        verify_installed_skill(target, manifest)
    else:
        staging_parent = install_root / ".staging"
        staging_parent.mkdir(exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{manifest['skillName']}.", dir=staging_parent))
        try:
            for relative, content in files.items():
                destination = staging.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            verify_installed_skill(staging, manifest)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, target)
        finally:
            if staging.exists():
                for path in sorted(staging.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                staging.rmdir()
    for path in target.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    target.chmod(0o555)
    receipt = {
        "schemaVersion": 1,
        "skillName": manifest["skillName"],
        "skillVersion": manifest["skillVersion"],
        "packageSha256": actual_package_sha,
        "sourceTreeSha256": manifest["sourceTreeSha256"],
        "installedFileSha256": {entry["path"]: entry["sha256"] for entry in manifest["files"]},
    }
    receipt_dir = install_root / "install-receipts"
    receipt_dir.mkdir(exist_ok=True)
    receipt_path = receipt_dir / f"{manifest['skillName']}-{manifest['skillVersion']}.json"
    encoded = _canonical_json(receipt)
    if receipt_path.exists() and receipt_path.read_bytes() != encoded:
        raise ReleaseError("install receipt content conflict")
    if not receipt_path.exists():
        receipt_path.write_bytes(encoded)
    return target, receipt_path


def verify_installed_skill(target: Path, manifest: Mapping[str, Any]) -> None:
    target = Path(target).resolve()
    expected = {entry["path"]: entry for entry in manifest["files"]}
    actual = {
        path.relative_to(target).as_posix(): path
        for path in target.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if set(actual) != set(expected):
        raise ReleaseError("installed file set differs from the package")
    for relative, path in actual.items():
        content = path.read_bytes()
        entry = expected[relative]
        if len(content) != entry["byteLength"] or _sha256(content) != entry["sha256"]:
            raise ReleaseError("installed file digest mismatch")


def activate_installed_skill(installed: Path, discovery_root: Path) -> Path:
    """Atomically expose one immutable installed version to Codex discovery."""

    installed = Path(installed).resolve()
    if not (installed / "SKILL.md").is_file() or installed.parent.name not in ALLOWED_SKILLS:
        raise ReleaseError("installed Skill path is invalid")
    discovery_root = Path(discovery_root).resolve()
    discovery_root.mkdir(parents=True, exist_ok=True)
    active = discovery_root / installed.parent.name
    if active.exists() and not active.is_symlink():
        raise ReleaseError("active Skill path exists and is not a managed symlink")
    if active.is_symlink() and active.resolve() == installed:
        return active
    temporary = discovery_root / f".{installed.parent.name}.activate-{os.getpid()}"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(installed, target_is_directory=True)
    try:
        os.replace(temporary, active)
    finally:
        if temporary.is_symlink():
            temporary.unlink()
    return active


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--root", type=Path, default=Path.cwd())
    build.add_argument("--skill", choices=sorted(ALLOWED_SKILLS), required=True)
    build.add_argument("--output", type=Path, required=True)
    install = subparsers.add_parser("install")
    install.add_argument("--package", type=Path, required=True)
    install.add_argument("--target", type=Path, required=True)
    install.add_argument("--expected-sha256", required=True)
    install.add_argument("--activate-root", type=Path)
    args = parser.parse_args(argv)
    if args.command == "build":
        path, digest = build_skill_package(args.root, args.skill, args.output)
        print(json.dumps({"package": str(path), "sha256": digest}, ensure_ascii=False))
    else:
        target, receipt = install_skill_package(
            args.package, args.target, expected_package_sha256=args.expected_sha256
        )
        active = activate_installed_skill(target, args.activate_root) if args.activate_root else None
        print(json.dumps({
            "installed": str(target),
            "receipt": str(receipt),
            **({"active": str(active)} if active else {}),
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
