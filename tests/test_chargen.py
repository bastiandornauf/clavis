from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.template.loader import render_to_string
from django.urls import reverse
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from apps.chargen.catalog import core_entries
from apps.chargen.core_tables import (
    CHILDHOOD_TOTAL_XP,
    FERAL_CHILDHOOD_XP,
    HOUSES,
    NATIVE_LANGUAGE_XP,
    RECOMMENDED_GAUNTLET_ABILITIES,
    SAMPLE_CHILDHOODS,
    SKILLED_PARENS_SPELLS,
    SKILLED_PARENS_XP,
    TYPE_BUDGETS,
)
from apps.chargen.creation import (
    VirtueFlaw,
    ability_learnable,
    ability_score_from_xp,
    ability_xp_for_score,
    add_aging_point,
    aging_outcome,
    aging_total,
    aging_years_required,
    art_score_from_xp,
    art_xp_for_score,
    can_know_spell,
    characteristic_cost,
    characteristics_for_play,
    characteristics_remaining,
    characteristics_spent,
    check_apprenticeship_minima,
    check_virtues_and_flaws,
    child_modifiers,
    childhood_ability_allowed,
    childhood_package_xp,
    experience_pools,
    experience_pools_from_picks,
    known_spell,
    later_life_xp_rate,
    max_ability_score,
    post_gauntlet_year_points,
    recommended_gauntlet_xp,
    resolve_aging,
    sample_childhood,
    size_for_play,
    spell_level_cap,
    starting_confidence,
    stress_die,
    vf_points,
)
from apps.chargen.pdf_fill import (
    MSG_EMPTY,
    MSG_NO_FIELDS,
    MSG_NO_FILE,
    MSG_NOT_PDF,
    MSG_UNKNOWN,
    PdfFillError,
    fill_character_pdf,
    identify_template,
    read_uploaded_pdf,
)
from apps.chargen.play import casting_parts, play_overlay, voice_penalties, wound_levels
from apps.chargen.vf_effects import apply_vf_effects, boost_xp, vf_slug
from apps.chargen.views import VF_PAGE_SIZE
from apps.chargen.worksheet import (
    _ability_scores,
    _phase_editor_rows,
    apply_post,
    default_state,
    house_suggestion_rows,
    learnable_spell_rows,
    life_path,
    living_condition_choices,
    meter_for,
    note_placeholder,
    picks_from_state,
    sheet_context,
    sheet_json,
    sheet_markdown,
    step_brief,
    step_checklist,
    target_prompt,
    validate_step,
    vf_category_options,
    virtue_sheet_name,
    write_overlay,
)
from apps.sources.services import import_sources

# Darius of Flambeau, Core characteristic example (Int +3, Per +1, Pre −3, Com −1,
# Sta 0, Qik +2, Str +2, Dex +1) spends exactly 7 points.
DARIUS_SCORES = {
    "int": 3,
    "per": 1,
    "str": 2,
    "sta": 0,
    "pre": -3,
    "com": -1,
    "dex": 1,
    "qik": 2,
}


def test_characteristic_cost_table():
    assert [characteristic_cost(s) for s in (3, 2, 1, 0, -1, -2, -3)] == [6, 3, 1, 0, -1, -3, -6]


def test_darius_characteristics_spend_seven_points():
    assert characteristics_spent(DARIUS_SCORES) == 7
    assert characteristics_remaining(DARIUS_SCORES) == 0


def test_ability_and_art_xp_match_core_formulas():
    assert ability_xp_for_score(0) == 0
    assert ability_xp_for_score(1) == 5
    assert ability_xp_for_score(2) == 15
    assert ability_xp_for_score(5) == NATIVE_LANGUAGE_XP
    assert ability_score_from_xp(75) == (5, 0)
    assert ability_score_from_xp(16) == (2, 1)
    assert art_xp_for_score(1) == 1
    assert art_xp_for_score(10) == 55
    assert art_xp_for_score(15) == 120
    assert art_score_from_xp(54) == (9, 9)


def test_age_caps_ability_scores():
    assert max_ability_score(25) == 5
    assert max_ability_score(30) == 6
    assert max_ability_score(35) == 6
    assert max_ability_score(36) == 7
    assert max_ability_score(46) == 9
    assert max_ability_score(25, affinity=True) == 7


def test_spell_level_cap_is_arts_plus_int_plus_magic_theory_plus_three():
    cap = spell_level_cap(technique=10, form=10, intelligence=3, magic_theory=4)
    assert cap == 30
    assert can_know_spell(30, technique=10, form=10, intelligence=3, magic_theory=4)
    assert not can_know_spell(31, technique=10, form=10, intelligence=3, magic_theory=4)


def test_childhood_ability_whitelist():
    assert childhood_ability_allowed("Athletics")
    assert childhood_ability_allowed("Area Lore (Bavaria)")
    assert childhood_ability_allowed("Living Language")
    assert not childhood_ability_allowed("Magic Theory")
    assert not childhood_ability_allowed("Parma Magica")


def test_sample_childhoods_spend_exactly_the_childhood_pool():
    assert len(SAMPLE_CHILDHOODS) == 5
    for package in SAMPLE_CHILDHOODS:
        assert childhood_package_xp(package) == CHILDHOOD_TOTAL_XP
        for name, _score in package.abilities:
            if name.casefold().startswith("native language"):
                continue
            assert childhood_ability_allowed(name)
    traveling = sample_childhood("Traveling")
    assert traveling.name == "Traveling"


def test_grog_budget_three_minor_flaws():
    picks = [
        VirtueFlaw("Covenfolk", "virtue", "Free", "Social Status"),
        VirtueFlaw("Tough", "virtue", "Minor", "General"),
        VirtueFlaw("Missing Eye", "flaw", "Minor", "General"),
    ]
    totals = check_virtues_and_flaws("grog", picks)
    assert (totals.virtue_points, totals.flaw_points, totals.remaining) == (1, 1, 0)
    assert totals.legal


def test_grog_cannot_take_the_gift():
    totals = check_virtues_and_flaws(
        "grog",
        [VirtueFlaw("The Gift", "virtue", "Free", "Special")],
    )
    assert any(issue.code == "gift_on_grog" for issue in totals.issues)


def test_hermetic_virtue_without_gift_is_an_error():
    totals = check_virtues_and_flaws(
        "companion",
        [
            VirtueFlaw("Wanderer", "virtue", "Free", "Social Status"),
            VirtueFlaw("Puissant Art", "virtue", "Minor", "Hermetic"),
            VirtueFlaw("Missing Ear", "flaw", "Minor", "General"),
        ],
    )
    assert any(issue.code == "hermetic_without_gift" for issue in totals.issues)
    assert not totals.legal


def test_grog_major_and_story_flaws_are_illegal():
    totals = check_virtues_and_flaws(
        "grog",
        [
            VirtueFlaw("Covenfolk", "virtue", "Free", "Social Status"),
            VirtueFlaw("Giant Blood", "virtue", "Major", "General"),
            VirtueFlaw("Enemy", "flaw", "Major", "Story"),
        ],
    )
    codes = {issue.code for issue in totals.issues}
    assert {"major_on_grog", "story_on_grog"} <= codes
    assert not totals.legal


def test_missing_social_status_is_illegal():
    totals = check_virtues_and_flaws("companion", [])
    assert any(issue.code == "need_social_status" for issue in totals.issues)
    assert not totals.legal


def test_magus_without_hermetic_magus_is_illegal():
    totals = check_virtues_and_flaws(
        "magus",
        [VirtueFlaw("The Gift", "virtue", "Free")],
    )
    assert any(issue.code == "magus_needs_status" for issue in totals.issues)
    assert not totals.legal


def test_virtue_points_cannot_exceed_flaw_points():
    totals = check_virtues_and_flaws(
        "companion",
        [
            VirtueFlaw("Knight", "virtue", "Minor", "Social Status"),
            VirtueFlaw("Tough", "virtue", "Minor", "General"),
        ],
    )
    assert any(issue.code == "virtue_overspend" for issue in totals.issues)


def test_flaw_points_cannot_exceed_type_cap():
    flaws = [VirtueFlaw(f"Flaw {i}", "flaw", "Major", "General") for i in range(4)]
    totals = check_virtues_and_flaws("companion", flaws)
    assert totals.flaw_points == 12
    assert any(issue.code == "flaw_overspend" for issue in totals.issues)


def test_magus_needs_the_gift_and_may_take_hermetic_status():
    totals = check_virtues_and_flaws(
        "magus",
        [
            VirtueFlaw("The Gift", "virtue", "Free"),
            VirtueFlaw("Hermetic Magus", "virtue", "Free", "Social Status"),
            VirtueFlaw("Puissant Ignem", "virtue", "Minor", "Hermetic"),
            VirtueFlaw("Necessary Condition", "flaw", "Major", "Hermetic"),
        ],
    )
    assert totals.has_gift and totals.has_hermetic_magus
    assert totals.virtue_points == 1
    assert totals.flaw_points == 3
    assert totals.legal


def test_magus_without_a_hermetic_flaw_is_illegal():
    totals = check_virtues_and_flaws(
        "magus",
        [
            VirtueFlaw("The Gift", "virtue", "Free"),
            VirtueFlaw("Hermetic Magus", "virtue", "Free", "Social Status"),
            VirtueFlaw("Puissant Ignem", "virtue", "Minor", "Hermetic"),
            VirtueFlaw("Missing Ear", "flaw", "Minor", "General"),
        ],
    )
    assert any(issue.code == "magus_needs_hermetic_flaw" for issue in totals.issues)
    assert not totals.legal


def test_two_major_personality_flaws_are_illegal():
    totals = check_virtues_and_flaws(
        "companion",
        [
            VirtueFlaw("Wanderer", "virtue", "Free", "Social Status"),
            VirtueFlaw("Driven", "flaw", "Major", "Personality"),
            VirtueFlaw("Wrathful", "flaw", "Major", "Personality"),
        ],
    )
    assert any(issue.code == "two_major_personality" for issue in totals.issues)
    assert not totals.legal


def test_wealthy_and_poor_are_companion_only_and_exclusive():
    magus = check_virtues_and_flaws(
        "magus",
        [
            VirtueFlaw("The Gift", "virtue", "Free"),
            VirtueFlaw("Hermetic Magus", "virtue", "Free", "Social Status"),
            VirtueFlaw("Wealthy", "virtue", "Major", "General"),
            VirtueFlaw("Obsession", "flaw", "Major", "Personality"),
        ],
    )
    assert any(issue.code == "wealthy_poor_companions" for issue in magus.issues)
    both = check_virtues_and_flaws(
        "companion",
        [
            VirtueFlaw("Wanderer", "virtue", "Free", "Social Status"),
            VirtueFlaw("Wealthy", "virtue", "Major", "General"),
            VirtueFlaw("Poor", "flaw", "Major", "General"),
        ],
    )
    assert any(issue.code == "wealthy_and_poor" for issue in both.issues)


