from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse

from apps.library.models import Section
from apps.reader.services import build_toc_tree, section_branch
from apps.sources.services import import_sources
from clavis.markdown import render_markdown


@pytest.mark.django_db
def test_branch_includes_descendants(fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    spells = Section.objects.get(title="Spells")
    branch = section_branch(spells)
    titles = [section.title for section in branch]
    assert titles[0] == "Spells"
    assert "Pilum of Fire" in titles


@pytest.mark.django_db
def test_toc_tree_page_renders(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    section = Section.objects.get(title="Spells")
    url = reverse("reader:section", args=[section.book.slug, section.path])

    shallow = client.get(url, {"toc": "1", "view": "single"})
    assert shallow.status_code == 200
    assert b"toc-disclosure" in shallow.content
    assert b"Contents" in shallow.content
    assert b"toc-tree" in shallow.content
    assert b"toc-tree__twist" in shallow.content
    assert b"toc-tree__row" in shallow.content
    assert b"Include subsections" in shallow.content
    assert b'type="checkbox"' in shallow.content
    assert b'aria-label="Breadcrumb"' in shallow.content
    assert b"Definitive Edition Sample" in shallow.content
    assert b"javelin of fire" not in shallow.content.lower()

    pilum = Section.objects.get(title="Pilum of Fire")
    pilum_page = client.get(
        reverse("reader:section", args=[pilum.book.slug, pilum.path]),
        {"toc": "3", "view": "single"},
    )
    assert pilum_page.status_code == 200
    assert b"Spells" in pilum_page.content
    assert b"LEVEL 20" in pilum_page.content

    branch = client.get(url, {"toc": "6", "view": "branch"})
    assert branch.status_code == 200
    assert b"javelin of fire" in branch.content.lower()
    assert b"Include subsections" in branch.content
    assert b"Save &amp; organize" in branch.content


@pytest.mark.django_db
def test_branch_headings_nest_from_h2_and_markdown_source_is_available(
    client, fixture_markdown_dir: Path
):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    spells = Section.objects.get(title="Spells")
    level = Section.objects.get(title="LEVEL 20", parent=spells)
    pilum = Section.objects.get(title="Pilum of Fire")
    page = client.get(
        reverse("reader:section", args=[spells.book.slug, spells.path]),
        {"view": "branch"},
    ).content.decode()

    def heading_tag(section: Section) -> str:
        anchor = page.index(f'id="s-{section.stable_id[:12]}"')
        return page[page.index('<h', anchor) : page.index('<h', anchor) + 3]

    assert heading_tag(level) == "<h2"
    assert heading_tag(pilum) == "<h3"
    assert "data-markdown-toggle" in page
    assert 'class="markdown-source" data-markdown-source hidden' in page


@pytest.mark.django_db
def test_static_urls_carry_a_version(client):
    body = client.get(reverse("library:index")).content.decode()
    assert "/static/css/clavis.css?v=" in body


def test_br_tags_become_line_breaks():
    html = render_markdown("**Age:** 160<br>**Trait:** Bold")
    assert "&lt;br&gt;" not in html
    assert "Age" in html and "Trait" in html
    assert "<br" in html or "</p>\n<p>" in html


@pytest.mark.django_db
def test_toc_tree_opens_path_and_respects_depth(fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    chapter = Section.objects.get(title="Definitive Edition Sample")
    spells = Section.objects.get(title="Spells")
    all_sections = list(Section.objects.filter(book=chapter.book).order_by("position"))

    at_chapter = build_toc_tree(all_sections, depth=1, current=chapter)
    root = next(node for node in at_chapter if node.section.title == chapter.title)
    assert root.is_open is True
    assert any(child.section.title == "Spells" for child in root.children)
    # Depth 1: siblings of the selected chapter stay closed if they have children.
    closed_roots = [node for node in at_chapter if node.section.id != chapter.id and node.children]
    assert all(node.is_open is False for node in closed_roots)

    at_spells = build_toc_tree(all_sections, depth=1, current=spells)
    root = next(node for node in at_spells if node.section.title == chapter.title)
    spells_node = next(child for child in root.children if child.section.title == "Spells")
    assert root.is_open is True
    assert spells_node.is_open is True
    assert any(child.section.title == "LEVEL 20" for child in spells_node.children)
