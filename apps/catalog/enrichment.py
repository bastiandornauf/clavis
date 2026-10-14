"""Optional catalog enrichment for rule leftovers (dry-run first, LLM later)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from django.db.models import QuerySet
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.extractors import MIGHT_LINE_RE
from apps.catalog.models import CatalogEntry, EnrichmentProposal
from apps.library.models import Section
from apps.sources.models import SourceSnapshot

_SPECIALTIES = re.compile(r"\*Specialties:\s*[^*]+\*", re.IGNORECASE)
_FIRST_SENTENCE = re.compile(r"([^.!?\n]{20,180}[.!?])")


@dataclass(frozen=True)
class EnrichmentHint:
    section: Section
    proposed_entry_type: str
    proposed_name: str
    proposed_summary: str
    evidence: str
    confidence: float
    extractor: str
    provider: str
    notes: str = ""


class EnrichmentProvider(Protocol):
    name: str

    def propose(self, section: Section) -> EnrichmentHint | None: ...


def sections_without_definitions(
    *,
    snapshot: SourceSnapshot | None = None,
    book_ids: list[int] | None = None,
) -> QuerySet[Section]:
    current = snapshot or SourceSnapshot.current()
    if not current:
        return Section.objects.none()

    covered = CatalogEntry.objects.filter(
        snapshot=current,
        kind=CatalogEntry.Kind.DEFINITION,
    ).values_list("primary_section_stable_id", flat=True)

    qs = Section.objects.filter(book__snapshot=current).exclude(stable_id__in=covered)
    if book_ids:
        qs = qs.filter(book_id__in=book_ids)
    return qs.select_related("book")


def _is_plausible_leftover(section: Section) -> bool:
    title = (section.display_title or "").strip()
    body = (section.body_markdown or "").strip()
    if section.level < 1 or len(title) < 3:
        return False
    if len(body) < 40 and not MIGHT_LINE_RE.search(body[:400]):
        return False
    if re.fullmatch(r"[\d.\s]+", title):
        return False
    return True


def _signal_score(section: Section) -> int:
    """Higher = more likely a useful enrichment target for dry-run review."""
    lead = (section.body_markdown or "")[:400]
    if MIGHT_LINE_RE.search(lead):
        return 2
    if _SPECIALTIES.search(lead):
        return 2
    return 0


def interesting_leftover_sections(
    *,
    snapshot: SourceSnapshot | None = None,
    book_ids: list[int] | None = None,
    limit: int = 200,
    signal_only: bool = True,
) -> list[Section]:
    """Shortlist leftovers. Default: only high-signal patterns (Might / Specialties)."""
    signal: list[Section] = []
    weak: list[Section] = []
    for section in sections_without_definitions(snapshot=snapshot, book_ids=book_ids).iterator():
        if not _is_plausible_leftover(section):
            continue
        if _signal_score(section) > 0:
            signal.append(section)
        elif not signal_only:
            weak.append(section)
        if len(signal) >= limit:
            break
    if signal_only:
        return signal[:limit]
    # Prefer signal rows, then weak fillers up to limit.
    return (signal + weak)[:limit]


class DryRunHeuristicProvider:
    """No network: only emit typed, pattern-backed leftovers (reviewable)."""

    name = "dry-run"

    def __init__(self, *, include_untyped: bool = False) -> None:
        self.include_untyped = include_untyped

    def propose(self, section: Section) -> EnrichmentHint | None:
        title = section.display_title.strip()
        body = section.body_markdown or ""
        lead = body[:400]

        if MIGHT_LINE_RE.search(lead):
            return EnrichmentHint(
                section=section,
                proposed_entry_type=CatalogEntry.EntryType.CREATURE,
                proposed_name=title,
                proposed_summary=_summary_from_body(body),
                evidence=lead.strip()[:500],
                confidence=0.45,
                extractor="heuristic",
                provider=self.name,
                notes="Might pattern leftover that rules missed; review before accept.",
            )
        if _SPECIALTIES.search(lead):
            return EnrichmentHint(
                section=section,
                proposed_entry_type=CatalogEntry.EntryType.ABILITY,
                proposed_name=title,
                proposed_summary=_summary_from_body(body),
                evidence=lead.strip()[:500],
                confidence=0.4,
                extractor="heuristic",
                provider=self.name,
                notes="Specialties pattern leftover that rules missed; review before accept.",
            )
        if not self.include_untyped:
            return None
        return EnrichmentHint(
            section=section,
            proposed_entry_type="",
            proposed_name=title,
            proposed_summary=_summary_from_body(body),
            evidence=lead.strip()[:500],
            confidence=0.15,
            extractor="heuristic",
            provider=self.name,
            notes="Unclassified leftover; noise unless you asked for --include-untyped.",
        )


class NullProvider:
    """Explicit no-op when enrichment is disabled."""

    name = "null"

    def propose(self, section: Section) -> EnrichmentHint | None:
        return None


class RemoteLLMProvider:
    """Placeholder: requires API key; refuses offline rather than inventing."""

    name = "remote-llm"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key or "").strip()

    def propose(self, section: Section) -> EnrichmentHint | None:
        if not self.api_key:
            return None
        # Networked LLM calls stay deferred until a concrete provider is wired.
        raise NotImplementedError(
            "Remote LLM enrichment is not configured yet; use --provider dry-run."
        )


def get_provider(
    name: str,
    *,
    api_key: str | None = None,
    include_untyped: bool = False,
) -> EnrichmentProvider:
    key = (name or "dry-run").strip().lower()
    if key in {"dry-run", "heuristic", "dry_run"}:
        return DryRunHeuristicProvider(include_untyped=include_untyped)
    if key in {"null", "none", "off"}:
        return NullProvider()
    if key in {"remote", "remote-llm", "llm"}:
        return RemoteLLMProvider(api_key=api_key)
    raise ValueError(f"Unknown enrichment provider: {name}")


def collect_proposals(
    provider: EnrichmentProvider,
    *,
    snapshot: SourceSnapshot | None = None,
    book_ids: list[int] | None = None,
    limit: int = 50,
    include_untyped: bool = False,
) -> list[EnrichmentHint]:
    hints: list[EnrichmentHint] = []
    # Scan enough leftovers that signal rows are not starved by chapter fluff.
    scan_limit = max(limit * 20, 500) if include_untyped else max(limit * 40, 2000)
    for section in interesting_leftover_sections(
        snapshot=snapshot,
        book_ids=book_ids,
        limit=scan_limit,
        signal_only=not include_untyped,
    ):
        hint = provider.propose(section)
        if hint is None:
            continue
        if not include_untyped and not hint.proposed_entry_type:
            continue
        hints.append(hint)
        if len(hints) >= limit:
            break
    return hints


def persist_proposals(hints: list[EnrichmentHint]) -> int:
    created = 0
    for hint in hints:
        _, was_created = EnrichmentProposal.objects.update_or_create(
            snapshot=hint.section.book.snapshot,
            section_stable_id=hint.section.stable_id,
            proposed_name=hint.proposed_name[:512],
            provider=hint.provider,
            defaults={
                "book": hint.section.book,
                "section_path": hint.section.path,
                "proposed_entry_type": hint.proposed_entry_type,
                "proposed_summary": hint.proposed_summary[:512],
                "evidence": hint.evidence,
                "confidence": hint.confidence,
                "status": EnrichmentProposal.Status.PENDING,
                "extractor": hint.extractor,
                "notes": hint.notes,
                "reviewed_at": None,
            },
        )
        if was_created:
            created += 1
    return created


def accept_proposal(proposal: EnrichmentProposal) -> CatalogEntry | None:
    """Promote a reviewed proposal into a catalog entry (extractor=llm)."""
    if proposal.status == EnrichmentProposal.Status.ACCEPTED:
        return CatalogEntry.objects.filter(
            snapshot=proposal.snapshot,
            primary_section_stable_id=proposal.section_stable_id,
            name=proposal.proposed_name,
        ).first()

    entry_type = proposal.proposed_entry_type.strip()
    if entry_type not in CatalogEntry.EntryType.values:
        proposal.status = EnrichmentProposal.Status.SKIPPED
        proposal.notes = (proposal.notes + "\nSkipped: missing entry type.").strip()
        proposal.reviewed_at = timezone.now()
        proposal.save(update_fields=["status", "notes", "reviewed_at"])
        return None

    slug = slugify(proposal.proposed_name)[:255] or "entry"
    entry, _ = CatalogEntry.objects.update_or_create(
        snapshot=proposal.snapshot,
        entry_type=entry_type,
        slug=slug,
        primary_section_stable_id=proposal.section_stable_id,
        defaults={
            "book": proposal.book,
            "kind": CatalogEntry.Kind.DEFINITION,
            "name": proposal.proposed_name,
            "summary": proposal.proposed_summary,
            "section_path": proposal.section_path,
            "evidence": proposal.evidence,
            "extractor": proposal.extractor or "llm",
        },
    )
    proposal.status = EnrichmentProposal.Status.ACCEPTED
    proposal.reviewed_at = timezone.now()
    proposal.save(update_fields=["status", "reviewed_at"])
    return entry


def _summary_from_body(body: str) -> str:
    cleaned = re.sub(r"[*_`>#]+", "", body).strip()
    match = _FIRST_SENTENCE.search(cleaned)
    if match:
        return match.group(1).strip()[:512]
    return cleaned[:180].strip()
