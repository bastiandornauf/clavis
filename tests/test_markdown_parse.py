from clavis.markdown.parse import parse_sections, walk_sections
from clavis.markdown.render import render_markdown


def test_parse_sections_builds_tree_and_hashes():
    md = "# Title\n\nIntro\n\n## Child\n\nBody\n"
    roots = parse_sections(md)
    flat = walk_sections(roots)
    assert [s.title for s in flat] == ["Title", "Child"]
    assert flat[1].path == "title/child"
    assert flat[1].content_hash


def test_render_markdown_strips_script():
    html = render_markdown('Hello <script>alert(1)</script> **bold**')
    assert "<script>" not in html
    assert "<strong>bold</strong>" in html


def test_render_markdown_converts_source_br_tags():
    html = render_markdown("Line one<br>Line two")
    assert "&lt;br&gt;" not in html
    assert "Line one" in html and "Line two" in html


def test_parse_unescapes_asterisk_markers_in_titles():
    md = "## New Abilities\n\n#### Ceremony\\*\n\nUsed in rituals.\n"
    roots = parse_sections(md)
    flat = walk_sections(roots)
    assert flat[-1].title == "Ceremony*"
    assert "\\" not in flat[-1].title