def test_darius_later_life_five_years_at_standard_rate():
    # Childhood 5, apprenticeship from 10, gauntlet 25.
    pools = experience_pools(character_type="magus", age=25, apprenticeship_start_age=10)
    assert pools.later_life_years == 5
    assert pools.later_life_xp == 75
    assert pools.apprenticeship_xp == 240
    assert pools.apprenticeship_spell_levels == 120
    assert pools.post_gauntlet_years == 0
    assert not pools.aging_warning


def test_companion_later_life_and_wealthy():
    standard = experience_pools(character_type="companion", age=25)
    assert standard.later_life_years == 20
    assert standard.later_life_xp == 300
    assert later_life_xp_rate(wealthy=True) == 20
    wealthy = experience_pools(character_type="companion", age=25, wealthy=True)
    assert wealthy.later_life_xp == 400
    poor = experience_pools(character_type="companion", age=25, poor=True)
    assert poor.later_life_xp == 200
    extra = experience_pools(character_type="companion", age=25, privileged_upbringing=True)
    assert extra.extra_xp == 50


def test_post_gauntlet_points_and_aging_warning():
    pools = experience_pools(character_type="magus", age=45, apprenticeship_start_age=10)
    assert pools.post_gauntlet_years == 20
    assert pools.post_gauntlet_points == 600
    assert pools.aging_warning
    assert any(issue.code == "aging" for issue in pools.issues)


def test_ability_gates_by_life_path_phase():
    assert ability_learnable(category="General", phase="later_life")
    assert not ability_learnable(category="Academic", phase="later_life")
    assert ability_learnable(
        category="Academic", phase="later_life", granted_categories=frozenset({"academic"})
    )
    assert ability_learnable(category="Martial", phase="apprenticeship")
    assert not ability_learnable(category="Supernatural", phase="apprenticeship")
    assert not ability_learnable(name="Magic Theory", category="Arcane", phase="childhood")
    assert ability_learnable(name="Athletics", category="General", phase="childhood")


def test_apprenticeship_minima_and_reading_notes():
    errors = check_apprenticeship_minima({"Latin": 1, "Magic Theory": 1, "Parma Magica": 1})
    codes = {issue.code for issue in errors}
    assert "apprenticeship_minimum" not in codes
    assert "cannot_read_order_books" in codes
    assert "weak_magic_theory" in codes
    missing = check_apprenticeship_minima({})
    assert any(issue.blocks for issue in missing)
    ready = check_apprenticeship_minima(
        {"Latin": 4, "Artes Liberales": 1, "Magic Theory": 3, "Parma Magica": 1}
    )
    assert ready == ()


def test_grogs_have_no_confidence():
    assert starting_confidence("grog") is None
    assert starting_confidence("companion") == (1, 3)
    assert starting_confidence("magus") == (1, 3)


def test_classic_vf_effects_change_the_xp_pools():
    assert vf_slug("Great (Characteristic)") == "great-characteristic"
    wealthy = apply_vf_effects(
        [VirtueFlaw("Wealthy", "virtue", "Major", "General", slug="wealthy")]
    )
    assert wealthy.later_life_xp_per_year == 20
    educated = apply_vf_effects(
        [VirtueFlaw("Educated", "virtue", "Minor", "General")]
    )
    assert educated.extra_xp == 50
    assert "academic" in educated.granted_categories
    warrior = apply_vf_effects([VirtueFlaw("Warrior", "virtue", "Minor")])
    assert "martial" in warrior.granted_categories
    parens = apply_vf_effects([VirtueFlaw("Skilled Parens", "virtue", "Minor", "Hermetic")])
    assert parens.apprenticeship_xp_delta == SKILLED_PARENS_XP
    assert parens.apprenticeship_spell_delta == SKILLED_PARENS_SPELLS
    improved = apply_vf_effects(
        [
            VirtueFlaw("Improved Characteristics", "virtue", "Minor"),
            VirtueFlaw("Improved Characteristics", "virtue", "Minor"),
        ]
    )
    assert improved.characteristic_points_delta == 6
    sight = apply_vf_effects([VirtueFlaw("Second Sight", "virtue", "Minor", "Supernatural")])
    assert ("Second Sight", 1) in sight.free_abilities
    giant = apply_vf_effects(
        [
            VirtueFlaw("Giant Blood", "virtue", "Major"),
            VirtueFlaw("Large", "virtue", "Minor"),
        ]
    )
    assert any(issue.code == "vf_incompatible" for issue in giant.issues)
    covenfolk_rich = apply_vf_effects(
        [
            VirtueFlaw("Covenfolk", "virtue", "Free", "Social Status"),
            VirtueFlaw("Wealthy", "virtue", "Major"),
        ]
    )
    assert any(issue.code == "wealthy_poor_status" for issue in covenfolk_rich.issues)
    assert boost_xp(37, extra_per=2) == 56
    magus = experience_pools_from_picks(
        character_type="magus",
        age=25,
        apprenticeship_start_age=10,
        picks=[VirtueFlaw("Skilled Parens", "virtue", "Minor", "Hermetic")],
    )[0]
    assert magus.apprenticeship_xp == 300
    assert magus.apprenticeship_spell_levels == 150
    feral = experience_pools_from_picks(
        character_type="grog",
        age=25,
        picks=[VirtueFlaw("Feral Upbringing", "flaw", "Minor")],
    )[0]
    assert feral.native_language_xp == 0
    assert feral.childhood_xp == FERAL_CHILDHOOD_XP
    stacked = experience_pools_from_picks(
        character_type="companion",
        age=25,
        picks=[
            VirtueFlaw("Educated", "virtue", "Minor"),
            VirtueFlaw("Warrior", "virtue", "Minor"),
            VirtueFlaw("Privileged Upbringing", "virtue", "Minor"),
        ],
    )[0]
    assert stacked.extra_xp == 150


def test_child_modifiers_and_aging_and_gauntlet_package():
    assert child_modifiers(25) == (0, 0)
    assert child_modifiers(7) == (-4, -2)
    assert child_modifiers(10) == (-2, -2)
    play = characteristics_for_play({"str": 3, "int": 1}, 7)
    assert play["str"] == -1
    assert size_for_play(age=10, virtue_size=1) == -1
    assert aging_years_required(35) == 0
    assert aging_years_required(45) == 10
    assert aging_total(die=5, age=40, living_conditions=1) == 5 + 4 - 1
    assert aging_total(die=16, age=40) == 16 + 4
    assert aging_total(die=0, age=40) == 4
    low = aging_outcome(2)
    assert low.apparent_age_increase == 0 and not low.crisis
    crisis = aging_outcome(13)
    assert crisis.crisis and crisis.next_decrepitude
    assert post_gauntlet_year_points(0) == 30
    assert post_gauntlet_year_points(2) == 10
    assert post_gauntlet_year_points(3) == 0
    assert recommended_gauntlet_xp() == 90
    assert len(RECOMMENDED_GAUNTLET_ABILITIES) == 4
    custom = known_spell("A custom bolt", "Cr", "Ig", 15)
    assert custom.technique == "Creo" and custom.form == "Ignem" and custom.cost == 15
    corpus = known_spell("Dust", "Pe", "Corporem", 15)
    assert corpus.form == "Corpus"
    grog = experience_pools(character_type="grog", age=40)
    assert grog.apprenticeship_xp == 0
    assert grog.aging_years == 5
    assert childhood_ability_allowed("Hunt", feral=True)
    assert not childhood_ability_allowed("Hunt")


def test_twelve_houses_and_type_budgets():
    assert len(HOUSES) == 12
    assert {house.name for house in HOUSES} >= {"Flambeau", "Guernicus", "Ex Miscellanea"}
    assert TYPE_BUDGETS["grog"].max_flaw_points == 3
    assert TYPE_BUDGETS["magus"].max_flaw_points == 10
    assert vf_points("Minor") == 1 and vf_points("Major") == 3 and vf_points("Free") == 0


