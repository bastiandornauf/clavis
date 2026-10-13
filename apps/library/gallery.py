"""Browse Atlas Games released Open License images from the source repo."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.sources.models import SourceSnapshot

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}
SKIP_NAMES = {"desktop.ini", ".ds_store", "thumbs.db"}
# Prefer a stable album order for the main Open License packs.
ALBUM_ORDER = (
    "",  # root logos
    "techniques",
    "forms",
    "house-symbols",
    "mythic-europe-map",
    "semita-errabunda",
)
ALBUM_TITLES = {
    "": "Logos & marks",
    "techniques": "Techniques",
    "forms": "Forms",
    "house-symbols": "House symbols",
    "mythic-europe-map": "Mythic Europe map",
    "semita-errabunda": "Semita Errabunda",
}
PREVIEW_MAX_EDGE = 1600
_TITLE_CLEAN_RE = re.compile(r"[\s_\-]+")
_SYMBOL_PREFIX_RE = re.compile(r"^symbol\s+", re.I)
_HIREZ_SUFFIX_RE = re.compile(r"\s*(sepia\s*)?hirez\s*$", re.I)


@dataclass(frozen=True)
class GalleryImage:
    relative_path: str
    album: str
    title: str
    suffix: str


@dataclass(frozen=True)
class GalleryAlbum:
    key: str
    title: str
    images: list[GalleryImage]


def released_images_root() -> Path | None:
    """Locate ``released-images`` under the current source checkout."""
    current = SourceSnapshot.current()
    candidates: list[Path] = []
    if current and current.local_path:
        candidates.append(Path(current.local_path) / "released-images")
    candidates.append(
        Path(settings.CLAVIS_SOURCES_DIR)
        / settings.CLAVIS_SOURCE_REPO_NAME
        / "released-images"
    )
    for path in candidates:
        if path.is_dir():
            return path.resolve()
    return None


def gallery_cache_dir() -> Path:
    path = Path(settings.CLAVIS_DATA_DIR) / "cache" / "released-images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def display_title(filename: str) -> str:
    stem = Path(filename).stem
    stem = _HIREZ_SUFFIX_RE.sub("", stem)
    stem = _SYMBOL_PREFIX_RE.sub("", stem)
    stem = stem.replace("MAP", "Map")
    stem = _TITLE_CLEAN_RE.sub(" ", stem).strip(" .")
    if not stem:
        return filename
    # Title-case short symbol names; keep mixed case art titles mostly intact.
    if stem.islower() or stem.isupper() or " " not in stem:
        return stem.title()
    return stem


def _album_key(relative: Path) -> str:
    parts = relative.parts
    if len(parts) == 1:
        return ""
    return parts[0]


def _album_title(key: str) -> str:
    if key in ALBUM_TITLES:
        return ALBUM_TITLES[key]
    return key.replace("-", " ").replace("_", " ").title()


def list_gallery_albums(root: Path | None = None) -> list[GalleryAlbum]:
    root = root or released_images_root()
    if root is None:
        return []

    buckets: dict[str, list[GalleryImage]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower() in SKIP_NAMES:
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        album = _album_key(path.relative_to(root))
        buckets.setdefault(album, []).append(
            GalleryImage(
                relative_path=rel,
                album=album,
                title=display_title(path.name),
                suffix=path.suffix.lower(),
            )
        )

    keys = [k for k in ALBUM_ORDER if k in buckets]
    keys.extend(sorted(k for k in buckets if k not in ALBUM_ORDER))
    return [
        GalleryAlbum(key=key, title=_album_title(key), images=buckets[key])
        for key in keys
        if buckets[key]
    ]


def resolve_gallery_file(relative_path: str, root: Path | None = None) -> Path:
    """Resolve a gallery-relative path, rejecting traversal."""
    root = (root or released_images_root())
    if root is None:
        raise FileNotFoundError("released-images not found")
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise FileNotFoundError(relative_path)
    candidate = (root / rel).resolve()
    if not candidate.is_file() or not candidate.is_relative_to(root.resolve()):
        raise FileNotFoundError(relative_path)
    if candidate.suffix.lower() not in IMAGE_SUFFIXES:
        raise FileNotFoundError(relative_path)
    return candidate


def _cache_path_for(source: Path, relative_path: str) -> Path:
    digest = hashlib.sha256(
        f"{relative_path}:{source.stat().st_mtime_ns}:{source.stat().st_size}".encode()
    ).hexdigest()[:20]
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", relative_path).strip("-")[:120]
    return gallery_cache_dir() / f"{safe}.{digest}.png"


def preview_png_path(source: Path, relative_path: str) -> Path:
    """Return a browser-friendly PNG path, converting TIFF when needed."""
    suffix = source.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return source

    cached = _cache_path_for(source, relative_path)
    if cached.is_file():
        return cached

    from PIL import Image, ImageOps

    with Image.open(source) as image:
        # 1-bit Open License symbols are often WhiteIsZero line art.
        if image.mode == "1":
            image = ImageOps.invert(image.convert("L"))
            image = image.convert("RGB")
        elif image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        image.thumbnail((PREVIEW_MAX_EDGE, PREVIEW_MAX_EDGE), Image.Resampling.LANCZOS)
        cached.parent.mkdir(parents=True, exist_ok=True)
        image.save(cached, format="PNG", optimize=True)
    return cached
