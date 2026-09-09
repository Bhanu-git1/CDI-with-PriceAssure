"""
Prompt equivalence regression.

Collapsing four per-source/per-provider pipelines into one generic pipeline is
only safe if the prompt each existing source receives is unchanged — the model's
output is a function of that text. These tests reproduce the previous prompt
assembly verbatim and assert byte equality against the new builder.

The reproductions are copies, not imports, so the tests keep their meaning
after the original code is removed.

Run from backend/:  python -m pytest tests/test_prompt_equivalence.py -v
"""

import pytest

from app.datasources import registry
from app.llm_service import SALESFORCE_SYSTEM_PROMPT, SYSTEM_PROMPT, llm_service

PROMPTS = [
    "Show the top 10 physician leakage records",
    "Calculate leakage summary grouped by state",
    "List all physicians flagged with a digital fatigue score above 45",
    "Show email open rate per campaign",
    "Show work details for rep 2006",
    "Show the most frequently extracted tablets with their dosages",
    "Show Salesforce sync status and audit logs",
    "hello",
]

HISTORY_CONTEXTS = [
    "",
    "CONVERSATION HISTORY:\nUser: hi\nAssistant: hello\n\n",
]


def old_mysql_prompt(svc, user_message: str, history_context: str) -> str:
    """The DB 1 assembly exactly as it was inlined in the original process_chat."""
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"{svc._get_refinement_instructions()}\n\n"
        f"{svc.semantic_loader.get_semantic_context_prompt_trimmed(user_message)}\n\n"
        f"{history_context}"
        f"CRITICAL REMINDER: You are currently operating in the MySQL database environment. "
        f"You MUST generate Python code using `db.execute_sql()` to retrieve data from MySQL "
        f"tables like `Tablet_Extract_History` or `medicine_extraction_log`. Do NOT mention "
        f"Salesforce or SOQL.\n\n"
        f"User Question: {user_message}"
    )


def old_salesforce_prompt(svc, user_message: str, history_context: str, schema_context: str) -> str:
    """The UC3 assembly exactly as it was in the original _process_salesforce_chat."""
    semantic_layer_prompt = (
        f"SEMANTIC LAYER CONFIGURATION (YAML):\n{svc.sf_semantic_layer_raw}\n\n"
        if svc.sf_semantic_layer_raw else ""
    )
    return (
        f"{SALESFORCE_SYSTEM_PROMPT}\n\n"
        f"{svc._get_salesforce_refinement_instructions()}\n\n"
        f"{semantic_layer_prompt}"
        f"SALESFORCE SCHEMA DETAILS:\n{schema_context}\n\n"
        f"{history_context}"
        "CRITICAL REMINDER FOR THIS ORG:\n"
        "- Query custom objects 'Doctor__c' and 'Rep_Details__c'.\n"
        "- Filter HCPs / Doctors using fields like HCP_First_Name__c, HCP_Last_Name__c, "
        "Speciality__c, Practice_State__c, Status__c.\n"
        "- Use relationship 'Rep_Ids__r' on Doctor__c to get Sales Representative fields.\n"
        "- DO NOT query or include Manager objects or relationship fields ('Rep_Manager__c', "
        "'Rep_Manager__r') as manager data is unpopulated.\n\n"
        f"User Question: {user_message}"
    )


@pytest.mark.parametrize("history_context", HISTORY_CONTEXTS)
@pytest.mark.parametrize("message", PROMPTS)
def test_db1_prompt_differs_only_by_the_live_row_counts_block(message, history_context):
    """
    The DB 1 prompt is unchanged apart from one deliberate addition: a block of
    live row counts, added because the counts stated in the semantic layer had
    drifted by more than two orders of magnitude.

    Asserting that removing that block reproduces the original byte-for-byte is
    what keeps this a real guarantee — it proves nothing else drifted with it.
    """
    ctx = registry.require("mysql_primary")
    new = llm_service._build_source_prompt(ctx, message, history_context)
    old = old_mysql_prompt(llm_service, message, history_context)

    block = llm_service._row_counts_block(ctx)
    assert block, "expected a live row-counts block; is the database reachable?"
    assert block in new, "row-counts block missing from the assembled prompt"

    assert new.replace(block, "", 1) == old, (
        f"DB 1 prompt changed beyond the row-counts block for {message!r}"
    )


def test_row_counts_block_is_authoritative_and_current():
    """
    The block must both correct the stale prose and be marked as overriding it,
    otherwise the model is left with two contradictory numbers.
    """
    ctx = registry.require("mysql_primary")
    block = llm_service._row_counts_block(ctx)
    assert "SUPERSEDE any row counts mentioned elsewhere" in block
    # The stale prose claims 60; anything in that neighbourhood means the live
    # read silently failed and fell back to something wrong.
    assert "Leakage_Activity=60," not in block
    assert "Leakage_Activity=" in block


@pytest.mark.parametrize("history_context", HISTORY_CONTEXTS)
@pytest.mark.parametrize("message", PROMPTS)
def test_salesforce_prompt_unchanged(monkeypatch, message, history_context):
    ctx = registry.require("salesforce")
    # Pin the schema block: it is a live API read, and the point of this test is
    # the surrounding assembly, not the org's current field list.
    fixed_schema = "Salesforce Schema Overview:\nObject 'Doctor__c': [HCP_First_Name__c]"
    monkeypatch.setattr(ctx.adapter, "get_schema_overview", lambda: fixed_schema)

    new = llm_service._build_source_prompt(ctx, message, history_context)
    old = old_salesforce_prompt(llm_service, message, history_context, fixed_schema)
    assert new == old, f"Salesforce prompt changed for {message!r}"


# --- the new source -------------------------------------------------------

@pytest.mark.parametrize("message", [
    "Which batches failed HIN validation?",
    "Show the audit trail for batch 1024",
    "List roles and their permissions",
])
def test_gpo_prompt_is_scoped_to_its_own_source(message):
    """
    The GPO prompt must name its own sandbox global and must not leak the other
    sources' vocabulary, or the model will emit code that cannot run.
    """
    ctx = registry.require("mysql_gpo")
    prompt = llm_service._build_source_prompt(ctx, message, "")
    flat = " ".join(prompt.split())

    assert "gpo.execute_sql" in prompt
    assert "the global is named 'gpo', NOT 'db'" in prompt
    assert "BATCH_NUM" in prompt

    # Must never instruct the model to call another source's global.
    assert "db.execute_sql()" not in prompt
    assert "sf.execute_soql" not in prompt

    # DB 1 table names may appear ONLY inside the negative instruction that
    # tells the model they do not exist on this source.
    assert flat.count("Leakage_Activity") == 1
    assert (
        "do NOT mention Salesforce, SOQL, or any commercial/pharma tables such as "
        "Leakage_Activity or fatigue_score — they do not exist here." in flat
    )


def test_gpo_prompt_stays_within_token_budget():
    """
    70 tables must never all reach the prompt. The semantic block is budgeted,
    so total prompt size has to stay bounded.
    """
    ctx = registry.require("mysql_gpo")
    for message in ("Which batches failed HIN validation?", "Show every table you have"):
        prompt = llm_service._build_source_prompt(ctx, message, "")
        assert len(prompt) < 24000, f"GPO prompt too large ({len(prompt)} chars) for {message!r}"
