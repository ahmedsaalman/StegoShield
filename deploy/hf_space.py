"""Publish the committed app to a Hugging Face Space that builds the project's Dockerfile.

Usage:
    .venv/bin/hf auth login                                  # once, with a token that has write access
    .venv/bin/python -m deploy.hf_space --space OWNER/NAME   # or: make deploy-hf SPACE=OWNER/NAME

Only files committed at HEAD are published, so uncommitted edits never reach the public demo.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError, LocalTokenNotFoundError

REPO_ROOT = Path(__file__).resolve().parent.parent
SPACE_CARD = Path(__file__).with_name("space_README.md")

# Everything the Dockerfile copies, and nothing else: no tests, docs, data or notebooks.
DEPLOYED_PATHS = (
    "Dockerfile",
    ".dockerignore",
    "requirements.txt",
    "core",
    "ml",
    "api",
    "models",
    "experiments",
    "frontend",
)
FREE_SPACE_VCPUS = 2
SPACE_VARIABLES = {
    "STEGOSHIELD_ENABLE_HSTS": "1",
    # os.cpu_count() in the container can report the host's cores, not the Space's share.
    "STEGOSHIELD_MAX_CONCURRENT_JOBS": str(FREE_SPACE_VCPUS),
    # The container is reachable only through the Spaces proxy. Trusting X-Forwarded-For gives each visitor their
    # own rate-limit bucket instead of one shared bucket; a spoofed header only evades the limit, and the job cap
    # above still bounds CPU use.
    "FORWARDED_ALLOW_IPS": "*",
}
SPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$")
READ_ONLY_TOKEN_ROLE = "read"


class PublishPermissionError(Exception):
    """The token cannot publish to the requested Space; the message says what to change."""


def main(argv: list[str] | None = None) -> int:
    """Stage the committed app, then upload it to the Space (or only list it with --dry-run)."""
    args = _parse_args(argv)
    warn_about_uncommitted_changes()
    with tempfile.TemporaryDirectory() as temp_dir:
        staging_dir = stage_committed_files(Path(temp_dir))
        print(f"Staged {_describe(staging_dir)} from commit {_head_commit()}.")
        if args.dry_run:
            print("\n".join(sorted(str(p.relative_to(staging_dir)) for p in staging_dir.rglob("*") if p.is_file())))
            return 0
        try:
            publish(staging_dir, args.space, is_private=args.private)
        except (HfHubHTTPError, LocalTokenNotFoundError, PublishPermissionError) as error:
            print(f"[!] Upload failed: {error}", file=sys.stderr)
            return 1
    print(f"Space page: https://huggingface.co/spaces/{args.space}")
    print(f"App URL (share this one): {space_app_url(args.space)}")
    print("The Space now builds the Docker image; follow progress in the Space's Logs tab.")
    return 0


def stage_committed_files(staging_dir: Path) -> Path:
    """Extract the deployed paths at HEAD into staging_dir and add the Space card as README.md."""
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *DEPLOYED_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(staging_dir, filter="data")
    (staging_dir / "README.md").write_text(SPACE_CARD.read_text(encoding="utf-8"), encoding="utf-8")
    return staging_dir


def publish(staging_dir: Path, space_id: str, is_private: bool) -> None:
    """Create the Docker Space if needed, set its variables, and replace its files with staging_dir."""
    api = HfApi()
    check_token_can_publish(api.whoami(), space_id)
    api.create_repo(space_id, repo_type="space", space_sdk="docker", private=is_private, exist_ok=True)
    for key, value in SPACE_VARIABLES.items():
        api.add_space_variable(space_id, key, value)
    api.upload_folder(
        repo_id=space_id,
        repo_type="space",
        folder_path=staging_dir,
        commit_message=f"Deploy StegoShield {_head_commit()}",
        delete_patterns="*",  # mirror HEAD: files removed from the repo disappear from the Space too
    )


def check_token_can_publish(identity: dict, space_id: str) -> None:
    """Fail early, naming the token's real account, instead of with Hugging Face's bare 403.

    Raises:
        PublishPermissionError: the token is read-only, or its account cannot write to the Space's owner.
    """
    account = identity["name"]
    owner = space_id.split("/", 1)[0]
    writable_namespaces = {account.lower(), *(org["name"].lower() for org in identity.get("orgs", []))}
    if owner.lower() not in writable_namespaces:
        raise PublishPermissionError(
            f"The token belongs to the Hugging Face account {account!r}, which cannot publish under {owner!r}. "
            f"Set HF_SPACE to {account}/<name>, or use a token from the {owner!r} account."
        )
    role = identity.get("auth", {}).get("accessToken", {}).get("role")
    if role == READ_ONLY_TOKEN_ROLE:
        raise PublishPermissionError(f"The token of {account!r} is read-only. Create one with Write access.")


def space_app_url(space_id: str) -> str:
    """Direct URL of the running app; the app refuses to be framed, so share this, not the Space page."""
    subdomain = re.sub(r"[_.]", "-", space_id.replace("/", "-")).lower()
    return f"https://{subdomain}.hf.space"


def warn_about_uncommitted_changes() -> None:
    """Uncommitted edits are not deployed; say so rather than surprise the user."""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *DEPLOYED_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if status.strip():
        print("[!] Uncommitted changes in deployed files will NOT be published:", file=sys.stderr)
        print(status.rstrip(), file=sys.stderr)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--space", required=True, type=_space_id, help="Space id, OWNER/NAME")
    parser.add_argument("--private", action="store_true", help="create the Space as private (examiners need access)")
    parser.add_argument("--dry-run", action="store_true", help="stage and list the files without uploading")
    return parser.parse_args(argv)


def _space_id(value: str) -> str:
    if not SPACE_ID_PATTERN.match(value):
        raise argparse.ArgumentTypeError(f"expected OWNER/NAME, got {value!r}")
    return value


def _head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _describe(staging_dir: Path) -> str:
    files = [p for p in staging_dir.rglob("*") if p.is_file()]
    size_mb = sum(p.stat().st_size for p in files) / 1_000_000
    return f"{len(files)} files ({size_mb:.1f} MB)"


if __name__ == "__main__":
    sys.exit(main())
