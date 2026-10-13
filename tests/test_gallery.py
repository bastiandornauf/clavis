from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from PIL import Image

from apps.library.gallery import display_title, list_gallery_albums, preview_png_path
from apps.sources.models import SourceSnapshot


def _write_tif(path: Path) -> None:
    Image.new("1", (32, 32), color=1).save(path, format="TIFF")


@pytest.mark.django_db
def test_gallery_lists_albums_and_serves_converted_tiff(tmp_path: Path, client, settings):
    root = tmp_path / "released-images"
    (root / "forms").mkdir(parents=True)
    Image.new("RGB", (24, 24), color=(120, 40, 30)).save(root / "arm5sigil.png")
    _write_tif(root / "forms" / "ignem.tif")
    (root / "forms" / "desktop.ini").write_text("[trash]\n", encoding="utf-8")

    SourceSnapshot.objects.create(
        repo_url="file://fixture",
        commit_sha="gallery",
        local_path=str(tmp_path),
        status=SourceSnapshot.Status.READY,
        is_current=True,
    )
    settings.CLAVIS_DATA_DIR = tmp_path / "data"
    settings.CLAVIS_DATA_DIR.mkdir()

    albums = list_gallery_albums(root)
    assert [a.key for a in albums] == ["", "forms"]
    assert albums[0].images[0].title == "Arm5Sigil"
    assert albums[1].images[0].title == "Ignem"
    assert all(img.relative_path != "forms/desktop.ini" for a in albums for img in a.images)

    index = client.get(reverse("library:gallery"))
    assert index.status_code == 200
    assert b"Ignem" in index.content
    assert b"Forms" in index.content

    response = client.get(reverse("library:gallery_file", args=["forms/ignem.tif"]))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    # Force evaluation of streaming content.
    payload = b"".join(response.streaming_content)
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"

    blocked = client.get(reverse("library:gallery_file", args=["../secret.tif"]))
    assert blocked.status_code == 404


def test_display_title_strips_hirez_noise():
    assert display_title("symbol flambeau.tif") == "Flambeau"
    assert display_title("Darius of Flambeau Sepia HIREZ.tif") == "Darius of Flambeau"
    assert display_title("creo.tif") == "Creo"


def test_preview_converts_tiff(tmp_path: Path, settings):
    settings.CLAVIS_DATA_DIR = tmp_path / "data"
    settings.CLAVIS_DATA_DIR.mkdir()
    source = tmp_path / "line.tif"
    _write_tif(source)
    preview = preview_png_path(source, "line.tif")
    assert preview.suffix == ".png"
    assert preview.is_file()
    with Image.open(preview) as image:
        assert image.format == "PNG"
