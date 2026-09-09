"""
Router regression suite.

The first test is the guarantee that multi-source support did not change how
existing questions are answered: for every prompt the product already ships
(the curated suggestion chips in frontend/src/utils/suggestionHelper.js, plus
the README examples), the new router must pick the same source the old
two-way keyword check picked.

The old logic is reproduced verbatim below rather than imported, so this test
keeps working after the original function is deleted.

Run from backend/:  python -m pytest tests/test_source_router.py -v
"""

import asyncio

import pytest

from app.datasources import registry
from app.router import SourceRouter

# --- the pre-existing routing logic, copied verbatim ------------------------

OLD_MYSQL_PRIORITY_KEYWORDS = (
    "leakage", "fatigue", "compliance", "campaign", "claim", "claims",
    "rejection", "rejections", "pharmacy", "engagement", "mysql",
    "prescriber", "npi", "medicine", "medicines", "clinical", "tablet",
    "dosage", "extract", "extraction", "sync", "sync_log", "salesforce_sync_log",
    "transcript", "transcripts", "work detail", "work_detail", "workdetails",
    "audit", "history_id", "tablet_extract_history", "medicine_extraction_log"
)
OLD_SALESFORCE_KEYWORDS = (
    "salesforce", "doctor", "doctors", "sales rep", "sales reps",
    "sales representative", "sales representatives", "sales manager",
    "sales managers", "rep manager", "rep managers", "hcp status",
    "state license", "crm", "soql", "sosl"
)


def old_route(message: str) -> str:
    """Returns 'salesforce' or 'mysql_primary', matching the original behaviour."""
    text = (message or "").lower()
    if any(kw in text for kw in OLD_MYSQL_PRIORITY_KEYWORDS):
        return "mysql_primary"
    if any(kw in text for kw in OLD_SALESFORCE_KEYWORDS):
        return "salesforce"
    return "mysql_primary"  # the old default


# --- prompts the product already ships -------------------------------------

EXISTING_PROMPTS = [
    # suggestionHelper.js — leakage
    "Calculate leakage summary grouped by state",
    "Show the top 10 physician leakage records",
    "List all claims rejected due to prior authorization requirements",
    "Show government plans bypassed summary from compliance table",
    "Find prescribers where leakage rate is greater than 50%",
    # fatigue
    "List all physicians flagged with a digital fatigue score above 45",
    "Show email open rate per campaign",
    "List high-fatigue HCPs who are currently in active marketing campaigns",
    "Show average fatigue score distribution across medical specialties",
    "Show recent engagement logs for physicians with fatigue score above 40",
    # work detail
    "Show work details for rep 2006",
    "List HCPs managed by reps with status Needs Follow-up",
    "Show recent work detail history updates with rep names",
    "List sales reps with their assigned HCP interaction counts",
    "Show the 10 most recently updated HCP work details",
    # clinical
    "Show the most frequently extracted tablets with their dosages",
    "List clinical transcripts with extraction status Completed",
    "Show tablet extraction history grouped by Prescriber NPI",
    "List all extracted medicines with frequency Twice Daily",
    "Show tablet extractions with guidance messages and timestamps",
    # salesforce sync
    "Show Salesforce sync status and audit logs",
    "List HCP records successfully mapped with Salesforce ID",
    "Show any medicine extractions or HCP records with sync status Failed",
    # Salesforce CRM vocabulary
    "List all doctors with their sales rep details",
    "Show all doctors in CA",
    "List sales reps",
    "Show sales representatives along with their email and phone",
    "List all In-Progress doctors with their speciality and state",
    "Find doctors and their assigned sales representative details",
    "Show doctors with their state license",
    "What is the hcp status for each doctor",
]


@pytest.fixture(scope="module")
def router():
    # No classifier: the deterministic stages must decide these on their own.
    return SourceRouter(registry, classifier=None)


def route_sync(router, message, requested=None, previous=None):
    return asyncio.run(router.route(message, requested_source=requested, previous_source_id=previous))


@pytest.mark.parametrize("prompt", EXISTING_PROMPTS)
def test_existing_prompts_route_unchanged(router, prompt):
    """No existing prompt may change source, and none may start asking for clarification."""
    decision = route_sync(router, prompt)
    expected = old_route(prompt)
    assert not decision.needs_clarification, (
        f"{prompt!r} now asks for clarification but used to route to {expected}"
    )
    assert decision.source_id == expected, (
        f"{prompt!r}: expected {expected}, got {decision.source_id} "
        f"(stage={decision.stage}, scores={decision.scores})"
    )


# --- GPO routing -----------------------------------------------------------

GPO_PROMPTS = [
    "Which batches failed HIN validation?",
    "Show the audit trail for batch 1024",
    "List roles and their permissions",
    "Show members with their organization identifiers",
    "Show USPS address corrections for the last batch",
    "What is the class of trade discrepancy for batch 900?",
    "Show final output records for batch 1024",
    "List structured contracts by document",
    "How many batches are pending DEA validation?",
    "Show the HRSA validation results",
    "List eligible customers for each member",
    "Show the GPO membership hierarchy",
    "Which users logged in most recently?",
    "Show batches awaiting output generation",
    "List the input format templates",
]


@pytest.mark.parametrize("prompt", GPO_PROMPTS)
def test_gpo_prompts_route_to_gpo(router, prompt):
    decision = route_sync(router, prompt)
    assert decision.source_id == "mysql_gpo", (
        f"{prompt!r}: got {decision.source_id} (stage={decision.stage}, scores={decision.scores})"
    )


