"""
Generates app/semantic/gpo_schema_model.yaml.

Columns, types and row counts come from the live schema dump produced by
scripts/introspect_gpo.py — never hand-typed, because the assistant is
instructed to never invent column names.

The business knowledge (domains, join paths, mapping rules, measures) is
curated in the constants below, so re-running this script after a schema change
regenerates the whole file without losing the annotations.

Usage (from backend/):
    python -m scripts.introspect_gpo            # refresh the dump first
    python -m scripts.build_gpo_semantic_model
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(HERE, "gpo_schema_dump.json")
OUT = os.path.abspath(os.path.join(HERE, "..", "app", "semantic", "gpo_schema_model.yaml"))

# Infrastructure tables that are not business data.
SKIP_TABLES = {"dce_chat_sessions", "dce_chat_messages"}

# Columns emitted per table in the YAML. The loader trims further at render
# time, and describe_table() always exposes the complete list on demand.
MAX_COLS = 40

# =====================================================================
# Curated business knowledge
# =====================================================================

# Each domain doubles as (a) the routing vocabulary and (b) the relevance index
# the loader uses to trim prompts — without it, 70 tables would blow the
# character budget on every question.
DOMAINS = [
    {
        "name": "rbac_security",
        "purpose": "Roles, CRUD permissions, user-role assignment and login/token sessions",
        "tables": ["GPO_ROLE_MASTER", "GPO_ROLE_PERMISSION", "GPO_ROLE_MAPPING", "GPO_USER_LOGIN"],
        "keywords": ["role", "roles", "permission", "permissions", "rbac", "login", "logins",
                     "token", "user access", "who can", "admin", "analyst", "session"],
    },
    {
        "name": "membership_contract",
        "purpose": "Member, organization identifier, eligible customer, structured document and contract data",
        "tables": ["MN_MEMBER", "MN_ORGANIZATION_ID", "MN_ORGANIZATION_ID_ASTELLAS",
                   "MN_CF_ELIGIBLE_CUSTOMER", "MN_STRUCTURED_DOC", "MN_STRUCTURED_CONTRACT"],
        "keywords": ["member", "members", "membership", "organization", "org id", "identifier",
                     "eligible customer", "eligibility", "contract", "contracts",
                     "structured doc", "structured contract", "astellas"],
    },
    {
        "name": "customer_upload",
        "purpose": "Batch file upload, raw staging and standardized customer input",
        "tables": ["GPO_CUST_HDR", "GPO_STAGED_INPUT", "GPO_CUST_INPUT", "GPO_INPUT_FORMAT"],
        "keywords": ["upload", "uploaded", "batch", "batches", "batch_num", "batch number",
                     "file", "files", "roster", "staged", "staging", "input format",
                     "customer input", "batch header", "record count"],
    },
    {
        "name": "hin_validation",
        "purpose": "HIN master lookup and HIN validation results",
        "tables": ["GPO_HIN", "GPO_HIN_VALIDATE"],
        "keywords": ["hin", "hibcc", "health industry number"],
    },
    {
        "name": "dea_validation",
        "purpose": "DEA master lookup and DEA validation results",
        "tables": ["GPO_DEA", "GPO_DEA_VALIDATE"],
        "keywords": ["dea", "drug enforcement"],
    },
    {
        "name": "hrsa_validation",
        "purpose": "HRSA master lookup and HRSA validation results (340B)",
        "tables": ["GPO_HRSA", "GPO_HRSA_VALIDATE"],
        "keywords": ["hrsa", "340b"],
    },
    {
        "name": "address_validation",
        "purpose": "USPS address standardisation and correction",
        "tables": ["GPO_USPS", "GPO_USPS_VALIDATE"],
        "keywords": ["usps", "address", "addresses", "street", "city", "postal", "zip",
                     "plus 4", "plus_4"],
    },
    {
        "name": "cot_validation",
        "purpose": "Class-of-Trade validation, derived by reconciling HIN, DEA and RODB COT values",
        "tables": ["GPO_COT_VALIDATE"],
        "keywords": ["cot", "class of trade", "hibcc_cot", "dea_cot", "rodb_cot", "trade class"],
    },
    {
        "name": "member_validation",
        "purpose": "Membership matching and identifier/address completeness checks",
        "tables": ["GPO_MEMBER_VALIDATE"],
        "keywords": ["member validation", "member match", "matching criteria", "mismatch",
                     "member validate"],
    },
    {
        "name": "output_processing",
        "purpose": "Merge of all validation results into staged output, then the final formatted output",
        "tables": ["GPO_CUST_STG_OUTPUT", "GPO_CUST_OUTPUT", "GPO_OUTPUT_FORMAT"],
        "keywords": ["output", "outputs", "final output", "staged output", "stg output",
                     "deliverable", "output format", "generated file", "corrected"],
    },
    {
        "name": "job_tracking",
        "purpose": "Per-stage processing status and progress for each batch",
        "tables": ["GPO_VALIDATION_JOBS", "GPO_CUST_HDR"],
        "keywords": ["job", "jobs", "status", "progress", "stage", "stages", "pending",
                     "failed", "completed", "in-progress", "processing time", "validation job"],
    },
    {
        "name": "audit_log",
        "purpose": "Central audit trail — every module writes an action row here",
        "tables": ["GPO_LOGS"],
        "keywords": ["log", "logs", "gpo logs", "user action", "action_desc", "audit trail",
                     "who did", "history of actions", "activity"],
    },
    {
        "name": "configuration",
        "purpose": "Administrative matching thresholds and membership file configuration",
        "tables": ["GPO_ADMIN_VALIDATION_CONFIG", "GPO_MEMBERSHIP_FORMAT",
                   "GPO_MEMBERSHIP_HDR", "GPO_MEMBERSHIP_HEIRARCHY"],
        "keywords": ["config", "configuration", "threshold", "similarity", "matching percentage",
                     "membership format", "membership header", "hierarchy", "heirarchy",
                     "gpo hierarchy", "parent", "grandparent", "child"],
    },
    {
        "name": "reference_data",
        "purpose": "Supporting reference, display-message and mail monitoring data",
        "tables": ["BUID", "BUTYPE", "DISPLAY_MSG", "MAIL_MONITOR", "TTBC"],
        "keywords": ["buid", "butype", "business unit", "display message", "msg", "mail monitor",
                     "ttbc", "reference data"],
    },
    # --- client-specific parallel pipelines -------------------------------
    {
        "name": "program_reg",
        "purpose": "REG program's own copy of the upload/validate/output pipeline",
        "tables": ["REG_CUST_HDR", "REG_CUST_INPUT", "REG_STAGED_INPUT", "REG_CUST_STG_OUTPUT",
                   "REG_CUST_OUTPUT", "REG_HIN_VALIDATE", "REG_DEA_VALIDATE",
                   "REG_USPS_VALIDATE", "REG_VALIDATION_JOBS", "REG_LOGS",
                   "REG_INPUT_FORMAT", "REG_OUTPUT_FORMAT", "REG_REPORT_FORMAT"],
        "keywords": ["reg", "reg program", "reg batch", "reg pipeline"],
    },
    {
        "name": "program_abbott",
        "purpose": "Abbott program: customer LEH pipeline, cyclic and parent validation",
        "tables": ["ABBOTT_CUST_HDR", "ABBOTT_CUSTOMER_LEH_INPUT", "ABBOTT_CUSTOMER_LEH_STG_INPUT",
                   "ABBOTT_CUSTOMER_LEH_STG_OUTPUT", "ABBOTT_CUSTOMER_LEH_OUTPUT",
                   "ABBOTT_CYCLIC_VALIDATE", "ABBOTT_PARENT_VALIDATE", "ABBOTT_LOGS",
                   "ABBOTT_MN_MEMBER", "ABBOTT_MN_CMTY_EDGE"],
        "keywords": ["abbott", "leh", "cyclic", "parent validate", "community edge", "cmty"],
    },
    {
        "name": "program_eisai",
        "purpose": "Eisai program: GPO roster change-tracking (additions, removals, address, identifier and hierarchy changes)",
        "tables": ["EISAI_CUST_HDR", "EISAI_STAGED_INPUT", "EISAI_GPO_ROSTER", "EISAI_ADDITIONS",
                   "EISAI_REMOVALS", "EISAI_ADDRESS_CHANGES", "EISAI_IDENTIFIER_CHANGES",
                   "EISAI_MEMBERSHIP_HEIRARCHY_CHANGES", "EISAI_INPUT_FORMAT"],
        "keywords": ["eisai", "additions", "removals", "address changes", "identifier changes",
                     "roster changes", "gpo roster"],
    },
]

TABLE_DESCRIPTIONS = {
    # --- upload / pipeline spine ---
    "GPO_CUST_HDR": (
        "BATCH HEADER — one row per uploaded batch and the hub of the whole pipeline. "
        "BATCH_NUM is the correlation key used by every other pipeline table. "
        "Holds boolean completion flags (HIN_VALIDATED, DEA_VALIDATED, USPS_VALIDATED, "
        "COT_VALIDATED, HRSA_VALIDATED, MEMBER_VALIDATED, isOutputGenerated; 0=not done, 1=done), "
        "record counts (TOTAL_RECORDS, VALID_RECORDS, ERROR_RECORDS) and CURRENT_ACTION, the stage "
        "the batch is sitting at. Also serves the read-only Execution History view."
    ),
    "GPO_STAGED_INPUT": (
        "Raw uploaded rows exactly as received, keyed by BATCH_NUM. VERY WIDE (200 generic columns) "
        "and large — never SELECT *; always name columns and filter by BATCH_NUM."
    ),
    "GPO_CUST_INPUT": (
        "Standardized customer input for a batch, mapped from GPO_STAGED_INPUT using a "
        "GPO_INPUT_FORMAT template. The input side of every validation stage. Large table "
        "(~438k rows) — always filter by BATCH_NUM."
    ),
    "GPO_INPUT_FORMAT": "Column-mapping templates (FORMAT_NAME) used to map staged columns into GPO_CUST_INPUT.",
    # --- validation ---
    "GPO_HIN": "HIN master lookup table. Authoritative NAME/HIN/COT plus address per HIN.",
    "GPO_HIN_VALIDATE": (
        "HIN validation RESULTS per batch. ORIGINAL_* vs UPDATED_* hold the submitted and corrected "
        "values. STATUS here is a MATCH OUTCOME code (DUP, SAME, NO, ONE) — NOT a job status. "
        "MATCH_TYPE explains how the match was made (exact_match_with_hin, abbreviation_match, "
        "similarity_match, no_match, ...). Large table (~199k rows) — always filter by BATCH_NUM."
    ),
    "GPO_DEA": "DEA master lookup table. Authoritative NAME/DEA/COT plus address per DEA.",
    "GPO_DEA_VALIDATE": (
        "DEA validation results per batch. Same ORIGINAL_*/UPDATED_* shape as GPO_HIN_VALIDATE; "
        "DEA_COT carries the class of trade derived from the DEA match."
    ),
    "GPO_HRSA": "HRSA (340B) master lookup table.",
    "GPO_HRSA_VALIDATE": "HRSA validation results per batch, same ORIGINAL_*/UPDATED_* shape as the HIN/DEA validators.",
    "GPO_USPS": "USPS address master lookup table.",
    "GPO_USPS_VALIDATE": (
        "USPS address validation/correction results per batch. ORIGINAL_* vs UPDATED_* address "
        "fields plus PLUS_4_CODE. ACTION values: NEW, ORG, USR."
    ),
    "GPO_COT_VALIDATE": (
        "Class-of-Trade validation results, keyed by BATCH_NUM + CUSTOMER_NAME. DERIVED, not a "
        "master lookup: reconciles ORIGINAL_COT against HIBCC_COT (from HIN), DEA_COT (from DEA) "
        "and RODB_COT to produce CORRECTED_COT."
    ),
    "GPO_MEMBER_VALIDATE": (
        "Membership matching and identifier/address completeness results, keyed by BATCH_NUM + NAME. "
        "STATUS values are match outcomes (Same, One, New, No). MATCHING_CRITERIA explains the match "
        "('Exact Match', 'HIN Match', 'DEA Match', 'New Identifier(s)', 'No Match(Missing info on the Roster)')."
    ),
    # --- output ---
    "GPO_CUST_STG_OUTPUT": (
        "STAGED (pre-final) output — the merge of all validation results for a batch. Carries both "
        "SOURCE_* (as submitted) and CORRECTED_* (validated) values side by side, plus all four COT "
        "opinions (HIBCC_COT, SOURCE_COT, DEA_COT, RODB_COT, MN_COT). NOT the final deliverable."
    ),
    "GPO_CUST_OUTPUT": (
        "FINAL output for a batch, formatted via a GPO_OUTPUT_FORMAT template. CORRECTED_* values "
        "only. This is the customer-facing deliverable."
    ),
    "GPO_OUTPUT_FORMAT": "Output formatting templates (FORMAT_NAME, PARAMETERS) applied when generating GPO_CUST_OUTPUT.",
    # --- tracking / audit ---
    "GPO_VALIDATION_JOBS": (
        "PER-STAGE JOB STATUS for a batch — one row per BATCH_NUM. STATUS is the overall job state; "
        "MEMBER_STATUS, HIN_STATUS, DEA_STATUS, USPS_STATUS, COT_STATUS, HRSA_STATUS, STG_STATUS and "
        "OUTPUT_STATUS are the individual stage states. THIS is where 'failed' or 'pending' stages "
        "live — not in the *_VALIDATE tables."
    ),
    "GPO_LOGS": (
        "Central audit trail. Every module inserts a row keyed by BATCH_NUM with USER_ACTION "
        "(e.g. 'HIN Validation', 'Upload Member File', 'Output File') and action_desc."
    ),
    # --- config / reference ---
    "GPO_ADMIN_VALIDATION_CONFIG": "Administrative matching configuration: COMPARISON_FIELDS, SIMILIARITY_TYPE, MATCHING_PERCENTAGE, THRESHOLD.",
    "GPO_MEMBERSHIP_HDR": "Membership file upload header (FILE_NAME, NO_OF_RECORDS, FORMAT_NAME).",
    "GPO_MEMBERSHIP_FORMAT": "Column-mapping templates for membership file uploads.",
    "GPO_MEMBERSHIP_HEIRARCHY": (
        "GPO membership hierarchy: GPO_ID/GPO_NAME with GRAND_PARENT, PARENT and CHILD id/name pairs. "
        "Note the spelling 'HEIRARCHY' in the table name."
    ),
    # --- membership / contract ---
    "MN_MEMBER": "MEMBERSHIP HUB — one row per member (MEMBER_ID, MEMBER_NAME, MEMBER_GRP_NAME).",
    "MN_ORGANIZATION_ID": "Organization identifiers belonging to a member (TYPE, IDENTIFIER, PRIMARY_FLAG). Many per MEMBER_ID.",
    "MN_ORGANIZATION_ID_ASTELLAS": "Astellas-specific copy of MN_ORGANIZATION_ID with the same shape. Use only when the question names Astellas.",
    "MN_CF_ELIGIBLE_CUSTOMER": "Eligible-customer records per member, with eligibility window and IS_LATEST_ELIGIBILITY flag.",
    "MN_STRUCTURED_DOC": "CONTRACT DOCUMENT HUB — one row per structured document (STRUCT_DOC_ID, STRUCT_DOC_NAME, validity window).",
    "MN_STRUCTURED_CONTRACT": "Structured contracts belonging to a document. Many per STRUCT_DOC_ID. Carries CTRT_DOC_STATUS, contract type/sub-type and approval/implementation dates.",
    "BUID": "Business-unit identifier reference data.",
    "BUTYPE": "Business-unit type reference data.",
    "DISPLAY_MSG": "UI display message catalogue (MSG_NUM, MSG_TEXT, MSG_CONTEXT).",
    "MAIL_MONITOR": "Tracks batches picked up from the mail channel (BATCH_NUM, FILE_NAME).",
    "TTBC": "Text/message component reference table joining MSG_NUM to component codes.",
}

# Fallback descriptions for the client-specific pipelines, applied by prefix.
PREFIX_DESCRIPTIONS = {
    "REG_": "REG program pipeline table — mirrors the equivalent GPO_* table for the REG program only.",
    "ABBOTT_": "Abbott program pipeline table — Abbott-specific customer LEH / validation flow.",
    "EISAI_": "Eisai program table — GPO roster change tracking for the Eisai program only.",
}

JOINS = [
    # --- RBAC ---
    ("rbac_role_to_permission", "GPO_ROLE_PERMISSION", "GPO_ROLE_MASTER",
     "GPO_ROLE_PERMISSION.ROLE_ID = GPO_ROLE_MASTER.ROLE_ID",
     "Declared FK. CRUD permissions (CAN_VIEW/CAN_ADD/CAN_EDIT/CAN_DELETE) for a role."),
    ("rbac_role_to_mapping", "GPO_ROLE_MAPPING", "GPO_ROLE_MASTER",
     "GPO_ROLE_MAPPING.ROLE_ID = GPO_ROLE_MASTER.ROLE_ID",
     "Declared FK. Which users are assigned a role."),
    ("rbac_mapping_to_login", "GPO_USER_LOGIN", "GPO_ROLE_MAPPING",
     "GPO_USER_LOGIN.USER_ID = GPO_ROLE_MAPPING.USER_ID",
     "Declared FK. Login/token sessions for a mapped user."),
    # --- membership / contract ---
    ("member_to_org_id", "MN_ORGANIZATION_ID", "MN_MEMBER",
     "MN_ORGANIZATION_ID.MEMBER_ID = MN_MEMBER.MEMBER_ID",
     "Declared FK. One member has many organization identifiers."),
    ("member_to_eligible_customer", "MN_CF_ELIGIBLE_CUSTOMER", "MN_MEMBER",
     "MN_CF_ELIGIBLE_CUSTOMER.MEMBER_ID = MN_MEMBER.MEMBER_ID",
     "Declared FK. One member has many eligible-customer records."),
    ("doc_to_contract", "MN_STRUCTURED_CONTRACT", "MN_STRUCTURED_DOC",
     "MN_STRUCTURED_CONTRACT.STRUCT_DOC_ID = MN_STRUCTURED_DOC.STRUCT_DOC_ID",
     "Declared FK. One structured document has many structured contracts."),
    # --- batch spine ---
    ("hdr_to_input", "GPO_CUST_INPUT", "GPO_CUST_HDR",
     "GPO_CUST_INPUT.BATCH_NUM = GPO_CUST_HDR.BATCH_NUM",
     "Declared FK. Standardized input rows for a batch."),
    ("hdr_to_staged", "GPO_STAGED_INPUT", "GPO_CUST_HDR",
     "GPO_STAGED_INPUT.BATCH_NUM = GPO_CUST_HDR.BATCH_NUM",
     "Raw uploaded rows for a batch."),
    ("hdr_to_jobs", "GPO_VALIDATION_JOBS", "GPO_CUST_HDR",
     "GPO_VALIDATION_JOBS.BATCH_NUM = GPO_CUST_HDR.BATCH_NUM",
     "Per-stage job status for a batch."),
    ("hdr_to_logs", "GPO_LOGS", "GPO_CUST_HDR",
     "GPO_LOGS.BATCH_NUM = GPO_CUST_HDR.BATCH_NUM",
     "Audit rows for a batch."),
    ("hdr_to_stg_output", "GPO_CUST_STG_OUTPUT", "GPO_CUST_HDR",
     "GPO_CUST_STG_OUTPUT.BATCH_NUM = GPO_CUST_HDR.BATCH_NUM",
     "Staged (pre-final) merged output for a batch."),
    ("hdr_to_output", "GPO_CUST_OUTPUT", "GPO_CUST_HDR",
     "GPO_CUST_OUTPUT.BATCH_NUM = GPO_CUST_HDR.BATCH_NUM",
     "Final formatted output for a batch."),
    ("hdr_to_mail_monitor", "MAIL_MONITOR", "GPO_CUST_HDR",
     "MAIL_MONITOR.BATCH_NUM = GPO_CUST_HDR.BATCH_NUM",
     "Batches that arrived via the mail channel."),
    # --- validation results per batch ---
    ("input_to_hin_validate", "GPO_HIN_VALIDATE", "GPO_CUST_INPUT",
     "GPO_HIN_VALIDATE.BATCH_NUM = GPO_CUST_INPUT.BATCH_NUM AND GPO_HIN_VALIDATE.ORIGINAL_HIN = GPO_CUST_INPUT.HIN",
     "HIN validation outcome for an input row."),
    ("input_to_dea_validate", "GPO_DEA_VALIDATE", "GPO_CUST_INPUT",
     "GPO_DEA_VALIDATE.BATCH_NUM = GPO_CUST_INPUT.BATCH_NUM AND GPO_DEA_VALIDATE.ORIGINAL_DEA = GPO_CUST_INPUT.DEA",
     "DEA validation outcome for an input row."),
    ("input_to_hrsa_validate", "GPO_HRSA_VALIDATE", "GPO_CUST_INPUT",
     "GPO_HRSA_VALIDATE.BATCH_NUM = GPO_CUST_INPUT.BATCH_NUM AND GPO_HRSA_VALIDATE.ORIGINAL_HRSA = GPO_CUST_INPUT.HRSA",
     "HRSA validation outcome for an input row."),
    ("input_to_usps_validate", "GPO_USPS_VALIDATE", "GPO_CUST_INPUT",
     "GPO_USPS_VALIDATE.BATCH_NUM = GPO_CUST_INPUT.BATCH_NUM AND GPO_USPS_VALIDATE.ORIGINAL_NAME = GPO_CUST_INPUT.NAME",
     "USPS address validation outcome for an input row."),
    ("input_to_cot_validate", "GPO_COT_VALIDATE", "GPO_CUST_INPUT",
     "GPO_COT_VALIDATE.BATCH_NUM = GPO_CUST_INPUT.BATCH_NUM AND GPO_COT_VALIDATE.CUSTOMER_NAME = GPO_CUST_INPUT.NAME",
     "Class-of-Trade outcome for an input row."),
    ("input_to_member_validate", "GPO_MEMBER_VALIDATE", "GPO_CUST_INPUT",
     "GPO_MEMBER_VALIDATE.BATCH_NUM = GPO_CUST_INPUT.BATCH_NUM AND GPO_MEMBER_VALIDATE.NAME = GPO_CUST_INPUT.NAME",
     "Membership matching outcome for an input row."),
    # --- validation results to master lookups ---
    ("hin_validate_to_master", "GPO_HIN_VALIDATE", "GPO_HIN",
     "GPO_HIN_VALIDATE.UPDATED_HIN = GPO_HIN.HIN",
     "Resolves the matched HIN master record (authoritative name/COT/address)."),
    ("dea_validate_to_master", "GPO_DEA_VALIDATE", "GPO_DEA",
     "GPO_DEA_VALIDATE.UPDATED_DEA = GPO_DEA.DEA",
     "Resolves the matched DEA master record."),
    ("hrsa_validate_to_master", "GPO_HRSA_VALIDATE", "GPO_HRSA",
     "GPO_HRSA_VALIDATE.UPDATED_HRSA = GPO_HRSA.HRSA",
     "Resolves the matched HRSA master record."),
    # --- staged -> final output ---
    ("stg_output_to_output", "GPO_CUST_OUTPUT", "GPO_CUST_STG_OUTPUT",
     "GPO_CUST_OUTPUT.BATCH_NUM = GPO_CUST_STG_OUTPUT.BATCH_NUM AND GPO_CUST_OUTPUT.KEYNUM = GPO_CUST_STG_OUTPUT.KEYNUM",
     "Final output row and the staged row it came from."),
    # --- reference ---
    ("display_msg_to_ttbc", "TTBC", "DISPLAY_MSG",
     "TTBC.MSG_NUM = DISPLAY_MSG.MSG_NUM",
     "Message component code to display text."),
]

MAPPING_RULES = [
    ("Batch correlation key", """
        BATCH_NUM is THE correlation key for this database. Every pipeline question is scoped to a
        batch, and GPO_CUST_HDR is the batch header hub. When the user names a batch, filter
        BATCH_NUM on every table in the query. GPO_CUST_INPUT (~438k rows), GPO_HIN_VALIDATE
        (~199k rows) and GPO_STAGED_INPUT (~483k rows) MUST always be filtered by BATCH_NUM or
        another selective predicate — never scan them whole."""),
    ("Job status vs match status - CRITICAL", """
        Two different 'STATUS' concepts exist and must never be interchanged.
        1) PROCESSING / JOB status lives ONLY on GPO_VALIDATION_JOBS: STATUS ('In-Progress',
           'Completed', 'Failed', 'Cancelled', 'Started', 'Pending', 'Open') and the per-stage
           columns HIN_STATUS, DEA_STATUS, USPS_STATUS, COT_STATUS, HRSA_STATUS, MEMBER_STATUS,
           STG_STATUS, OUTPUT_STATUS. Stage values are stored with INCONSISTENT CASING
           ('pending', 'completed', 'failed', 'In-Progress'), so ALWAYS compare case-insensitively:
           WHERE LOWER(HIN_STATUS) = 'failed'.
        2) MATCH OUTCOME status lives on the *_VALIDATE tables and is NOT a job state:
           GPO_HIN_VALIDATE.STATUS / GPO_DEA_VALIDATE.STATUS / GPO_HRSA_VALIDATE.STATUS use
           'DUP', 'SAME', 'NO', 'ONE'; GPO_MEMBER_VALIDATE.STATUS uses 'Same', 'One', 'New', 'No'.
        So 'which batches failed HIN validation' -> GPO_VALIDATION_JOBS.HIN_STATUS, NOT
        GPO_HIN_VALIDATE.STATUS."""),
    ("Completion flags vs stage status", """
        GPO_CUST_HDR carries BOOLEAN completion flags: HIN_VALIDATED, DEA_VALIDATED,
        USPS_VALIDATED, COT_VALIDATED, HRSA_VALIDATED, MEMBER_VALIDATED, isOutputGenerated
        (0 = not done, 1 = done). Use these for 'has stage X been done for this batch'.
        Use GPO_VALIDATION_JOBS.*_STATUS for 'how did stage X end up'. CURRENT_ACTION on
        GPO_CUST_HDR names the stage the batch is sitting at
        ('UPLOAD', 'HIN', 'COT', 'HRSA', 'USPS', 'MEMBER', 'FINAL OUTPUT', 'CANCELLED')
        and is NULL for batches that have not progressed."""),
    ("Staged output vs final output", """
        GPO_CUST_STG_OUTPUT is the PRE-FINAL merge (carries both SOURCE_* and CORRECTED_* values);
        GPO_CUST_OUTPUT is the FINAL customer-facing deliverable (CORRECTED_* only). Never mix them
        in one answer, and never present staged rows as final output. 'Was output generated?' is
        answered by GPO_CUST_HDR.isOutputGenerated."""),
    ("Original vs corrected values", """
        Validation tables store the submitted value and the corrected value side by side:
        GPO_HIN_VALIDATE / GPO_DEA_VALIDATE / GPO_HRSA_VALIDATE / GPO_USPS_VALIDATE use
        ORIGINAL_* and UPDATED_*; GPO_COT_VALIDATE uses ORIGINAL_COT and CORRECTED_COT;
        GPO_CUST_STG_OUTPUT uses SOURCE_* and CORRECTED_*. When the user asks 'what changed',
        return both sides. A record was corrected when the two differ."""),
    ("Class of Trade is derived", """
        COT is NOT a master lookup. GPO_COT_VALIDATE reconciles ORIGINAL_COT against HIBCC_COT
        (from the HIN match), DEA_COT (from the DEA match) and RODB_COT to produce CORRECTED_COT,
        keyed by BATCH_NUM + CUSTOMER_NAME. There is no GPO_COT master table — do not invent one."""),
    ("Program-specific pipelines - ASK, DO NOT ASSUME", """
        Four parallel pipelines exist in this database with near-identical table shapes:
        GPO_* (the base/default program), REG_*, ABBOTT_* and EISAI_*.
        Use GPO_* tables unless the user explicitly names REG, Abbott or Eisai.
        If a question about batches, validation or output could apply to more than one program and
        the user has not said which, ASK which program they mean rather than guessing — the numbers
        differ completely between them.
        Note ABBOTT_* has no HIN/DEA/USPS validators (it uses ABBOTT_CYCLIC_VALIDATE and
        ABBOTT_PARENT_VALIDATE), and EISAI_* is change-tracking (additions/removals/changes),
        not validation."""),
    ("Membership vs member validation", """
        These are unrelated despite similar names.
        - MN_MEMBER / MN_ORGANIZATION_ID / MN_CF_ELIGIBLE_CUSTOMER = reference membership master
          data, keyed by MEMBER_ID, NOT batch-scoped.
        - GPO_MEMBER_VALIDATE = per-batch membership MATCHING results, keyed by BATCH_NUM + NAME.
        - GPO_MEMBERSHIP_HEIRARCHY = GPO parent/child org hierarchy.
        Pick by whether the question is about reference data or about a batch run."""),
    ("Audit trail", """
        GPO_LOGS is the only audit table for the GPO program (REG_LOGS and ABBOTT_LOGS for those
        programs). Query it by BATCH_NUM and USER_ACTION. Real USER_ACTION values include
        'HIN Validation', 'HIN Verification', 'HIN Selection', 'USPS Validation', 'DEA Validation',
        'COT Validation', 'Output File', 'STAGE_OUPTUT' (note the typo in the data) and
        'Upload Member File'."""),
    ("Column naming and safety", """
        Business columns in this database are UPPER_CASE (BATCH_NUM, ORIGINAL_HIN, CURRENT_ACTION),
        with a few exceptions: GPO_CUST_HDR.isOutputGenerated, GPO_LOGS.action_desc and
        GPO_COT_VALIDATE.Modified. Table name spellings to respect exactly:
        GPO_MEMBERSHIP_HEIRARCHY and EISAI_MEMBERSHIP_HEIRARCHY_CHANGES ('HEIRARCHY'),
        GPO_ADMIN_VALIDATION_CONFIG.SIMILIARITY_TYPE ('SIMILIARITY').
        Output tables use KEYNUM while GPO_CUST_INPUT/GPO_HIN/GPO_DEA use KEY_NUM.
        NEVER invent a table or column name — call describe_table('<name>') when unsure."""),
    ("Read-only and result size", """
        This source is strictly read-only: SELECT / SHOW / DESCRIBE / EXPLAIN only.
        Cross-table search is DISABLED here because of table sizes — use targeted SELECTs with a
        WHERE clause. Prefer aggregates (COUNT/GROUP BY) over returning raw rows from the large
        tables."""),
]

MEASURES = [
    ("batch_pipeline_status",
     "Per-stage status for a batch, joined to its header",
     "SELECT h.BATCH_NUM, h.FILE_NAME, h.CURRENT_ACTION, h.TOTAL_RECORDS, h.VALID_RECORDS, h.ERROR_RECORDS, "
     "j.STATUS, j.HIN_STATUS, j.DEA_STATUS, j.HRSA_STATUS, j.USPS_STATUS, j.COT_STATUS, j.MEMBER_STATUS, "
     "j.STG_STATUS, j.OUTPUT_STATUS, j.PROCESSING_TIME "
     "FROM GPO_CUST_HDR h JOIN GPO_VALIDATION_JOBS j ON h.BATCH_NUM = j.BATCH_NUM "
     "WHERE h.BATCH_NUM = <batch_num>"),
    ("recent_batches",
     "Most recently created batches with their validation completion flags",
     "SELECT BATCH_NUM, FILE_NAME, CREATED_DATE, CREATED_BY, CURRENT_ACTION, VALIDATION_TYPE, "
     "TOTAL_RECORDS, VALID_RECORDS, ERROR_RECORDS, HIN_VALIDATED, DEA_VALIDATED, HRSA_VALIDATED, "
     "USPS_VALIDATED, COT_VALIDATED, MEMBER_VALIDATED, isOutputGenerated "
     "FROM GPO_CUST_HDR ORDER BY CREATED_DATE DESC LIMIT 20"),
    ("failed_stages_by_batch",
     "Batches with any stage in a failed state (case-insensitive)",
     "SELECT BATCH_NUM, STATUS, HIN_STATUS, DEA_STATUS, HRSA_STATUS, USPS_STATUS, COT_STATUS, "
     "MEMBER_STATUS, STG_STATUS, OUTPUT_STATUS FROM GPO_VALIDATION_JOBS "
     "WHERE LOWER(STATUS) = 'failed' OR LOWER(HIN_STATUS) = 'failed' OR LOWER(DEA_STATUS) = 'failed' "
     "OR LOWER(HRSA_STATUS) = 'failed' OR LOWER(USPS_STATUS) = 'failed' OR LOWER(COT_STATUS) = 'failed' "
     "OR LOWER(MEMBER_STATUS) = 'failed' OR LOWER(OUTPUT_STATUS) = 'failed' ORDER BY BATCH_NUM DESC"),
    ("job_status_summary",
     "Count of batches by overall job status",
     "SELECT STATUS, COUNT(*) AS batch_count FROM GPO_VALIDATION_JOBS GROUP BY STATUS ORDER BY batch_count DESC"),
    ("hin_match_outcome_summary",
     "HIN match outcomes for a batch, by match type",
     "SELECT STATUS, MATCH_TYPE, COUNT(*) AS record_count FROM GPO_HIN_VALIDATE "
     "WHERE BATCH_NUM = <batch_num> GROUP BY STATUS, MATCH_TYPE ORDER BY record_count DESC"),
    ("hin_corrections_for_batch",
     "HIN records whose value or name was changed by validation",
     "SELECT BATCH_NUM, ORIGINAL_NAME, ORIGINAL_HIN, UPDATED_NAME, UPDATED_HIN, STATUS, MATCH_TYPE, "
     "SIMILARITY_SCORE FROM GPO_HIN_VALIDATE WHERE BATCH_NUM = <batch_num> "
     "AND (ORIGINAL_HIN <> UPDATED_HIN OR ORIGINAL_NAME <> UPDATED_NAME) LIMIT 200"),
    ("unmatched_hin_records",
     "Input records that found no HIN match in a batch",
     "SELECT BATCH_NUM, ORIGINAL_NAME, ORIGINAL_HIN, ORIGINAL_CITY, ORIGINAL_STATE, STATUS, MATCH_TYPE "
     "FROM GPO_HIN_VALIDATE WHERE BATCH_NUM = <batch_num> AND (STATUS = 'NO' OR MATCH_TYPE = 'no_match') LIMIT 200"),
    ("address_corrections_for_batch",
     "USPS address corrections applied in a batch",
     "SELECT BATCH_NUM, ORIGINAL_NAME, ORIGINAL_STREET, ORIGINAL_CITY, ORIGINAL_STATE, ORIGINAL_POSTAL_CODE, "
     "UPDATED_STREET, UPDATED_CITY, UPDATED_STATE, UPDATED_POSTAL_CODE, PLUS_4_CODE, ACTION "
     "FROM GPO_USPS_VALIDATE WHERE BATCH_NUM = <batch_num> AND (ORIGINAL_STREET <> UPDATED_STREET "
     "OR ORIGINAL_POSTAL_CODE <> UPDATED_POSTAL_CODE) LIMIT 200"),
    ("cot_discrepancies_for_batch",
     "Records where the corrected Class of Trade differs from the submitted one",
     "SELECT BATCH_NUM, CUSTOMER_NAME, ORIGINAL_COT, HIBCC_COT, DEA_COT, RODB_COT, CORRECTED_COT "
     "FROM GPO_COT_VALIDATE WHERE BATCH_NUM = <batch_num> AND CORRECTED_COT <> ORIGINAL_COT LIMIT 200"),
    ("member_match_summary",
     "Membership match outcomes for a batch, by criteria",
     "SELECT STATUS, MATCHING_CRITERIA, COUNT(*) AS record_count FROM GPO_MEMBER_VALIDATE "
     "WHERE BATCH_NUM = <batch_num> GROUP BY STATUS, MATCHING_CRITERIA ORDER BY record_count DESC"),
    ("final_output_for_batch",
     "Final formatted output rows for a batch",
     "SELECT KEYNUM, BATCH_NUM, NAME, CORRECTED_HIN, CORRECTED_DEA, CORRECTED_HRSA, STATUS, HIBCC_COT, "
     "DEA_COT, RODB_COT, MN_COT, CORRECTED_STREET, CORRECTED_CITY, CORRECTED_STATE, CORRECTED_POSTAL_CODE, "
     "MEMBER_MATCHING_CRITERIA FROM GPO_CUST_OUTPUT WHERE BATCH_NUM = <batch_num> LIMIT 200"),
    ("batches_awaiting_output",
     "Batches fully validated but with no output generated yet",
     "SELECT BATCH_NUM, FILE_NAME, CREATED_DATE, CURRENT_ACTION FROM GPO_CUST_HDR "
     "WHERE isOutputGenerated = 0 AND HIN_VALIDATED = 1 AND DEA_VALIDATED = 1 AND USPS_VALIDATED = 1 "
     "AND COT_VALIDATED = 1 ORDER BY CREATED_DATE DESC"),
    ("batch_audit_trail",
     "Audit trail for a batch, newest first",
     "SELECT BATCH_NUM, USER_ACTION, action_desc, CREATED_DATE, CREATED_BY FROM GPO_LOGS "
     "WHERE BATCH_NUM = <batch_num> ORDER BY CREATED_DATE DESC LIMIT 200"),
    ("action_volume_summary",
     "Most frequent audit actions across all batches",
     "SELECT USER_ACTION, COUNT(*) AS action_count FROM GPO_LOGS GROUP BY USER_ACTION ORDER BY action_count DESC"),
    ("role_permission_matrix",
     "Roles with their CRUD permissions",
     "SELECT r.ROLE_ID, r.ROLE, r.DESCRIPTION, p.CAN_VIEW, p.CAN_ADD, p.CAN_EDIT, p.CAN_DELETE "
     "FROM GPO_ROLE_MASTER r LEFT JOIN GPO_ROLE_PERMISSION p ON r.ROLE_ID = p.ROLE_ID ORDER BY r.ROLE_ID"),
    ("users_by_role",
     "Users assigned to each role",
     "SELECT r.ROLE, m.USER_ID, m.USERNAME, m.EMAIL, m.STATUS, m.ASSIGNED_DATE "
     "FROM GPO_ROLE_MAPPING m JOIN GPO_ROLE_MASTER r ON m.ROLE_ID = r.ROLE_ID ORDER BY r.ROLE, m.USERNAME"),
    ("recent_logins",
     "Most recent login sessions with the user's role",
     "SELECT l.USER_ID, m.USERNAME, r.ROLE, l.LOGIN_TIME, l.EXPIRY_TIME, l.STATUS "
     "FROM GPO_USER_LOGIN l LEFT JOIN GPO_ROLE_MAPPING m ON l.USER_ID = m.USER_ID "
     "LEFT JOIN GPO_ROLE_MASTER r ON m.ROLE_ID = r.ROLE_ID ORDER BY l.LOGIN_TIME DESC LIMIT 50"),
    ("members_with_organization_ids",
     "Members with their organization identifiers",
     "SELECT m.MEMBER_ID, m.MEMBER_NAME, m.MEMBER_GRP_NAME, o.TYPE, o.IDENTIFIER, o.PRIMARY_FLAG, "
     "o.START_DATE, o.END_DATE FROM MN_MEMBER m LEFT JOIN MN_ORGANIZATION_ID o "
     "ON m.MEMBER_ID = o.MEMBER_ID ORDER BY m.MEMBER_NAME"),
    ("eligible_customers_latest",
     "Current eligible-customer records per member",
     "SELECT m.MEMBER_ID, m.MEMBER_NAME, c.ELIGIBLE_CUSTOMER_ID, c.START_DATE, c.END_DATE, c.INC_FLAG "
     "FROM MN_CF_ELIGIBLE_CUSTOMER c JOIN MN_MEMBER m ON c.MEMBER_ID = m.MEMBER_ID "
     "WHERE c.IS_LATEST_ELIGIBILITY = 1 ORDER BY m.MEMBER_NAME"),
    ("contracts_by_document",
     "Structured contracts with their parent document",
     "SELECT d.STRUCT_DOC_ID, d.STRUCT_DOC_NAME, c.STRUCT_CTRT_ID, c.CTRT_DOC_STATUS, c.STRUCT_DOC_TYPE, "
     "c.CTRT_SUB_TYPE, c.CONTRACT_TERM, c.DATE_APPROVED, c.DATE_IMPLEMENTED "
     "FROM MN_STRUCTURED_CONTRACT c JOIN MN_STRUCTURED_DOC d ON c.STRUCT_DOC_ID = d.STRUCT_DOC_ID "
     "ORDER BY d.STRUCT_DOC_NAME"),
    ("membership_hierarchy",
     "GPO membership parent/child hierarchy",
     "SELECT GPO_ID, GPO_NAME, GRAND_PARENT_ID, GRAND_PARENT_NAME, PARENT_ID, PARENT_NAME, "
     "CHILD_ID, CHILD_NAME FROM GPO_MEMBERSHIP_HEIRARCHY ORDER BY GPO_NAME LIMIT 200"),
]


def yaml_block(text: str, indent: int) -> str:
    """Render a folded multi-line description as an indented YAML block scalar."""
    pad = " " * indent
    lines = [ln.strip() for ln in text.strip().split("\n")]
    return "\n".join(pad + ln for ln in lines if ln)


def describe(name: str, dump_comment: str) -> str:
    if name in TABLE_DESCRIPTIONS:
        return TABLE_DESCRIPTIONS[name]
    for prefix, desc in PREFIX_DESCRIPTIONS.items():
        if name.startswith(prefix):
            return desc
    return dump_comment or f"{name} table."


def main():
    with open(DUMP, encoding="utf-8") as f:
        dump = json.load(f)

    tables = {n: t for n, t in dump["tables"].items() if n not in SKIP_TABLES}
    fk_index = {}
    for fk in dump["declared_foreign_keys"]:
        if fk["table"] in SKIP_TABLES:
            continue
        fk_index[(fk["table"], fk["column"])] = f"{fk['ref_table']}.{fk['ref_column']}"

    out = []
    w = out.append

    w("# ============================================================")
    w("# GPO CUSTOMER ROSTER VALIDATION — SEMANTIC LAYER (DB 2)")
    w("# ============================================================")
    w("# GENERATED FILE — do not edit by hand.")
    w("#   Regenerate with:")
    w("#     python -m scripts.introspect_gpo")
    w("#     python -m scripts.build_gpo_semantic_model")
    w("#")
    w("# Columns, types and row counts are read from the live database, so they")
    w("# are accurate by construction. Business knowledge (domains, joins,")
    w("# mapping rules, measures) is curated in")
    w("# scripts/build_gpo_semantic_model.py.")
    w("# ============================================================")
    w("version: 2")
    w("semantic_model:")
    w("  name: gpo_customer_roster_validation")
    w("  description: >")
    w(yaml_block(
        f"Semantic layer for the GPO customer-roster validation platform "
        f"({dump['table_count']} tables in schema '{dump['database']}'). "
        "A batch of customer records is uploaded, staged, mapped to a standard shape, validated "
        "against HIN / DEA / HRSA / USPS master data plus Class-of-Trade and membership matching, "
        "then merged and formatted into a final output file. Every stage is status-tracked and "
        "audit-logged. The schema also holds membership/contract reference data, role-based access "
        "control, and three client-specific parallel pipelines (REG, Abbott, Eisai).", 4))
    w("")

    # --- programs -----------------------------------------------------
    w("  # ============================================================")
    w("  # PARALLEL PROGRAM PIPELINES — pick the right table prefix")
    w("  # ============================================================")
    w("  programs:")
    for pid, prefix, note in [
        ("gpo", "GPO_", "Base/default program. Use these tables unless the user names another program."),
        ("reg", "REG_", "REG program. Mirrors the GPO_* pipeline shape."),
        ("abbott", "ABBOTT_", "Abbott program. Customer LEH flow; uses ABBOTT_CYCLIC_VALIDATE and ABBOTT_PARENT_VALIDATE instead of HIN/DEA/USPS validators."),
        ("eisai", "EISAI_", "Eisai program. Roster change tracking (additions/removals/changes), not validation."),
    ]:
        members = sorted(n for n in tables if n.startswith(prefix))
        w(f"    - id: {pid}")
        w(f"      table_prefix: \"{prefix}\"")
        w(f"      table_count: {len(members)}")
        w(f"      note: >")
        w(yaml_block(note, 8))
    w("")

    # --- domains ------------------------------------------------------
    w("  # ============================================================")
    w("  # DOMAINS — business grouping, and the prompt-trimming index")
    w("  # ============================================================")
    w("  domains:")
    for d in DOMAINS:
        present = [t for t in d["tables"] if t in tables]
        w(f"    - name: {d['name']}")
        w(f"      purpose: >")
        w(yaml_block(d["purpose"], 8))
        w(f"      tables: [{', '.join(present)}]")
        kw = ", ".join(f'"{k}"' for k in d["keywords"])
        w(f"      keywords: [{kw}]")
    w("")

    # --- tables -------------------------------------------------------
    w("  # ============================================================")
    w("  # TABLES & COLUMNS (introspected from the live schema)")
    w("  # ============================================================")
    w("  sources:")
    w(f"    - name: mysql_gpo")
    w(f"      database: {dump['database']}")
    w("      tables:")

    domain_of = {}
    for d in DOMAINS:
        for t in d["tables"]:
            domain_of.setdefault(t, d["name"])

    for name in sorted(tables):
        t = tables[name]
        cols = t["columns"]
        w("")
        w(f"        - name: {name}")
        w(f"          row_count: {t['row_count']}")
        if name in domain_of:
            w(f"          domain: {domain_of[name]}")
        w("          description: >")
        w(yaml_block(describe(name, t.get("comment", "")), 12))
        w("          columns:")
        for c in cols[:MAX_COLS]:
            w(f"            - name: {c['name']}")
            w(f"              type: {c['type']}")
            ref = fk_index.get((name, c["name"]))
            if ref:
                w(f"              references: {ref}")
            elif c["key"] == "PRI":
                w("              key: primary")
            if c.get("comment"):
                w(f"              description: \"{c['comment']}\"")
        if len(cols) > MAX_COLS:
            remaining = len(cols) - MAX_COLS
            w(f"          # +{remaining} further columns not listed here —")
            w(f"          # call describe_table('{name}') for the complete list.")
    w("")

    # --- joins --------------------------------------------------------
    w("  # ============================================================")
    w("  # JOIN PATHS")
    w("  # 7 are declared foreign keys; the BATCH_NUM and master-lookup")
    w("  # paths are the documented pipeline flow.")
    w("  # ============================================================")
    w("  joins:")
    for jname, left, right, cond, desc in JOINS:
        if left not in tables or right not in tables:
            continue
        w(f"    - name: {jname}")
        w(f"      left_table: {left}")
        w(f"      right_table: {right}")
        w(f"      join_condition: \"{cond}\"")
        w(f"      description: \"{desc}\"")
    w("")

    # --- mapping rules ------------------------------------------------
    w("  # ============================================================")
    w("  # BUSINESS TO DATABASE MAPPING RULES (STRICT)")
    w("  # ============================================================")
    w("  mapping_rules:")
    for category, rule in MAPPING_RULES:
        w(f"    - category: \"{category}\"")
        w("      rule: >")
        w(yaml_block(rule, 8))
    w("")

    # --- measures -----------------------------------------------------
    w("  # ============================================================")
    w("  # PRE-DEFINED SQL MEASURES")
    w("  # Templates using verified column names. Replace <batch_num>")
    w("  # with the batch the user asked about.")
    w("  # ============================================================")
    w("  measures:")
    for mname, mdesc, msql in MEASURES:
        w(f"    - name: {mname}")
        w(f"      description: \"{mdesc}\"")
        w(f"      sql: \"{msql}\"")
    w("")

    text = "\n".join(out)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"tables written : {len(tables)} (skipped {len(SKIP_TABLES)} infra)")
    print(f"domains        : {len(DOMAINS)}")
    print(f"joins          : {len(JOINS)}")
    print(f"mapping rules  : {len(MAPPING_RULES)}")
    print(f"measures       : {len(MEASURES)}")
    print(f"output         : {OUT}  ({len(text):,} bytes)")


if __name__ == "__main__":
    main()
