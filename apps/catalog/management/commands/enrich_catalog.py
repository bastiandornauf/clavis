"""Collect or accept reviewable catalog enrichment proposals."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.catalog.enrichment import (
    accept_proposal,
    collect_proposals,
    get_provider,
    persist_proposals,
)
from apps.catalog.models import EnrichmentProposal
from apps.sources.models import SourceSnapshot


class Command(BaseCommand):
    help = (
        "Scan rule leftovers and write typed EnrichmentProposal rows "
        "(default provider: dry-run, no network, signal patterns only)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--provider",
            default="dry-run",
            help="dry-run (default), null, or remote-llm (requires key; not implemented)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max proposals to emit (default 50)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print hints without writing to the database",
        )
        parser.add_argument(
            "--include-untyped",
            action="store_true",
            help="Also emit low-confidence unclassified leftovers (noisy; off by default)",
        )
        parser.add_argument(
            "--accept-pending",
            action="store_true",
            help="Promote pending proposals that already have an entry type",
        )
        parser.add_argument(
            "--reject-pending",
            action="store_true",
            help="Mark all pending proposals as rejected",
        )
        parser.add_argument(
            "--clear-noise",
            action="store_true",
            help="Delete pending untyped / confidence<0.3 proposals (cleanup)",
        )
        parser.add_argument(
            "--clear-pending",
            action="store_true",
            help="Delete all pending proposals (e.g. after a rules rebuild)",
        )

    def handle(self, *args, **options) -> None:
        current = SourceSnapshot.current()
        if not current:
            raise CommandError("No current source snapshot. Import sources first.")

        if options["clear_pending"]:
            deleted, _ = EnrichmentProposal.objects.filter(
                snapshot=current,
                status=EnrichmentProposal.Status.PENDING,
            ).delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} pending proposal(s)."))
            return

        if options["clear_noise"]:
            deleted, _ = (
                EnrichmentProposal.objects.filter(
                    snapshot=current,
                    status=EnrichmentProposal.Status.PENDING,
                )
                .filter(Q(proposed_entry_type="") | Q(confidence__lt=0.3))
                .delete()
            )
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} noisy pending proposal(s)."))
            return

        if options["reject_pending"]:
            updated = EnrichmentProposal.objects.filter(
                snapshot=current,
                status=EnrichmentProposal.Status.PENDING,
            ).update(status=EnrichmentProposal.Status.REJECTED)
            self.stdout.write(self.style.WARNING(f"Rejected {updated} pending proposal(s)."))
            return

        if options["accept_pending"]:
            pending = (
                EnrichmentProposal.objects.filter(
                    snapshot=current,
                    status=EnrichmentProposal.Status.PENDING,
                )
                .exclude(proposed_entry_type="")
                .select_related("book")
            )
            accepted = 0
            skipped = 0
            for proposal in pending:
                entry = accept_proposal(proposal)
                if entry:
                    accepted += 1
                else:
                    skipped += 1
            self.stdout.write(
                self.style.SUCCESS(f"Accepted {accepted} proposal(s); skipped {skipped}.")
            )
            return

        try:
            provider = get_provider(
                options["provider"],
                api_key=getattr(settings, "CLAVIS_LLM_API_KEY", "") or None,
                include_untyped=options["include_untyped"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        try:
            hints = collect_proposals(
                provider,
                snapshot=current,
                limit=options["limit"],
                include_untyped=options["include_untyped"],
            )
        except NotImplementedError as exc:
            raise CommandError(str(exc)) from exc

        if options["dry_run"]:
            for hint in hints:
                self.stdout.write(
                    f"{hint.proposed_entry_type or 'untyped':10} "
                    f"c={hint.confidence:.2f}  {hint.proposed_name}  "
                    f"[{hint.section.book.slug}]"
                )
            scope = "includes untyped" if options["include_untyped"] else "typed/signal only"
            self.stdout.write(self.style.SUCCESS(f"Dry-run: {len(hints)} hint(s) ({scope})."))
            return

        created = persist_proposals(hints)
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote/updated proposals from {len(hints)} hint(s) "
                f"({created} newly created; typed/signal only by default)."
            )
        )