# --- explicit override ----------------------------------------------------

def test_ui_selection_wins_over_keywords(router):
    """A deliberate UI choice overrides vocabulary that points elsewhere."""
    decision = route_sync(router, "Show the top 10 physician leakage records", requested="mysql_gpo")
    assert decision.source_id == "mysql_gpo"
    assert decision.stage == "explicit"


def test_unknown_requested_source_falls_back_to_routing(router):
    decision = route_sync(router, "Show the top 10 physician leakage records", requested="nope")
    assert decision.source_id == "mysql_primary"


@pytest.mark.parametrize("prompt,expected", [
    ("in gpo, how many records are there", "mysql_gpo"),
    ("from salesforce, list everything", "salesforce"),
    ("using database 2, show me the tables", "mysql_gpo"),
    ("show me the tables in db1", "mysql_primary"),
])
def test_in_prompt_directives(router, prompt, expected):
    decision = route_sync(router, prompt)
    assert decision.source_id == expected, f"{prompt!r} -> {decision.source_id}"
    assert decision.stage in ("alias", "explicit")


# --- sticky follow-up -----------------------------------------------------

@pytest.mark.parametrize("followup", [
    "show me the top 5 of those",
    "and the failed ones",
    "now group them by state",
    "just the first 10",
])
def test_short_followup_stays_on_previous_source(router, followup):
    decision = route_sync(router, followup, previous="mysql_gpo")
    assert decision.source_id == "mysql_gpo", f"{followup!r} -> {decision.source_id}"
    assert decision.stage == "sticky"


def test_followup_naming_another_source_does_not_stick(router):
    """A 'follow-up' that names another domain must be re-routed, not inherited."""
    decision = route_sync(router, "now show leakage instead", previous="mysql_gpo")
    assert decision.source_id == "mysql_primary"
    assert decision.stage != "sticky"


def test_long_question_does_not_stick(router):
    decision = route_sync(
        router,
        "please list every single doctor together with the sales representative "
        "assigned to them and their contact details",
        previous="mysql_gpo",
    )
    assert decision.stage != "sticky"
    assert decision.source_id == "salesforce"


# --- abstention -----------------------------------------------------------

@pytest.mark.parametrize("prompt", [
    # 'compliance' is decisive for DB 1, 'batch' is decisive for GPO — a real
    # collision the router must not resolve by guessing.
    "show me the compliance status for batch 42",
    # 'extract' is decisive for DB 1 (UC4 medicine extraction), 'membership'
    # for GPO — evenly matched, so neither may win by default.
    "extract the membership data",
])
def test_genuinely_ambiguous_prompt_abstains(router, prompt):
    """
    When two sources both produce decisive evidence and neither is clearly
    ahead, the router must ask rather than answer from the wrong database.
    """
    decision = route_sync(router, prompt)
    assert decision.needs_clarification, (
        f"{prompt!r} routed to {decision.source_id} (scores={decision.scores})"
    )
    assert decision.source_id is None
    assert len(decision.candidates) >= 2


def test_weak_only_signal_does_not_interrupt_the_user(router):
    """
    Shared vocabulary ('member', 'customer', 'file') is not decisive, but it is
    enough to rank. It must resolve to a source, never to a clarifying question
    — the old behaviour for unrecognised prompts was simply the default source.
    """
    decision = route_sync(router, "show me the member status and customer file")
    assert not decision.needs_clarification
    assert decision.source_id is not None


def test_bare_source_mention_is_not_a_directive(router):
    """
    'Show Salesforce sync status' asks about DB 1's sync-audit tables. Only an
    addressed alias ('from salesforce', '@salesforce') overrides scoring.
    """
    decision = route_sync(router, "Show Salesforce sync status and audit logs")
    assert decision.source_id == "mysql_primary"
    assert decision.stage not in ("alias", "explicit")


def test_greeting_does_not_ask_for_clarification(router):
    for greeting in ("hello", "hi", "help", "thanks"):
        decision = route_sync(router, greeting)
        assert not decision.needs_clarification
        assert decision.source_id is not None


def test_no_signal_falls_back_to_default(router):
    decision = route_sync(router, "what can you do for me today")
    assert not decision.needs_clarification
    assert decision.source_id == registry.default_source_id
    assert decision.stage == "default"


# --- word-boundary matching ----------------------------------------------

@pytest.mark.parametrize("prompt", [
    "generate a report for me",       # 'rep' must not match inside 'report'
    "prepare the summary",            # 'rep' must not match inside 'prepare'
])
def test_substring_false_positives_are_gone(router, prompt):
    decision = route_sync(router, prompt)
    assert decision.source_id != "salesforce", (
        f"{prompt!r} wrongly matched Salesforce vocabulary (scores={decision.scores})"
    )


# --- manifest integrity --------------------------------------------------

def test_strong_keywords_are_disjoint():
    """Enforced at registry load; asserted here so the intent is visible."""
    seen = {}
    for ctx in registry.all():
        for kw in ctx.routing.strong_keywords:
            k = kw.lower()
            assert k not in seen, f"strong keyword {k!r} claimed by {seen[k]} and {ctx.id}"
            seen[k] = ctx.id


def test_sandbox_globals_are_distinct():
    globals_ = [ctx.sandbox_global for ctx in registry.all()]
    assert len(globals_) == len(set(globals_)), f"duplicate sandbox globals: {globals_}"
