"""Reader helpers: TOC tree, section branches, navigation."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.library.models import Section

# 1 = top-level only (e.g. "Chapter 1: …"), 2 = + major sections, etc.
TOC_DEPTH_CHOICES = (1, 2, 3, 6)
DEFAULT_TOC_DEPTH = 3
DEFAULT_VIEW_MODE = "single"


def parse_toc_depth(raw: str | None, fallback: int = DEFAULT_TOC_DEPTH) -> int:
    try:
        value = int(raw) if raw is not None else fallback
    except (TypeError, ValueError):
        return fallback
    if value not in TOC_DEPTH_CHOICES:
        return fallback
    return value


def parse_view_mode(raw: str | None, fallback: str = DEFAULT_VIEW_MODE) -> str:
    if raw in {"single", "branch"}:
        return raw
    return fallback


def section_branch(section: Section) -> list[Section]:
    """Section plus following descendants until the next same-or-higher heading."""
    qs = (
        Section.objects.filter(book_id=section.book_id, position__gte=section.position)
        .order_by("position")
    )
    branch: list[Section] = []
    for item in qs:
        if item.pk == section.pk:
            branch.append(item)
            continue
        if item.level <= section.level:
            break
        branch.append(item)
    return branch


def branch_neighbors(
    section: Section,
) -> tuple[Section | None, Section | None]:
    """Previous/next sections at the same structural level (block navigation)."""
    qs = Section.objects.filter(book_id=section.book_id).order_by("position")
    prev_section = (
        qs.filter(position__lt=section.position, level__lte=section.level)
        .order_by("-position")
        .first()
    )
    branch = section_branch(section)
    end_position = branch[-1].position if branch else section.position
    next_section = (
        qs.filter(position__gt=end_position, level__lte=section.level)
        .order_by("position")
        .first()
    )
    return prev_section, next_section


def section_path_nodes(section: Section) -> list[Section]:
    """Root → … → ``section`` inclusive."""
    nodes: list[Section] = []
    node: Section | None = section
    guard = 0
    while node is not None and guard < 32:
        nodes.append(node)
        node = node.parent if node.parent_id else None
        guard += 1
    nodes.reverse()
    return nodes


@dataclass
class TocNode:
    section: Section
    children: list[TocNode] = field(default_factory=list)
    is_open: bool = False
    is_current: bool = False
    is_in_path: bool = False


def build_toc_tree(
    sections: list[Section],
    depth: int,
    current: Section,
) -> list[TocNode]:
    """Nested TOC for a details/summary tree view.

    ``depth`` controls how far the tree is initially expanded:
    nodes with ``level < depth`` start open. The path to ``current`` is
    always open so the active branch stays visible after navigation.
    """
    children_by_parent: dict[int | None, list[Section]] = {}
    for section in sections:
        children_by_parent.setdefault(section.parent_id, []).append(section)

    path_ids = {node.id for node in section_path_nodes(current)}

    def build(parent_id: int | None) -> list[TocNode]:
        nodes: list[TocNode] = []
        for section in children_by_parent.get(parent_id, ()):
            children = build(section.id)
            in_path = section.id in path_ids
            is_open = bool(children) and (section.level < depth or in_path)
            nodes.append(
                TocNode(
                    section=section,
                    children=children,
                    is_open=is_open,
                    is_current=section.id == current.id,
                    is_in_path=in_path,
                )
            )
        return nodes

    return build(None)


def reader_query(
    *,
    toc_depth: int,
    view_mode: str,
    extra: dict[str, str] | None = None,
) -> str:
    from django.utils.http import urlencode

    params = {"toc": str(toc_depth), "view": view_mode}
    if extra:
        for key, value in extra.items():
            if value:
                params[key] = value
    return urlencode(params)