@pytest.mark.django_db
def test_clavisgen_home_uses_core_lexicon(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    response = client.get(reverse("chargen:home"))
    assert response.status_code == 200
    assert b"ClavisGen" in response.content
    assert b"Create a Companion" in response.content
    assert b"10 Flaw points and 300 later-life XP at age 25." in response.content
    assert b"Create a Magus" in response.content
    assert b"Magi pick a House" not in response.content
    assert b"One working copy in this browser" in response.content
    assert b"tab=characters" in response.content


def _continue(client, step: str, **fields):
    data = {"step": step, "action": "next", **fields}
    return client.post(reverse("chargen:new"), data, follow=True)


@pytest.mark.django_db
def test_worksheet_creates_a_companion(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    assert client.get(reverse("chargen:new"), follow=True).status_code == 200
    page = _continue(
        client,
        "start",
        name="Ava",
        character_type="companion",
        age="25",
        native_language="English",
        concept="A wandering hunter",
    )
    assert b"Virtues and Flaws" in page.content
    client.post(
        reverse("chargen:new"),
        {"step": "virtues", "action": "save", "add_slug": "wanderer"},
        follow=True,
    )
    page = _continue(client, "virtues")
    assert b"Characteristics" in page.content
    page = _continue(
        client,
        "characteristics",
        int="2",
        per="0",
        str="0",
        sta="2",
        pre="0",
        com="0",
        dex="0",
        qik="1",
    )
    assert b"Early childhood" in page.content
    page = _continue(client, "childhood", childhood_package="Social")
    assert b"Later life" in page.content
    assert b"Charm 2" in page.content
    later = client.get(f"{reverse('chargen:new')}?step=later_life")
    assert b"later_name_new" in later.content
    assert b'name="later_xp"' in later.content
    assert b"On the sheet" in later.content
    page = _continue(
        client,
        "later_life",
        later_name_new="Awareness",
        later_score_new="2",
    )
    assert b"Personality" in page.content
    page = _continue(
        client,
        "details",
        trait_name="Brave",
        trait_score="2",
        equipment="A bow and a pack",
    )
    assert page.status_code == 200
    assert b"Ava" in page.content
    assert b"Companion" in page.content
    assert b"English" in page.content
    assert b"Awareness 2" in page.content
    assert b"Charm 2" in page.content


def test_score_post_stores_triangular_xp():
    post = QueryDict(mutable=True)
    post.update({"later_name_new": "Awareness", "later_score_new": "2"})
    state = apply_post("later_life", default_state(), post)
    assert state["later_life"] == [
        {"name": "Awareness", "xp": 15, "specialty": ""},
    ]
    post = QueryDict(mutable=True)
    post.update({"art_creo": "5"})
    state = apply_post("apprenticeship", default_state(), post)
    assert state["arts"]["creo"] == art_xp_for_score(5)


def test_custom_ability_name_from_free_text():
    post = QueryDict(mutable=True)
    post.update(
        {
            "later_name_new": "__custom__",
            "later_name_custom": "Siege Engineering",
            "later_score_new": "2",
        }
    )
    state = apply_post("later_life", default_state(), post)
    assert state["later_life"] == [
        {"name": "Siege Engineering", "xp": 15, "specialty": ""},
    ]
    post = QueryDict(mutable=True)
    post.update({"later_name_custom": "Hunt", "later_score_new": "1"})
    state = apply_post("later_life", default_state(), post)
    assert state["later_life"][0]["name"] == "Hunt"


@pytest.mark.django_db
def test_ability_add_without_score_stays_off_the_sheet():
    post = QueryDict(mutable=True)
    post.update({"later_name_new": "Awareness", "action": "add_row"})
    state = apply_post("later_life", default_state(), post)
    assert state["later_life"] == [
        {"name": "Awareness", "xp": 0, "specialty": ""},
    ]
    names = [row["name"] for row in sheet_context(state)["abilities"] if row["score"]]
    assert "Awareness" not in names


def test_later_life_lists_known_abilities_and_stores_only_the_raise():
    state = default_state()
    state["native_language"] = "English"
    state["childhood"] = [{"name": "Hunt", "xp": 15, "specialty": "deer"}]
    applied = apply_vf_effects(picks_from_state(state))
    rows = {row["name"]: row for row in _phase_editor_rows(state, "later_life", applied)}
    assert rows["Hunt"]["score"] == 2
    assert rows["Hunt"]["xp"] == 0
    assert rows["Hunt"]["sheet_score"] == 2
    assert rows["English"]["score"] == 5
    post = QueryDict(mutable=True)
    post.setlist("later_name", ["Hunt", "English"])
    post.setlist("later_score", ["3", "5"])
    post.setlist("later_spec", ["deer", ""])
    state = apply_post("later_life", state, post)
    assert state["later_life"] == [{"name": "Hunt", "xp": 15, "specialty": "deer"}]


def test_magic_theory_asterisk_is_the_same_ability_as_the_recommended_score():
    state = default_state()
    state["apply_minima"] = True
    state["apprenticeship"] = [{"name": "Magic Theory*", "xp": 5, "specialty": ""}]
    applied = apply_vf_effects(picks_from_state(state))
    theory = [row for row in _ability_scores(state, 25, applied) if row["name"] == "Magic Theory"]
    assert len(theory) == 1
    assert theory[0]["score"] == 3
    shown = [
        row
        for row in _phase_editor_rows(state, "apprenticeship", applied)
        if row["name"] == "Magic Theory"
    ]
    assert len(shown) == 1
    assert shown[0]["score"] == 3
    assert shown[0]["min_score"] == 3
    post = QueryDict(mutable=True)
    post.update({"apply_minima": "1", "appr_name_new": "Magic Theory*", "action": "add_row"})
    saved = apply_post("apprenticeship", default_state(), post)
    assert saved["apprenticeship"] == []


def test_raising_a_recommended_ability_shows_this_phase_cost():
    state = default_state()
    state["character_type"] = "magus"
    state["apply_minima"] = True
    applied = apply_vf_effects(picks_from_state(state))
    rows = {row["name"]: row for row in _phase_editor_rows(state, "apprenticeship", applied)}
    theory = rows["Magic Theory"]
    assert theory["score"] == 3
    assert theory["paid_score"] == 0
    assert theory["min_score"] == 3
    assert theory["phase_xp"] == ability_xp_for_score(3)
    assert theory["phase_note"] == f"+{ability_xp_for_score(3)}"

    post = QueryDict(mutable=True)
    post["apply_minima"] = "1"
    names = list(rows)
    post.setlist("appr_name", names)
    post.setlist(
        "appr_score",
        ["4" if name == "Magic Theory" else str(rows[name]["score"]) for name in names],
    )
    post.setlist("appr_spec", [rows[name]["specialty"] for name in names])
    post.setlist("appr_xp", ["0"] * len(names))
    state = apply_post("apprenticeship", state, post)
    extra = ability_xp_for_score(4) - ability_xp_for_score(3)
    assert state["apprenticeship"] == [{"name": "Magic Theory", "xp": extra, "specialty": ""}]
    theory = next(
        row
        for row in _phase_editor_rows(
            state, "apprenticeship", apply_vf_effects(picks_from_state(state))
        )
        if row["name"] == "Magic Theory"
    )
    assert theory["score"] == 4
    assert theory["paid_score"] == 0
    assert theory["min_score"] == 3
    assert theory["phase_xp"] == ability_xp_for_score(4)
    assert theory["phase_note"] == f"+{ability_xp_for_score(4)}"


def test_spell_list_hides_levels_the_arts_cannot_learn():
    class Entry:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    ctx = {
        "arts": [
            {"name": "Creo", "score": 0, "bonus": 0},
            {"name": "Ignem", "score": 0, "bonus": 0},
        ],
        "abilities": [],
        "play": {"int": 0},
    }
    rows = learnable_spell_rows(
        ctx,
        [
            Entry(
                name="Big",
                technique="Creo",
                form="Ignem",
                level=20,
                section_path="a",
                primary_section_stable_id="1",
            ),
            Entry(
                name="Small",
                technique="Creo",
                form="Ignem",
                level=2,
                section_path="b",
                primary_section_stable_id="2",
            ),
            Entry(
                name="Open",
                technique="Creo",
                form="Ignem",
                level=None,
                section_path="c",
                primary_section_stable_id="3",
            ),
        ],
    )
    names = [row["name"] for row in rows]
    assert names == ["Small", "Open"]
    open_spell = rows[1]
    assert open_spell["needs_level"] is True
    assert open_spell["cap"] == 3
    assert open_spell["suggested_level"] is None


@pytest.mark.django_db
def test_companion_start_hides_house_and_shows_rules_before_continue(
    client, fixture_markdown_dir: Path
):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    page = client.get(f"{reverse('chargen:new')}?as=companion")
    assert page.status_code == 200
    assert b'type="radio" name="character_type"' not in page.content
    assert b'name="house"' not in page.content
    assert b"Apprenticeship starts at age" not in page.content
    assert b"Name the companion" in page.content
    assert b"<p>Still open before Continue</p>" not in page.content
    assert b"Choose a different type" in page.content
    assert b"cg-rule" in page.content
    assert b"Detailed character creation" in page.content
    client.post(reverse("chargen:reset"))
    magus = client.get(f"{reverse('chargen:new')}?as=magus")
    assert b'type="radio" name="character_type"' not in magus.content
    assert b'name="house"' in magus.content
    assert b"Apprenticeship starts at age" in magus.content
    assert b"pick a House" in magus.content
    assert b"A magus must pick a House" not in magus.content


@pytest.mark.django_db
def test_virtue_catalog_paginates_matches(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(f"{reverse('chargen:new')}?as=companion")
    closed = client.get(f"{reverse('chargen:new')}?step=virtues")
    assert closed.status_code == 200
    assert b"Search by name, or choose a magnitude or category." in closed.content
    assert b">Next</a>" not in closed.content
    names = list(
        core_entries("virtue")
        .filter(magnitude__iexact="Minor")
        .values_list("name", flat=True)
    )
    page1 = client.get(f"{reverse('chargen:new')}?step=virtues&vf_magnitude=Minor")
    assert page1.status_code == 200
    if len(names) <= VF_PAGE_SIZE:
        assert b">Next</a>" not in page1.content
        return
    assert b">Next</a>" in page1.content
    assert names[0].encode() in page1.content
    assert names[VF_PAGE_SIZE].encode() not in page1.content
    page2 = client.get(f"{reverse('chargen:new')}?step=virtues&vf_magnitude=Minor&vf_page=2")
    assert b">Previous</a>" in page2.content
    assert names[VF_PAGE_SIZE].encode() in page2.content
    assert names[0].encode() not in page2.content


@pytest.mark.django_db
def test_virtue_filter_survives_add(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(f"{reverse('chargen:new')}?as=companion")
    response = client.post(
        reverse("chargen:new"),
        {
            "step": "virtues",
            "action": "save",
            "kind": "flaw",
            "vf_magnitude": "Minor",
            "vf_category": "General",
            "vf_q": "Poor",
            "vf_page": "2",
        },
    )
    location = response["Location"]
    assert "kind=flaw" in location
    assert "vf_magnitude=Minor" in location
    assert "vf_category=General" in location
    assert "vf_q=Poor" in location
    assert "vf_page=2" in location
    page = client.get(location)
    html = page.content.decode()
    assert 'value="flaw" selected' in html
    assert 'value="Minor" selected' in html
    assert 'name="vf_q" value="Poor"' in html or 'value="Poor"' in html


@pytest.mark.django_db
def test_worksheet_magus_needs_house_and_can_reach_spells(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new"))
    blocked = _continue(
        client,
        "start",
        name="Marcus",
        character_type="magus",
        age="25",
        apprenticeship_start_age="10",
    )
    assert b"A magus must pick a House" in blocked.content
    _continue(
        client,
        "start",
        name="Marcus",
        character_type="magus",
        age="25",
        house="Flambeau",
        apprenticeship_start_age="10",
        native_language="Latin",
    )
    for slug in ("the-gift", "hermetic-magus"):
        client.post(
            reverse("chargen:new"),
            {"step": "virtues", "action": "save", "add_slug": slug},
            follow=True,
        )
    client.post(
        reverse("chargen:new"),
        {
            "step": "virtues",
            "action": "save",
            "add_kind": "flaw",
            "add_slug": "necessary-condition",
        },
        follow=True,
    )
    page = _continue(client, "virtues")
    assert b"Characteristics" in page.content
    _continue(
        client,
        "characteristics",
        int="3",
        per="1",
        str="0",
        sta="0",
        pre="0",
        com="0",
        dex="0",
        qik="0",
    )
    _continue(client, "childhood", childhood_package="Exploring")
    _continue(client, "later_life")
    page = _continue(client, "apprenticeship", apply_minima="1")
    assert b"Spells" in page.content
    page = _continue(
        client,
        "spells",
        spell_name="A custom bolt",
        spell_te="Creo",
        spell_fo="Ignem",
        spell_level="5",
    )
    assert b"Personality" in page.content
    page = _continue(client, "details", trait_name="Brave", trait_score="3")
    assert b"Marcus" in page.content
    assert b"Flambeau" in page.content
    assert b"A custom bolt" in page.content
    assert b"Parma Magica" in page.content


@pytest.mark.django_db
def test_spend_sentence_matches_on_the_pool():
    state = default_state()
    state["character_type"] = "companion"
    state["age"] = 25
    ctx = sheet_context(state)
    assert meter_for("later_life", ctx) == "0 of 300 XP spent, 300 left."
    assert meter_for("characteristics", ctx) == "0 of 7 points spent, 7 left."
    assert meter_for("virtues", ctx) == "No Virtue or Flaw points spent yet."
    assert "Wanderer or Covenfolk" not in step_brief("virtues", ctx)


def test_affinity_without_a_target_is_refused():
    post = QueryDict(mutable=True)
    post.update({"add_slug": "affinity-with-art", "add_kind": "virtue"})
    state = apply_post("virtues", default_state(), post)
    assert state["virtues_flaws"] == []
    assert "Art" in state["form_notice"]


@pytest.mark.django_db
def test_after_art_field_is_the_sheet_score():
    state = default_state()
    state["arts"]["creo"] = art_xp_for_score(5)
    post = QueryDict(mutable=True)
    post.update({"after_art_creo": "6"})
    state = apply_post("after", state, post)
    assert state["after_arts"]["creo"] == art_xp_for_score(6) - art_xp_for_score(5)
    row = next(item for item in sheet_context(state)["arts"] if item["key"] == "creo")
    assert row["raw_score"] == 6
    assert row["paid_score"] == 5
    assert row["after"] == art_xp_for_score(6) - art_xp_for_score(5)


@pytest.mark.django_db
def test_art_xp_can_stop_short_of_the_next_score():
    post = QueryDict(mutable=True)
    post.update({"art_creo": "5", "art_xp_creo": "3"})
    state = apply_post("apprenticeship", default_state(), post)
    state["character_type"] = "magus"
    assert state["arts"]["creo"] == art_xp_for_score(5) + 3
    ctx = sheet_context(state)
    row = next(item for item in ctx["arts"] if item["key"] == "creo")
    assert row["bought_score"] == 5
    assert row["bought_toward"] == 3
    assert "Cr 5 (3 xp)" in ctx["sheet"]["art_lines"][0]
    later = QueryDict(mutable=True)
    later.update({"after_art_creo": "5", "after_art_xp_creo": "4"})
    state = apply_post("after", state, later)
    assert state["after_arts"]["creo"] == 1
    assert state["arts"]["creo"] + state["after_arts"]["creo"] == art_xp_for_score(5) + 4


@pytest.mark.django_db
def test_childhood_package_live_replaces_the_editor(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(f"{reverse('chargen:new')}?as=companion")
    response = client.post(
        reverse("chargen:new"),
        {"step": "childhood", "action": "live", "childhood_package": "Athletic"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b'id="score-editor"' in response.content
    assert b"This package writes" not in response.content
    assert b'value="Athletics"' in response.content
    assert b'name="child_score"' in response.content


@pytest.mark.django_db
def test_aging_dice_start_empty(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(f"{reverse('chargen:new')}?as=companion")
    client.post(
        reverse("chargen:new"),
        {
            "step": "start",
            "action": "next",
            "name": "Marcus",
            "character_type": "companion",
            "age": "40",
            "native_language": "English",
        },
    )
    page = client.get(f"{reverse('chargen:new')}?step=aging")
    assert b"Age 36" in page.content
    assert b'name="aging_die" value=""' in page.content
    assert b'name="aging_living_36"' in page.content
    assert b'name="aging_longevity_36"' in page.content
    assert b'name="living_conditions"' not in page.content
    assert b"Not rolled" in page.content


class _Faces:
    def __init__(self, faces: list[int]) -> None:
        self._faces = list(faces)

    def randint(self, _low: int, _high: int) -> int:
        return self._faces.pop(0)


def test_stress_die_is_open():
    assert stress_die(_Faces([7])) == 7
    assert stress_die(_Faces([10])) == 0
    assert stress_die(_Faces([1, 4])) == 8
    assert stress_die(_Faces([1, 1, 10])) == 40


@pytest.mark.django_db
def test_specialty_survives_when_this_phase_adds_no_xp():
    state = default_state()
    state["native_language"] = "English"
    state["childhood"] = [{"name": "Hunt", "xp": 15, "specialty": ""}]
    post = QueryDict(mutable=True)
    post.setlist("later_name", ["Hunt"])
    post.setlist("later_score", ["2"])
    post.setlist("later_spec", ["deer"])
    state = apply_post("later_life", state, post)
    assert state["later_life"] == [{"name": "Hunt", "xp": 0, "specialty": "deer"}]
    sheet = {row["name"]: row for row in sheet_context(state)["abilities"]}
    assert sheet["Hunt"]["specialty"] == "deer"


def test_childhood_package_fills_once_and_keeps_the_edit():
    state = default_state()
    post = QueryDict(mutable=True)
    post["childhood_package"] = "Athletic"
    state = apply_post("childhood", state, post)
    athletics = next(row for row in state["childhood"] if row["name"] == "Athletics")
    assert athletics["xp"] == ability_xp_for_score(2)
    assert athletics["specialty"] == ""
    post = QueryDict(mutable=True)
    post["childhood_package"] = "Athletic"
    post.setlist("child_name", ["Athletics", "Brawl", "Swim"])
    post.setlist("child_score", ["3", "2", "2"])
    post.setlist("child_spec", ["running", "", ""])
    state = apply_post("childhood", state, post)
    athletics = next(row for row in state["childhood"] if row["name"] == "Athletics")
    assert athletics["specialty"] == "running"
    assert athletics["xp"] == ability_xp_for_score(3)


@pytest.mark.django_db
def test_partial_xp_stays_short_of_the_next_score():
    state = default_state()
    post = QueryDict(mutable=True)
    post.setlist("child_name", ["Swim"])
    post.setlist("child_score", ["1"])
    post.setlist("child_xp", ["4"])
    post.setlist("child_spec", ["rivers"])
    state = apply_post("childhood", state, post)
    swim = next(row for row in state["childhood"] if row["name"] == "Swim")
    assert swim["xp"] == ability_xp_for_score(1) + 4
    row = next(item for item in sheet_context(state)["abilities"] if item["name"] == "Swim")
    assert row["score"] == 1
    assert row["leftover"] == 4
    assert "Swim 1 (rivers) (4 xp)" in sheet_context(state)["sheet"]["ability_line"]
    post = QueryDict(mutable=True)
    post.setlist("later_name", ["Swim"])
    post.setlist("later_score", ["1"])
    post.setlist("later_xp", ["9"])
    post.setlist("later_spec", ["rivers"])
    state = apply_post("later_life", state, post)
    assert state["later_life"] == [{"name": "Swim", "xp": 5, "specialty": "rivers"}]
    row = next(item for item in sheet_context(state)["abilities"] if item["name"] == "Swim")
    assert row["score"] == 1
    assert row["leftover"] == 9


@pytest.mark.django_db
def test_puissant_ability_plays_as_score_plus_bonus():
    state = default_state()
    state["character_type"] = "magus"
    state["apprenticeship"] = [
        {"name": "Magic Theory", "xp": ability_xp_for_score(5) + 10, "specialty": ""}
    ]
    state["virtues_flaws"] = [
        {
            "name": "Puissant Ability",
            "slug": "puissant-ability",
            "magnitude": "Minor",
            "category": "General",
            "target": "Magic Theory",
        }
    ]
    state["arts"]["creo"] = art_xp_for_score(5)
    state["arts"]["ignem"] = art_xp_for_score(5)
    ctx = sheet_context(state)
    row = next(item for item in ctx["abilities"] if item["name"] == "Magic Theory")
    assert row["score"] == 5
    assert row["bonus"] == 2
    assert row["leftover"] == 10
    assert "Magic Theory 5+2 (10 xp)" in ctx["sheet"]["ability_line"]
    post = QueryDict(mutable=True)
    post["spell_name"] = "Pilum of Fire"
    post["spell_te"] = "Creo"
    post["spell_fo"] = "Ignem"
    post["spell_level"] = "19"
    state = apply_post("spells", state, post)
    assert state["spells"][0]["level"] == 19
    post = QueryDict(mutable=True)
    post["spell_name"] = "Twist"
    post["spell_te"] = "Muto"
    post["spell_fo"] = "Vim"
    post["spell_level"] = "12"
    state = apply_post("spells", state, post)
    assert [spell["name"] for spell in state["spells"]] == ["Pilum of Fire"]
    assert "Muto Vim" in state["form_notice"]
    assert "cap of 10" in state["form_notice"]


def test_score_above_the_age_cap_stays_and_is_marked():
    state = default_state()
    state["age"] = 25
    state["childhood"] = [{"name": "Hunt", "xp": 15, "specialty": "deer"}]
    post = QueryDict(mutable=True)
    post.setlist("later_name", ["Hunt"])
    post.setlist("later_score", ["6"])
    post.setlist("later_spec", ["deer"])
    state = apply_post("later_life", state, post)
    applied = apply_vf_effects(picks_from_state(state))
    rows = {row["name"]: row for row in _phase_editor_rows(state, "later_life", applied)}
    assert rows["Hunt"]["score"] == 6
    assert rows["Hunt"]["cap"] == 5
    assert rows["Hunt"]["over_cap"] is True
    assert rows["Hunt"]["phase_note"] == "+90"


@pytest.mark.django_db
def test_rail_count_is_shorter_than_the_step_sentence():
    state = default_state()
    state["character_type"] = "companion"
    state["age"] = 25
    ctx = sheet_context(state)
    path = {row["key"]: row["summary"] for row in life_path("later_life", ctx)}
    assert path["later_life"] == "0/300 XP"
    assert meter_for("later_life", ctx) == "0 of 300 XP spent, 300 left."
    state["character_type"] = "magus"
    ctx = sheet_context(state)
    path = {row["key"]: row["summary"] for row in life_path("spells", ctx)}
    assert "cap" not in path["spells"]
    assert meter_for("spells", ctx) == "0 of 120 spell levels spent, 120 left."


@pytest.mark.django_db
def test_aging_point_can_be_assigned_on_characteristics():
    state = default_state()
    state["age"] = 40
    state["aging_dice"] = [6]
    assert sheet_context(state)["aging_any"] == 1
    post = QueryDict(mutable=True)
    post.setlist("aging_assign", ["str"])
    state = apply_post("characteristics", state, post)
    ctx = sheet_context(state)
    assert ctx["aging_any"] == 0
    strength = next(row for row in ctx["char_rows"] if row["key"] == "str")
    assert strength["aging"] == 1


def test_virtue_detail_uses_the_blank_in_the_name():
    assert note_placeholder("Academic Concentration (Subject)") == "Subject"
    assert note_placeholder("Alluring to (Beings)") == "Beings"
    assert note_placeholder("Cautious with (Ability)") == "Ability"
    assert note_placeholder("Book Learner") == "Notes"
    assert note_placeholder("Cyclic Magic (positive)") == "Notes"
    assert note_placeholder("Necessary (Realm) Aura for (Ability)") == "Realm, Ability"
    assert note_placeholder("Deficient Form") == "Form"
    assert target_prompt("deficient-form")["label"] == "Form"
    assert (
        virtue_sheet_name("Academic Concentration (Subject)", "Logic")
        == "Academic Concentration (Logic)"
    )
    assert virtue_sheet_name("Book Learner", "") == "Book Learner"
    assert (
        virtue_sheet_name("Book Learner", "covenant library") == "Book Learner (covenant library)"
    )
    assert virtue_sheet_name("Affinity with Art", "Creo") == "Affinity with Art (Creo)"
    assert virtue_sheet_name("Great (Characteristic)", "Intelligence") == "Great (Intelligence)"


def test_optional_virtue_note_is_stored_and_a_listed_target_stays():
    state = default_state()
    state["character_type"] = "companion"
    state["virtues_flaws"] = [
        {
            "name": "Academic Concentration (Subject)",
            "slug": "academic-concentration-subject",
            "magnitude": "Minor",
            "category": "General",
            "target": "",
        },
        {
            "name": "Affinity with Art",
            "slug": "affinity-with-art",
            "magnitude": "Minor",
            "category": "Hermetic",
            "target": "Creo",
        },
    ]
    post = QueryDict(mutable=True)
    post.update({"vf_note_0": "Logic", "vf_note_1": "should not replace Creo"})
    state = apply_post("virtues", state, post)
    assert state["virtues_flaws"][0]["target"] == "Logic"
    assert state["virtues_flaws"][1]["target"] == "Creo"
    post = QueryDict(mutable=True)
    post.update({"add_slug": "wanderer", "add_target_wanderer": "the roads"})
    state = apply_post("virtues", state, post)
    wanderer = state["virtues_flaws"][-1]
    assert wanderer["name"] == "Wanderer"
    assert wanderer["target"] == "the roads"


def test_catalog_row_offers_the_blank_or_a_note():
    html = render_to_string(
        "chargen/vf_catalog.html",
        {
            "vf_filtered": True,
            "vf_match_count": 2,
            "vf_kind": "virtue",
            "vf_page_start": 1,
            "vf_page_end": 2,
            "vf_pages": 1,
            "vf_page": 1,
            "vf_prev_page": 0,
            "vf_next_page": 0,
            "catalog": [
                SimpleNamespace(
                    name="Academic Concentration (Subject)",
                    magnitude="Minor",
                    slug="academic-concentration-subject",
                    section_path="",
                    target_prompt=None,
                    note_label="Subject",
                ),
                SimpleNamespace(
                    name="Affinity with Ability",
                    magnitude="Minor",
                    slug="affinity-with-ability",
                    section_path="",
                    target_prompt={"label": "Ability", "options": ["Athletics"]},
                    note_label="",
                ),
            ],
        },
    )
    assert 'placeholder="Subject"' in html
    assert 'name="add_target_academic-concentration-subject"' in html
    assert 'placeholder="Notes"' not in html
    assert html.count("cg-note") == 1
    assert 'name="add_target_affinity-with-ability"' in html
    assert "Ability" in html


@pytest.mark.django_db
def test_suggested_status_has_an_optional_note(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    page = client.get(reverse("chargen:new") + "?as=companion&step=virtues")
    assert page.status_code == 200
    assert b'placeholder="Notes"' in page.content
    assert b'name="add_target_wanderer"' in page.content


@pytest.mark.django_db
def test_empty_magus_virtues_names_the_first_rows_once(
    client, fixture_markdown_dir: Path
):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(f"{reverse('chargen:new')}?as=magus")
    page = client.get(f"{reverse('chargen:new')}?step=virtues")
    html = page.content.decode()
    assert page.status_code == 200
    assert "None chosen yet" not in html
    assert "<h2>Chosen</h2>" not in html
    assert "Every character needs one" not in html
    assert "Wanderer or Covenfolk" not in html
    assert "No Virtue or Flaw points spent yet." in html
    assert "0 Virtue points spent against 0 Flaw points, 0 left." not in html
    assert 'name="add_slug" value="the-gift"' in html
    assert 'name="add_slug" value="hermetic-magus"' in html
    assert "All magi must have The Gift." not in html
    assert "All magi must take the free Social Status Hermetic Magus." not in html
    assert "Every character must take a Social Status." not in html
    assert "Hermetic Flaw" in html
    gift_heading = html.find("<h2>The Gift</h2>")
    status_heading = html.find("<h2>Social Status</h2>")
    gift_add = html.find('name="add_slug" value="the-gift"')
    magus_add = html.find('name="add_slug" value="hermetic-magus"')
    chosen = html.find("<h2>Chosen</h2>")
    house = html.find('id="house-benefit"')
    assert 0 <= gift_heading < gift_add < status_heading < magus_add
    assert chosen == -1
    assert magus_add < house

    state = default_state()
    state["character_type"] = "magus"
    state["house"] = "Flambeau"
    ctx = sheet_context(state)
    messages = [item["message"] for item in step_checklist("virtues", state, ctx)]
    assert any("Hermetic Flaw" in message for message in messages)
    assert not any("The Gift" in message for message in messages)
    assert not any("Hermetic Magus" in message for message in messages)
    assert not any("Social Status" in message for message in messages)

    taken = default_state()
    taken["character_type"] = "magus"
    taken["house"] = "Flambeau"
    taken["virtues_flaws"] = [
        {
            "name": "Hermetic Magus",
            "kind": "virtue",
            "magnitude": "Free",
            "category": "Social Status",
            "slug": "hermetic-magus",
        }
    ]
    left = sheet_context(taken)["suggested_free"]
    assert [item.slug for item in left] == ["the-gift"]


@pytest.mark.django_db
def test_on_the_sheet_uses_the_sheet_phrases():
    state = default_state()
    state["character_type"] = "magus"
    state["name"] = "Ava"
    state["house"] = "Flambeau"
    state["characteristics"]["int"] = 2
    state["childhood"] = [
        {
            "name": "Athletics",
            "xp": ability_xp_for_score(3),
            "specialty": "running",
        }
    ]
    ctx = {
        **sheet_context(state),
        "step_label": "Later life",
        "show_gaps": False,
        "step_checklist": [],
        "life_path": [],
        "chosen_virtues": [],
    }
    abilities = render_to_string("chargen/overview.html", {**ctx, "step": "later_life"})
    assert "Athletics 3 (running)" in abilities
    assert "<li>" not in abilities.split("<h3>Abilities</h3>", 1)[1]
    chars = render_to_string("chargen/overview.html", {**ctx, "step": "characteristics"})
    assert "Int +2 Per 0 Pre 0 Com 0" in chars
    assert "Intelligence" not in chars.split("<h3>Characteristics</h3>", 1)[1]
    assert "aging −" not in chars


@pytest.mark.django_db
def test_character_sheet_is_a_compact_block():
    state = default_state()
    state["character_type"] = "magus"
    state["name"] = "Daimon"
    state["house"] = "Criamon"
    state["age"] = 27
    state["characteristics"]["int"] = 3
    state["characteristics"]["sta"] = 1
    state["arts"]["creo"] = art_xp_for_score(11)
    state["arts"]["aquam"] = art_xp_for_score(10)
    state["virtues_flaws"] = [
        {
            "name": "The Gift",
            "magnitude": "Free",
            "category": "Special",
            "target": "",
            "slug": "the-gift",
        }
    ]
    state["later_life"] = [
        {"name": "Area Lore", "xp": ability_xp_for_score(2), "specialty": "London"}
    ]
    state["spells"] = [
        {"name": "Pilum of Fire", "technique": "Creo", "form": "Ignem", "level": 20}
    ]
    state["personality"] = [{"trait": "Brave", "score": 3}]
    sheet = sheet_context(state)["sheet"]
    assert sheet["identity"] == "Magus, House Criamon, Age 27, Size 0, Conf 1 (3)"
    assert sheet["char_mental"] == "Int +3 Per 0 Pre 0 Com 0"
    assert sheet["char_physical"] == "Str 0 Sta +1 Dex 0 Qik 0"
    assert sheet["virtue_line"] == (
        "The Gift (Free Special), The Enigma (Minor Hermetic, House)"
    )
    assert "Area Lore 2 (London)" in sheet["ability_line"]
    assert "Area Lore (London) 2" not in sheet["ability_line"]
    assert sheet["art_lines"][0].startswith("Cr 11 ")
    assert "(0)" not in sheet["art_lines"][0]
    assert "Aq 10" in sheet["art_lines"][1]
    assert "(0)" not in " ".join(sheet["art_lines"])
    state["arts"]["creo"] = art_xp_for_score(11) + 2
    partial = sheet_context(state)["sheet"]
    assert "Cr 11 (2 xp)" in partial["art_lines"][0]
    state["arts"]["creo"] = art_xp_for_score(11)
    assert sheet["spell_lines"] == ["Pilum of Fire (CrIg 20/+12)"]
    assert sheet["personality_line"] == "Brave 3"
    state["virtues_flaws"].append(
        {
            "name": "Puissant Art",
            "magnitude": "Minor",
            "category": "Hermetic",
            "target": "Creo",
            "slug": "puissant-art",
        }
    )
    sheet = sheet_context(state)["sheet"]
    assert "Cr 11+3" in sheet["art_lines"][0]
    assert "Cr 11+3 (" not in sheet["art_lines"][0]
    assert sheet["spell_lines"] == ["Pilum of Fire (CrIg 20/+15)"]
    plain = default_state()
    plain["character_type"] = "companion"
    companion = sheet_context(plain)["sheet"]
    assert companion["art_lines"] == []
    assert companion["spell_lines"] == []
    assert companion["identity"] == "Companion, Age 25, Size 0, Conf 1 (3)"


@pytest.mark.django_db
def test_sheet_page_keeps_generator_notes_off_the_character(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    page = client.get(reverse("chargen:new") + "?as=magus&step=sheet")
    html = page.content.decode()
    before, article = html.split('<article class="cg-sheet-doc">', 1)
    body = article.split("</article>", 1)[0]
    assert 'class="cg-sheet-meta' in before
    assert "Nothing left to enter" not in html
    assert "The framed block below is the character" not in html
    assert ">Print<" in before
    assert ">Markdown<" in before
    assert ">JSON<" in before
    assert "Fill PDF" in before
    assert "Fill and download" in before
    assert 'id="cg-pdf"' in html
    assert 'enctype="multipart/form-data"' in html
    assert "Play numbers" in before
    assert "Save to Workspace" in before
    assert "Print" not in body
    assert "Fill and download" not in body
    assert "Still open" not in body
    assert "<h2>Equipment</h2>" in body
    assert "Equipment:" not in body
    assert ">Play<" not in body
    assert "Int 0 Per 0 Pre 0 Com 0" in body
    assert "Cr 0" in body
    assert "(0)" not in body


@pytest.mark.django_db
def test_sheet_print_markdown_and_workspace_save(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=companion")
    client.post(
        reverse("chargen:new"),
        {"step": "start", "action": "save", "name": "Ava", "age": "25"},
    )
    client.post(
        reverse("chargen:new"),
        {
            "step": "details",
            "action": "save",
            "equipment": "A bow and a pack",
        },
    )
    page = client.get(reverse("chargen:new") + "?step=sheet")
    body = page.content.decode().split('<article class="cg-sheet-doc">', 1)[1]
    assert "<h2>Equipment</h2>" in body
    assert "A bow and a pack" in body
    printed = client.get(reverse("chargen:print"))
    assert printed.status_code == 200
    assert b'site-header' not in printed.content
    assert b"<h2>Equipment</h2>" in printed.content
    assert b"cg-print-bar" in printed.content
    md = client.get(reverse("chargen:markdown"))
    assert md.status_code == 200
    assert md["Content-Type"].startswith("text/markdown")
    assert "filename=" in md["Content-Disposition"]
    text = md.content.decode()
    assert text.startswith("# Ava")
    assert "## Equipment" in text
    assert "A bow and a pack" in text
    assert "## Play" not in text
    data = client.get(reverse("chargen:json"))
    assert data.status_code == 200
    assert data["Content-Type"].startswith("application/json")
    payload = data.json()
    assert payload["schema"] == "clavis.character/1"
    assert payload["name"] == "Ava"
    assert payload["equipment"] == "A bow and a pack"
    assert payload["play"]["soak"] == 0
    assert "worksheet" in payload
    saved = client.post(reverse("chargen:save"), {"campaign": ""})
    assert saved.status_code == 302
    from apps.chargen.models import Character

    row = Character.objects.get(name="Ava")
    assert row.character_type == "companion"
    assert row.state["equipment"] == "A bow and a pack"
    workspace = client.get(reverse("campaigns:workspace"), {"tab": "characters"})
    assert workspace.status_code == 200
    assert b"Ava" in workspace.content
    opened = client.get(reverse("chargen:open", args=[row.pk]))
    assert opened.status_code == 302
    again = client.get(reverse("chargen:new") + "?step=sheet")
    assert b"Ava" in again.content


@pytest.mark.django_db
def test_opening_another_character_asks_before_replacing_the_working_copy(
    client, fixture_markdown_dir: Path
):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=companion")
    client.post(
        reverse("chargen:new"),
        {"step": "start", "action": "save", "name": "Ava", "age": "25"},
    )
    other = write_overlay({"name": "Bob", "character_type": "grog", "age": 20, "equipment": ""})
    page = client.get(reverse("chargen:open", args=[other.pk]))
    assert page.status_code == 200
    assert b"Replace the working copy?" in page.content
    assert b"Opening Bob replaces that working copy." in page.content
    assert b"Ava has not been saved to Workspace" in page.content
    still = client.get(reverse("chargen:new") + "?step=start")
    assert b"Ava" in still.content
    assert b"Bob" not in still.content.split(b"<article", 1)[0]
    confirmed = client.post(reverse("chargen:open", args=[other.pk]))
    assert confirmed.status_code == 302
    opened = client.get(reverse("chargen:new") + "?step=sheet")
    assert b"Bob" in opened.content


@pytest.mark.django_db
def test_sheet_markdown_matches_the_html_sections():
    state = default_state()
    state["character_type"] = "companion"
    state["name"] = "Ava"
    state["equipment"] = "A pack"
    text = sheet_markdown(sheet_context(state))
    assert "## Personality" in text
    assert "## Equipment\nA pack" in text
    assert "## Play" not in text
    payload = sheet_json(sheet_context(state))
    assert payload["schema"] == "clavis.character/1"
    assert payload["play"]["soak"] == 0
    assert write_overlay(state).name == "Ava"


def test_wound_levels_and_quiet_magic():
    zero = wound_levels(0)
    assert [(row["name"], row["low"], row["high"]) for row in zero] == [
        ("Light", 1, 5),
        ("Medium", 6, 10),
        ("Heavy", 11, 15),
        ("Incapacitated", 16, 20),
        ("Dead", 21, None),
    ]
    assert wound_levels(-1)[0]["high"] == 4
    assert casting_parts(12) == {"formulaic": 12, "fatigue_spont": 6, "no_fatigue": 2}
    quiet = voice_penalties([{"slug": "quiet-magic", "magnitude": "Minor"}])
    assert quiet["soft"] == 0
    assert quiet["none"] == -5
    overlay = play_overlay(
        kind="magus",
        characteristics={
            "int": 2, "per": 0, "str": -1, "sta": 0, "pre": 0, "com": 0, "dex": 0, "qik": 0
        },
        size=0,
        abilities=[{"name": "Brawl", "score": 2, "bonus": 0}],
        arts=[{"name": "Creo", "key": "creo", "score": 5, "bonus": 0}],
        virtues_flaws=[],
    )
    crig = next(cell for cell in overlay["casting"]["grid"] if cell["abbrev"] == "CrIg")
    assert crig["formulaic"] == 5
    assert crig["fatigue_spont"] == 2
    assert crig["no_fatigue"] == 1
    assert overlay["combat"][1]["attack"] == 2
    labels = [row["label"] for row in overlay["casting_rows"]]
    assert labels == [
        "Laboratory",
        "Fast Cast",
        "Concentration",
        "Magic Resistance",
        "Ceremonial",
        "Targeting",
    ]
    resist = next(row for row in overlay["casting_rows"] if row["label"] == "Magic Resistance")
    assert resist["value"] == 0
    assert "MR" not in resist["note"]
    notes = {row["label"]: row["note"] for row in overlay["casting_rows"]}
    assert notes["Laboratory"] == "Int + Magic Theory + Te + Fo + Aura."
    assert notes["Fast Cast"] == "Qik + Finesse."
    assert notes["Concentration"] == "Sta + Concentration."
    assert notes["Magic Resistance"] == "Parma Magica × 5 + Fo."
    assert notes["Ceremonial"] == "Artes Liberales + Philosophiae."
    assert notes["Targeting"] == "Per + Finesse."
    assert overlay["casting_notes"] == [
        "Casting Score = Te+Fo+Sta. Voice soft −5, none −10. Gestures subtle −2, none −5.",
        "Spont: fatigue /2, no fatigue /5",
    ]
    assert [row["abbrev"] for row in overlay["casting"]["table"]["rows"]] == [
        "Cr",
        "In",
        "Mu",
        "Pe",
        "Re",
    ]
    assert [form["abbrev"] for form in overlay["casting"]["table"]["forms"]] == [
        "An",
        "Aq",
        "Au",
        "Co",
        "He",
        "Ig",
        "Im",
        "Me",
        "Te",
        "Vi",
    ]
    assert overlay["casting"]["table"]["rows"][0]["cells"][5]["abbrev"] == "CrIg"
    quiet_overlay = play_overlay(
        kind="magus",
        characteristics={"sta": 0},
        size=0,
        abilities=[],
        arts=[],
        virtues_flaws=[{"slug": "quiet-magic", "magnitude": "Minor"}],
    )
    assert quiet_overlay["casting_notes"][0].startswith(
        "Casting Score = Te+Fo+Sta. Voice soft 0, none −5. Gestures subtle −2, none −5."
    )


@pytest.mark.django_db
def test_play_numbers_stay_off_the_posted_sheet_until_toggled(
    client, fixture_markdown_dir: Path
):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=magus")
    client.post(
        reverse("chargen:new"),
        {"step": "start", "action": "save", "name": "Ava", "age": "25", "house": "Flambeau"},
    )
    page = client.get(reverse("chargen:new") + "?step=sheet")
    article = page.content.decode().split('<article class="cg-sheet-doc">', 1)[1]
    assert "<h2>Play</h2>" not in article
    client.post(
        reverse("chargen:new"),
        {"step": "sheet", "action": "live", "show_play": "1"},
    )
    shown = client.get(reverse("chargen:new") + "?step=sheet")
    assert b"<h2>Play</h2>" in shown.content
    assert b"Soak 0" in shown.content
    assert b"Magic Resistance" in shown.content
    assert b"Int + Magic Theory + Te + Fo + Aura" in shown.content
    assert b"Qik + Finesse" in shown.content
    assert b" MR " not in shown.content
    text = client.get(reverse("chargen:markdown")).content.decode()
    assert "## Play" in text
    assert "Soak 0" in text
    assert "Magic Resistance" in text
    assert "MR " not in text
    assert "Casting Score = Te+Fo+Sta" in text
    assert "| | An | Aq | Au | Co | He | Ig | Im | Me | Te | Vi |" in text
    assert "| Cr |" in text
    assert "Each cell is Te + Fo + Sta" not in text


def test_add_trait_keeps_a_blank_row_and_continue_drops_it():
    state = default_state()
    post = QueryDict(mutable=True)
    post.setlist("trait_name", [""])
    post.setlist("trait_score", [""])
    post["action"] = "add_trait"
    state = apply_post("details", state, post)
    assert len(state["personality"]) == 2
    assert all(row["trait"] == "" for row in state["personality"])
    post = QueryDict(mutable=True)
    post.setlist("trait_name", ["Brave", ""])
    post.setlist("trait_score", ["3", ""])
    post["action"] = "next"
    state = apply_post("details", state, post)
    assert state["personality"] == [{"trait": "Brave", "score": 3}]


def test_aging_point_falls_only_past_the_absolute_value():
    score, points = add_aging_point(2, 0)
    assert (score, points) == (2, 1)
    score, points = add_aging_point(score, points)
    assert (score, points) == (2, 2)
    score, points = add_aging_point(score, points)
    assert (score, points) == (1, 0)
    score, points = add_aging_point(-3, 3)
    assert (score, points) == (-4, 0)


def test_crisis_reaches_the_next_decrepitude_and_spends_the_ritual():
    play = {key: 0 for key in ("int", "per", "pre", "com", "str", "sta", "dex", "qik")}
    resolved = resolve_aging(
        age=40,
        post35=[11, 3],
        early={},
        crisis_dice={"36": 5},
        living=0,
        longevity=2,
        since=0,
        play=play,
        assignments=[],
    )
    first = resolved["years"][36]
    assert first["crisis"] is True
    assert resolved["decrepitude_score"] == 1
    assert resolved["decrepitude_xp"] == 5
    assert first["crisis_label"] == "Survived. The Longevity Ritual is spent."
    assert resolved["ritual_spent_age"] == 36
    assert resolved["years"][37]["total"] == 3 + 4 - 2


def test_pre35_ritual_die_counts_as_nine():
    play = {key: 0 for key in ("int", "per", "pre", "com", "str", "sta", "dex", "qik")}
    resolved = resolve_aging(
        age=40,
        post35=[],
        early={"30": 16},
        crisis_dice={},
        living=0,
        longevity=1,
        since=30,
        play=play,
        assignments=[],
    )
    year = resolved["years"][30]
    assert year["capped"] is True
    assert year["die_used"] == 9
    assert year["total"] == 9 + 3 - 1


def test_aging_living_and_ritual_are_per_winter():
    play = {key: 0 for key in ("int", "per", "pre", "com", "str", "sta", "dex", "qik")}
    resolved = resolve_aging(
        age=37,
        post35=[5, 5],
        early={},
        crisis_dice={},
        living={"36": 1, "37": -2},
        longevity={"36": 2, "37": 0},
        since=0,
        play=play,
        assignments=[],
    )
    assert resolved["years"][36]["total"] == 5 + 4 - 1 - 2
    assert resolved["years"][37]["total"] == 5 + 4 - (-2)
    assert resolved["years"][36]["living"] == 1
    assert resolved["years"][37]["longevity"] == 0


def test_aging_post_keeps_per_year_modifiers():
    state = default_state()
    state["character_type"] = "companion"
    state["age"] = 37
    post = QueryDict(mutable=True)
    post.setlist("aging_die", ["5", "5"])
    post["aging_living_36"] = "1"
    post["aging_living_37"] = "-2"
    post["aging_longevity_36"] = "3"
    post["aging_longevity_37"] = "0"
    state = apply_post("aging", state, post)
    assert state["aging_living"] == {"36": 1, "37": -2}
    assert state["aging_longevity"] == {"36": 3, "37": 0}
    play = {key: 0 for key in ("int", "per", "pre", "com", "str", "sta", "dex", "qik")}
    years = resolve_aging(
        age=37,
        post35=state["aging_dice"],
        early={},
        crisis_dice={},
        living=state["aging_living"],
        longevity=state["aging_longevity"],
        since=0,
        play=play,
        assignments=[],
    )["years"]
    assert years[36]["total"] == 5 + 4 - 1 - 3
    assert years[37]["total"] == 5 + 4 - (-2)


def test_house_choice_is_free_and_switches_with_the_house():
    state = default_state()
    state["character_type"] = "magus"
    post = QueryDict(mutable=True)
    post["character_type"] = "magus"
    post["house"] = "Flambeau"
    post["house_choice"] = "puissant-art|Ignem"
    post["age"] = "25"
    post["name"] = "Ava"
    state = apply_post("start", state, post)
    grant = state["virtues_flaws"][0]
    assert grant["name"] == "Puissant Art"
    assert grant["target"] == "Ignem"
    assert grant["house_grant"] is True
    assert picks_from_state(state)[0].granted is True
    totals = check_virtues_and_flaws("magus", picks_from_state(state))
    assert totals.virtue_points == 0
    post = QueryDict(mutable=True)
    post["character_type"] = "magus"
    post["house"] = "Guernicus"
    post["house_choice"] = "puissant-art|Ignem"
    post["age"] = "25"
    state = apply_post("start", state, post)
    assert [row["name"] for row in state["virtues_flaws"]] == ["Hermetic Prestige"]
    post = QueryDict(mutable=True)
    post["remove_index"] = "0"
    state = apply_post("virtues", state, post)
    assert state["virtues_flaws"] == []
    assert "hermetic-prestige|" in state["house_declined"]


def test_childhood_score_is_the_sheet_score_and_keeps_later_xp():
    state = default_state()
    state["childhood"] = [{"name": "Athletics", "xp": 15, "specialty": "running"}]
    state["later_life"] = [{"name": "Athletics", "xp": 15, "specialty": "running"}]
    applied = apply_vf_effects(picks_from_state(state))
    rows = _phase_editor_rows(state, "childhood", applied)
    row = next(item for item in rows if item["name"] == "Athletics")
    assert row["score"] == 3
    assert row["paid_score"] == 0
    assert row["min_score"] == 2
    assert row["phase_xp"] == 15
    post = QueryDict(mutable=True)
    post.setlist("child_name", ["Athletics"])
    post.setlist("child_score", ["3"])
    post.setlist("child_xp", ["0"])
    post.setlist("child_spec", ["running"])
    state = apply_post("childhood", state, post)
    assert state["childhood"] == [{"name": "Athletics", "xp": 15, "specialty": "running"}]
    assert state["later_life"] == [{"name": "Athletics", "xp": 15, "specialty": "running"}]


def test_package_keeps_a_specialty_and_does_not_touch_later_life():
    state = default_state()
    state["childhood_package"] = "Athletic"
    state["childhood"] = [
        {"name": "Athletics", "xp": 15, "specialty": "running"},
        {"name": "Brawl", "xp": 15, "specialty": ""},
        {"name": "Swim", "xp": 15, "specialty": ""},
    ]
    state["later_life"] = [{"name": "Athletics", "xp": 15, "specialty": ""}]
    post = QueryDict(mutable=True)
    post["childhood_package"] = "Exploring"
    state = apply_post("childhood", state, post)
    athletics = next(row for row in state["childhood"] if row["name"] == "Athletics")
    assert athletics["specialty"] == "running"
    assert athletics["xp"] == ability_xp_for_score(1)
    assert state["later_life"] == [{"name": "Athletics", "xp": 15, "specialty": ""}]


@pytest.mark.django_db
def test_house_benefit_follows_the_second_choice(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=magus")
    fields = {
        "step": "start",
        "action": "live",
        "character_type": "magus",
        "name": "Ava",
        "age": "40",
        "house": "Flambeau",
        "native_language": "English",
    }
    first = client.post(reverse("chargen:new"), fields, HTTP_HX_REQUEST="true")
    assert b"Puissant Perdo or Puissant Ignem" in first.content
    fields["house"] = "Guernicus"
    second = client.post(reverse("chargen:new"), fields, HTTP_HX_REQUEST="true")
    assert b"Hermetic Prestige" in second.content
    assert b"Puissant Perdo" not in second.content


@pytest.mark.django_db
def test_ex_miscellanea_flaw_is_required_and_free(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    state = default_state()
    state["character_type"] = "magus"
    state["house"] = "Ex Miscellanea"
    state["name"] = "Ava"
    state["virtues_flaws"] = [
        {
            "name": "Necessary Condition",
            "kind": "flaw",
            "magnitude": "Major",
            "category": "Hermetic",
            "slug": "necessary-condition",
            "target": "words",
        }
    ]
    open_issues = validate_step("virtues", state)
    assert any(item.code == "house_flaw" for item in open_issues)
    post = QueryDict(mutable=True)
    post["house_slot"] = "0"
    state = apply_post("virtues", state, post)
    assert state["virtues_flaws"][0]["house_grant"] is True
    totals = check_virtues_and_flaws("magus", picks_from_state(state))
    assert totals.flaw_points == 0
    assert all(item.code != "house_flaw" for item in validate_step("virtues", state))


@pytest.mark.django_db
def test_native_language_starts_empty_and_still_prints_score_five():
    state = default_state()
    assert state["native_language"] == ""
    state["character_type"] = "companion"
    names = {row["name"]: row["score"] for row in sheet_context(state)["abilities"]}
    assert names["Native Language"] == 5


def test_vf_category_options_are_atomic_buckets():
    labels = vf_category_options(
        [
            "Hermetic",
            "Hermetic and General",
            "Hermetic or General",
            "Hermetic, Story",
            "General",
            "Social Status",
        ]
    )
    assert labels == ["Hermetic", "General", "Social Status", "Story"]
    assert "Hermetic and General" not in labels
    assert "Hermetic or General" not in labels


@pytest.mark.django_db
def test_living_conditions_omit_starred_cumulative_rows():
    assert living_condition_choices(((0, "Average"), (1, "* Cumulative note"))) == (
        (0, "Average"),
    )
    state = default_state()
    state["character_type"] = "magus"
    for _value, label in sheet_context(state)["living_choices"]:
        assert not str(label).lstrip().startswith("*")


@pytest.mark.django_db
def test_identity_uses_apparent_age_wording():
    state = default_state()
    state["character_type"] = "magus"
    state["age"] = 40
    state["aging_dice"] = [6]
    identity = sheet_context(state)["sheet"]["identity"]
    assert "apparent" in identity
    assert "Age 40 (" in identity
    payload = sheet_json(sheet_context(state))
    assert payload["age"] == 40
    assert isinstance(payload["age"], int)


@pytest.mark.django_db
def test_bought_intelligence_keeps_its_plus_sign():
    state = default_state()
    state["character_type"] = "magus"
    state["characteristics"]["int"] = 2
    mental = sheet_context(state)["sheet"]["char_mental"]
    assert mental.startswith("Int +2")
    assert "Int +3" not in mental


def test_required_apprenticeship_rows_appear_without_minima():
    state = default_state()
    state["character_type"] = "magus"
    applied = apply_vf_effects(picks_from_state(state))
    rows = {row["name"]: row for row in _phase_editor_rows(state, "apprenticeship", applied)}
    assert rows["Latin"]["min_score"] == 1
    assert rows["Magic Theory"]["min_score"] == 1
    assert rows["Parma Magica"]["min_score"] == 1
    assert rows["Latin"]["score"] == 1
    assert rows["Latin"]["score"] < 4
    assert "Artes Liberales" not in rows


@pytest.mark.django_db
def test_aging_crisis_creates_any_characteristic_slots():
    state = default_state()
    state["character_type"] = "magus"
    state["age"] = 40
    state["aging_dice"] = [9]
    ctx = sheet_context(state)
    year = ctx["aging"]["years"][36]
    assert year["crisis"] is True
    assert ctx["aging"]["any_total"] > 0
    assert ctx["aging_slots"]
    assert ctx["aging_any"] == ctx["aging"]["any_points"]


@pytest.mark.django_db
def test_door_shows_type_cards_while_a_working_copy_exists(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=magus")
    home = client.get(reverse("chargen:home"))
    assert b"Continue" in home.content
    assert b"Create a Grog" in home.content
    assert b"Create a Companion" in home.content
    assert b"Create a Magus" in home.content
    confirm = client.get(reverse("chargen:home") + "?begin=grog")
    assert b"Replace the working copy?" in confirm.content
    assert b"Create a Grog" in confirm.content


@pytest.mark.django_db
def test_live_house_clears_need_house(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=magus")
    blocked = _continue(client, "start", name="Elena", character_type="magus", age="40")
    assert b"A magus must pick a House" in blocked.content
    live = client.post(
        reverse("chargen:new"),
        {
            "step": "start",
            "action": "live",
            "character_type": "magus",
            "name": "Elena",
            "age": "40",
            "house": "Jerbiton",
        },
        HTTP_HX_REQUEST="true",
    )
    assert live.status_code == 200
    assert b"A magus must pick a House" not in live.content
    assert b"Jerbiton" in live.content


@pytest.mark.django_db
def test_jerbiton_house_block_has_addable_virtue_rows(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=magus")
    client.post(
        reverse("chargen:new"),
        {
            "step": "start",
            "action": "save",
            "character_type": "magus",
            "name": "Elena",
            "age": "40",
            "house": "Jerbiton",
        },
    )
    page = client.get(reverse("chargen:new") + "?step=virtues")
    html = page.content.decode()
    assert "Educated" in html
    assert 'name="add_slug" value="educated"' in html
    state = default_state()
    state["character_type"] = "magus"
    state["house"] = "Jerbiton"
    names = [row["name"] for row in house_suggestion_rows(state)]
    assert "Educated" in names
    assert "Free Expression" in names


@pytest.mark.django_db
def test_vf_filtered_get_loads_catalog_and_consumes_filter_events(
    client, fixture_markdown_dir: Path
):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=companion")
    page = client.get(reverse("chargen:new") + "?step=virtues&vf_magnitude=Minor")
    html = page.content.decode()
    assert 'id="vf-catalog"' in html
    assert "Search by name, or choose a magnitude or category." not in html
    assert "hx-trigger=\"change consume\"" in html
    hermetic = client.get(
        reverse("chargen:new") + "?step=virtues&kind=flaw&vf_category=Hermetic"
    )
    options = hermetic.content.decode()
    assert "Hermetic and General" not in options.split("name=\"vf_category\"", 1)[-1].split(
        "</select>", 1
    )[0]


def _synthetic_acroform(names: list[str]) -> bytes:
    """Minimal AcroForm for tests. Never an Atlas sheet."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=800)
    fields = []
    top = 750
    for index, name in enumerate(names):
        y = top - index * 18
        annot = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(name),
                NameObject("/V"): TextStringObject(""),
                NameObject("/Ff"): NumberObject(0),
                NameObject("/F"): NumberObject(4),
                NameObject("/Rect"): ArrayObject(
                    [
                        FloatObject(40),
                        FloatObject(y),
                        FloatObject(220),
                        FloatObject(y + 16),
                    ]
                ),
                NameObject("/DA"): TextStringObject("/Helv 10 Tf 0 g"),
            }
        )
        ref = writer._add_object(annot)
        fields.append(ref)
    page[NameObject("/Annots")] = ArrayObject(fields)
    acro = DictionaryObject(
        {
            NameObject("/Fields"): ArrayObject(fields),
            NameObject("/NeedAppearances"): BooleanObject(True),
        }
    )
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(acro)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _elena_magus() -> dict:
    state = default_state()
    state["character_type"] = "magus"
    state["name"] = "Elena"
    state["house"] = "Flambeau"
    state["age"] = 27
    state["characteristics"]["int"] = 2
    state["characteristics"]["sta"] = 1
    state["characteristics"]["str"] = -1
    state["childhood"] = [
        {"name": "Athletics", "xp": ability_xp_for_score(3), "specialty": "running"}
    ]
    state["arts"]["creo"] = art_xp_for_score(11)
    state["spells"] = [
        {"name": "Pilum of Fire", "technique": "Creo", "form": "Ignem", "level": 20}
    ]
    state["virtues_flaws"] = [
        {
            "name": "The Gift",
            "kind": "virtue",
            "magnitude": "Free",
            "category": "Special",
            "slug": "the-gift",
        }
    ]
    state["personality"] = [{"trait": "Brave", "score": 3}]
    state["equipment"] = "A staff"
    return state


_ARMD_TEST_FIELDS = [
    "Text140",
    "Text6",
    "Text7",
    "Text8",
    "Text9",
    "Intelligence Score",
    "Creo",
    "ABILITY 1",
    "ABILITY 30",
    "Virtues 1",
    "SPELL",
    "Form",
    "Technique",
    "Level",
    "Bonus",
    "Soak",
    "Str",
    "SCORE 1",
    "Personality Traits 1",
    "1_4",
    "Text1",
]


def test_read_uploaded_pdf_rejects_empty_and_non_pdf():
    with pytest.raises(PdfFillError, match=MSG_NO_FILE):
        read_uploaded_pdf(None)
    empty = SimpleUploadedFile("blank.pdf", b"", content_type="application/pdf")
    with pytest.raises(PdfFillError, match=MSG_EMPTY):
        read_uploaded_pdf(empty)
    junk = SimpleUploadedFile("sheet.pdf", b"not-a-pdf", content_type="application/pdf")
    with pytest.raises(PdfFillError, match=MSG_NOT_PDF):
        read_uploaded_pdf(junk)


def test_identify_template_from_field_names():
    assert identify_template([]) == "no_fields"
    assert identify_template(_ARMD_TEST_FIELDS) == "armd_fillable"
    germanitas = [f"Text{i}" for i in range(1, 47)]
    assert identify_template(germanitas) == "germanitas"
    assert identify_template(["Foo", "Bar", "Text1"]) == "unknown"


@pytest.mark.django_db
def test_fill_rejects_pdf_with_no_fields():
    with pytest.raises(PdfFillError, match=MSG_NO_FIELDS):
        fill_character_pdf(_blank_pdf(), sheet_context(_elena_magus()))


@pytest.mark.django_db
def test_fill_rejects_unknown_and_germanitas_without_writing():
    ctx = sheet_context(_elena_magus())
    unknown = _synthetic_acroform(["Foo", "Bar", "Text1"])
    with pytest.raises(PdfFillError, match=MSG_UNKNOWN):
        fill_character_pdf(unknown, ctx)
    assert PdfReader(BytesIO(unknown)).get_form_text_fields()["Text1"] in (None, "")
    germanitas = _synthetic_acroform([f"Text{i}" for i in range(1, 47)])
    with pytest.raises(PdfFillError, match="Germanitas fillable sheet"):
        fill_character_pdf(germanitas, ctx)
    filled = PdfReader(BytesIO(germanitas)).get_form_text_fields()
    assert filled["Text1"] in (None, "")


@pytest.mark.django_db
def test_fill_synthetic_armd_fields_from_the_sheet():
    raw = _synthetic_acroform(_ARMD_TEST_FIELDS)
    ctx = sheet_context(_elena_magus())
    data = fill_character_pdf(raw, ctx)
    got = PdfReader(BytesIO(data)).get_form_text_fields()
    assert got["Text140"] == "Elena"
    assert got["Text6"] == "Flambeau"
    assert got["Text7"] == "27"
    assert got["Intelligence Score"] == "+2"
    assert got["ABILITY 1"] == "Athletics"
    assert got["Virtues 1"].startswith("The Gift")
    assert got["Creo"] == str(art_xp_for_score(11))
    assert got["SPELL"] == "Pilum of Fire"
    assert got["Form"] == "Ig"
    assert got["Technique"] == "Cr"
    assert got["Level"] == "20"
    assert got["Personality Traits 1"] == "Brave"
    assert got["SCORE 1"] == "3"
    assert got["1_4"] == "A staff"
    assert got["Text1"] in (None, "")
    assert got["Str"] in (None, "")
    assert got["Soak"] in (None, "")


@pytest.mark.django_db
def test_pdf_fill_view_errors_and_download(client, fixture_markdown_dir: Path):
    import_sources(sync=False, local_path=fixture_markdown_dir)
    client.get(reverse("chargen:new") + "?as=magus")
    client.post(
        reverse("chargen:new"),
        {
            "step": "start",
            "action": "save",
            "name": "Elena",
            "age": "27",
            "house": "Flambeau",
        },
    )
    missing = client.post(reverse("chargen:fill_pdf"))
    assert missing.status_code == 302
    page = client.get(reverse("chargen:new") + "?step=sheet")
    assert MSG_NO_FILE.encode() in page.content
    assert b"Elena" in page.content
    assert client.get(reverse("chargen:fill_pdf")).status_code == 405
    upload = SimpleUploadedFile(
        "sheet.pdf",
        _synthetic_acroform(_ARMD_TEST_FIELDS),
        content_type="application/pdf",
    )
    filled = client.post(reverse("chargen:fill_pdf"), {"sheet_pdf": upload})
    assert filled.status_code == 200
    assert filled["Content-Type"].startswith("application/pdf")
    assert "elena-filled.pdf" in filled["Content-Disposition"]
    values = PdfReader(BytesIO(filled.content)).get_form_text_fields()
    assert values["Text140"] == "Elena"
    still = client.get(reverse("chargen:new") + "?step=sheet")
    assert b"Elena" in still.content
