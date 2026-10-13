"""Git sync and import orchestration for Ars Magica sources."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.campaigns.services import refresh_excerpt_flags
from apps.catalog.services import rebuild_catalog_for_books
from apps.library.services import import_book_file, list_source_markdown_files
from apps.search.services import ensure_fts_schema, rebuild_fts_for_books
from apps.sources.models import SourceSnapshot

logger = logging.getLogger(__name__)


class SourceSyncError(Exception):
    pass


def repo_path() -> Path:
    return Path(settings.CLAVIS_SOURCES_DIR) / settings.CLAVIS_SOURCE_REPO_NAME


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SourceSyncError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout.strip()


def _default_remote_branch(path: Path) -> str:
    try:
        ref = _run_git(["rev-parse", "--abbrev-ref", "origin/HEAD"], cwd=path)
        return ref.split("/")[-1]
    except SourceSyncError:
        return "main"


def _sha_equal(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left.startswith(right) or right.startswith(left)


@dataclass(frozen=True)
class UpdateCheck:
    """Result of comparing the imported snapshot to origin."""

    status: str  # available | current | missing | unknown
    remote_sha: str = ""
    imported_sha: str = ""
    message: str = ""

    @property
    def updates_available(self) -> bool:
        return self.status == "available"


def check_for_updates() -> UpdateCheck:
    """Fetch origin and compare remote HEAD to the current import commit.

    Does not reset the working tree — only ``fetch``. Safe to call on page load.
    """
    current = SourceSnapshot.current()
    imported = (current.commit_sha if current else "") or ""
    path = repo_path()

    if not (path / ".git").exists():
        return UpdateCheck(
            status="missing",
            imported_sha=imported,
            message="No local clone yet. Sync and import to fetch sources.",
        )

    try:
        _run_git(["fetch", "--depth", "1", "origin"], cwd=path)
        branch = _default_remote_branch(path)
        remote = _run_git(["rev-parse", f"origin/{branch}"], cwd=path)
    except SourceSyncError as exc:
        logger.info("Update check failed: %s", exc)
        return UpdateCheck(
            status="unknown",
            imported_sha=imported,
            message=str(exc) or "Could not reach the remote repository.",
        )

    if not imported or imported == "local-fixture":
        return UpdateCheck(
            status="available",
            remote_sha=remote,
            imported_sha=imported,
            message="Remote sources are ready to import.",
        )

    if _sha_equal(remote, imported):
        return UpdateCheck(
            status="current",
            remote_sha=remote,
            imported_sha=imported,
            message="Library matches the latest remote commit.",
        )

    return UpdateCheck(
        status="available",
        remote_sha=remote,
        imported_sha=imported,
        message="A newer commit is available on the remote.",
    )


def sync_repository(repo_url: str | None = None) -> tuple[Path, str]:
    """Clone or pull the configured source repository. Returns (path, commit)."""
    url = repo_url or settings.CLAVIS_SOURCE_REPO_URL
    path = repo_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if (path / ".git").exists():
        logger.info("Pulling sources in %s", path)
        _run_git(["fetch", "--depth", "1", "origin"], cwd=path)
        branch = _default_remote_branch(path)
        _run_git(["reset", "--hard", f"origin/{branch}"], cwd=path)
    else:
        if path.exists():
            shutil.rmtree(path)
        logger.info("Cloning %s into %s", url, path)
        _run_git(["clone", "--depth", "1", url, str(path)])

    commit = _run_git(["rev-parse", "HEAD"], cwd=path)
    return path, commit


def backup_database() -> Path | None:
    """Copy the current SQLite database as a last-good backup."""
    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not db_path.exists():
        return None
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    dest = Path(settings.CLAVIS_BACKUP_DIR) / f"clavis-{stamp}.sqlite3"
    shutil.copy2(db_path, dest)
    # Keep only the newest backup plus one previous.
    backups = sorted(Path(settings.CLAVIS_BACKUP_DIR).glob("clavis-*.sqlite3"), reverse=True)
    for old in backups[2:]:
        old.unlink(missing_ok=True)
    return dest


@transaction.atomic
def import_sources(
    *,
    sync: bool = True,
    pilot_only: bool = False,
    local_path: Path | None = None,
) -> SourceSnapshot:
    """Sync (optional) and import Markdown books into the library."""
    ensure_fts_schema()
    backup_database()

    if local_path is not None:
        path = Path(local_path)
        commit = "local-fixture"
        repo_url = f"file://{path}"
    else:
        if sync:
            path, commit = sync_repository()
        else:
            path = repo_path()
            if not path.exists():
                raise SourceSyncError("Source repository is missing. Run sync first.")
            commit = _run_git(["rev-parse", "HEAD"], cwd=path)
        repo_url = settings.CLAVIS_SOURCE_REPO_URL

    snapshot = SourceSnapshot.objects.create(
        repo_url=repo_url,
        commit_sha=commit,
        local_path=str(path),
        status=SourceSnapshot.Status.PENDING,
        message="Import in progress",
        is_current=False,
    )

    try:
        files = list_source_markdown_files(path, pilot_only=pilot_only)
        book_ids: list[int] = []
        for file_info in files:
            book = import_book_file(file_info, snapshot)
            book_ids.append(book.pk)

        rebuild_fts_for_books(book_ids)
        rebuild_catalog_for_books(book_ids)
        if getattr(settings, "CLAVIS_REBUILD_EMBEDDINGS_ON_IMPORT", False):
            from apps.search.embeddings import rebuild_embeddings_for_books

            rebuild_embeddings_for_books(book_ids)
        if getattr(settings, "CLAVIS_ENRICH_ON_IMPORT", False):
            from apps.catalog.enrichment import (
                collect_proposals,
                get_provider,
                persist_proposals,
            )

            provider = get_provider("dry-run")
            persist_proposals(
                collect_proposals(provider, snapshot=snapshot, book_ids=book_ids)
            )
        refresh_excerpt_flags()

        SourceSnapshot.objects.filter(is_current=True).update(is_current=False)
        snapshot.status = SourceSnapshot.Status.READY
        snapshot.message = f"Imported {len(book_ids)} book(s)"
        snapshot.is_current = True
        snapshot.save(update_fields=["status", "message", "is_current"])

        # Keep a single working library: drop books from older snapshots.
        from apps.library.models import Book

        Book.objects.exclude(snapshot=snapshot).delete()
        return snapshot
    except Exception as exc:
        logger.exception("Source import failed")
        snapshot.status = SourceSnapshot.Status.FAILED
        snapshot.message = str(exc)
        snapshot.save(update_fields=["status", "message"])
        raise
