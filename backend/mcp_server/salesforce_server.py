import os
import re
import sys
import json
import logging
from typing import List, Dict, Any
from fastmcp import FastMCP
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed, SalesforceExpiredSession

# Configure logging to write to stderr so we don't corrupt the stdio stream
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("mcp-salesforce-server")

# Initialize FastMCP Server
mcp = FastMCP("salesforce-server")

# --- Salesforce Connection ---

def get_sf_connection() -> Salesforce:
    """
    Establish a connection to Salesforce using environment variables.
    Supports two modes:
      1. Username/Password + Security Token authentication
      2. Session ID passthrough (for user-level auth from Salesforce frontend)
    """
    session_id = os.getenv("SF_SESSION_ID")
    instance_url = os.getenv("SF_INSTANCE_URL")

    # Mode 1: Session ID passthrough (preferred when running inside Salesforce context)
    if session_id and instance_url:
        logger.info("Connecting to Salesforce via Session ID passthrough...")
        return Salesforce(session_id=session_id, instance_url=instance_url)

    # Mode 2: Username/Password authentication
    username = os.getenv("SF_USERNAME", "")
    password = os.getenv("SF_PASSWORD", "")
    security_token = os.getenv("SF_SECURITY_TOKEN", "")
    domain = os.getenv("SF_DOMAIN", "login")  # 'login' for production, 'test' for sandbox

    if not username or not password:
        raise ValueError(
            "Salesforce credentials not configured. "
            "Set SF_USERNAME, SF_PASSWORD, SF_SECURITY_TOKEN, and SF_DOMAIN environment variables."
        )

    logger.info(f"Connecting to Salesforce as '{username}' via {domain}.salesforce.com...")
    try:
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain
        )
        logger.info(f"Successfully connected to Salesforce. Instance: {sf.sf_instance}")
        return sf
    except SalesforceAuthenticationFailed as e:
        logger.error(f"Salesforce authentication failed: {e}")
        raise e


# Helper: Validate that a SOQL query is read-only
def is_soql_safe(query: str) -> bool:
    """Ensure the query is a read-only SELECT statement."""
    cleaned = query.strip().upper()
    # SOQL should start with SELECT
    if not cleaned.startswith("SELECT"):
        return False
    # Reject any DML-like keywords (shouldn't appear in SOQL, but defense-in-depth)
    destructive_keywords = [
        "INSERT", "UPDATE", "DELETE", "UPSERT", "MERGE",
        "UNDELETE", "CREATE", "DROP", "ALTER", "TRUNCATE"
    ]
    for keyword in destructive_keywords:
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, cleaned):
            return False
    return True


# --- Default Salesforce Objects for schema overview ---
DEFAULT_OBJECTS = [
    "Account", "Contact", "Opportunity", "Lead", "Case",
    "Task", "Event", "Campaign", "CampaignMember",
    "Product2", "PricebookEntry", "OpportunityLineItem",
    "User", "Contract", "Order", "OrderItem", "Asset"
]


# --- MCP Tools ---

@mcp.tool()
def list_objects() -> str:
    """
    List the key Salesforce standard objects available for querying.
    Returns:
        A list of commonly used Salesforce object names.
    """
    try:
        sf = get_sf_connection()
        # Retrieve all sObjects from the org
        describe_result = sf.describe()
        sobjects = describe_result.get("sobjects", [])

        # Filter to queryable, non-deprecated objects
        queryable = [
            obj["name"] for obj in sobjects
            if obj.get("queryable", False) and not obj.get("deprecatedAndHidden", False)
        ]

        # Separate standard vs custom
        standard = sorted([o for o in queryable if not o.endswith("__c")])
        custom = sorted([o for o in queryable if o.endswith("__c")])

        output_lines = [f"Salesforce Objects ({len(queryable)} queryable):"]
        output_lines.append(f"\nStandard Objects ({len(standard)}): {', '.join(standard[:50])}")
        if len(standard) > 50:
            output_lines.append(f"  ... and {len(standard) - 50} more standard objects")
        if custom:
            output_lines.append(f"\nCustom Objects ({len(custom)}): {', '.join(custom[:30])}")
            if len(custom) > 30:
                output_lines.append(f"  ... and {len(custom) - 30} more custom objects")

        return "\n".join(output_lines)
    except Exception as e:
        return f"Error listing Salesforce objects: {str(e)}"


@mcp.tool()
def describe_object(object_name: str) -> str:
    """
    Get the fields, data types, and schema details of a specific Salesforce object.
    Args:
        object_name: The API name of the Salesforce object (e.g., 'Account', 'Contact', 'Opportunity').
    """
    # Sanitize input
    if not re.match(r"^[a-zA-Z0-9_]+$", object_name):
        return "Error: Invalid object name format. Use the API name (e.g., 'Account', 'My_Custom_Object__c')."

    try:
        sf = get_sf_connection()
        obj_desc = getattr(sf, object_name).describe()

        fields = obj_desc.get("fields", [])
        object_label = obj_desc.get("label", object_name)

        output = [f"Salesforce Object: {object_name} (Label: '{object_label}')"]
        output.append(f"Total Fields: {len(fields)}")
        output.append(f"Queryable: {obj_desc.get('queryable', 'N/A')}")
        output.append(f"Searchable: {obj_desc.get('searchable', 'N/A')}")
        output.append("")
        output.append("Fields:")

        for field in fields:
            name = field.get("name", "")
            label = field.get("label", "")
            field_type = field.get("type", "")
            nillable = field.get("nillable", False)
            length = field.get("length", 0)

            # Build compact field description
            type_info = field_type
            if length and field_type in ("string", "textarea", "url", "email", "phone"):
                type_info = f"{field_type}({length})"

            # Show relationship info for reference fields
            if field_type == "reference":
                ref_to = field.get("referenceTo", [])
                if ref_to:
                    type_info = f"reference -> {', '.join(ref_to)}"

            # Show picklist values for picklist fields
            if field_type in ("picklist", "multipicklist"):
                values = [pv.get("value", "") for pv in field.get("picklistValues", []) if pv.get("active")]
                if values:
                    type_info = f"{field_type} [{', '.join(values[:10])}]"
                    if len(values) > 10:
                        type_info += f" +{len(values) - 10} more"

            nullable_str = "nullable" if nillable else "required"
            output.append(f"  - {name} ({type_info}) | {nullable_str} | Label: '{label}'")

        return "\n".join(output)
    except Exception as e:
        return f"Error describing object '{object_name}': {str(e)}"


@mcp.tool()
def execute_soql(soql_query: str) -> str:
    """
    Execute a read-only SOQL query against the Salesforce instance.
    Only SELECT statements are allowed. Results are limited to 200 records.
    Args:
        soql_query: The SOQL query to execute (e.g., "SELECT Id, Name FROM Account LIMIT 10").
    """
    # 1. Enforce safety checks
    if not is_soql_safe(soql_query):
        return "Error: Forbidden query. Only read-only SOQL SELECT statements are allowed."

    try:
        sf = get_sf_connection()

        # Add a default LIMIT if none is present to prevent huge result sets
        limit_match = re.search(r"\bLIMIT\b\s+\d+", soql_query, re.IGNORECASE)
        executed_query = soql_query.strip().rstrip(";")
        if not limit_match:
            executed_query += " LIMIT 200"

        logger.info(f"Executing SOQL: {executed_query}")
        result = sf.query(executed_query)

        records = result.get("records", [])
        total_size = result.get("totalSize", 0)

        if total_size == 0:
            return "Query executed successfully. 0 records returned."

        # Clean Salesforce metadata from records (remove 'attributes' key)
        cleaned_records = []
        for record in records:
            clean = {}
            for key, value in record.items():
                if key == "attributes":
                    continue
                # Handle nested relationship objects (e.g., Account.Name on Contact)
                if isinstance(value, dict) and "attributes" in value:
                    nested_clean = {k: v for k, v in value.items() if k != "attributes"}
                    clean[key] = nested_clean
                else:
                    clean[key] = value
            cleaned_records.append(clean)

        output = {
            "totalSize": total_size,
            "recordsReturned": len(cleaned_records),
            "records": cleaned_records
        }

        return json.dumps(output, indent=2, default=str)

    except Exception as e:
        return f"Salesforce query error: {str(e)}"


@mcp.tool()
def search_records(sosl_query: str) -> str:
    """
    Perform a cross-object keyword search using SOSL (Salesforce Object Search Language).
    Use this for full-text searches across multiple objects.
    Args:
        sosl_query: The SOSL query string (e.g., "FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name), Contact(Id, Name)").
    """
    try:
        sf = get_sf_connection()

        logger.info(f"Executing SOSL: {sosl_query}")
        result = sf.search(sosl_query)

        search_records_list = result.get("searchRecords", [])

        if not search_records_list:
            return "Search completed. 0 records found."

        # Clean and group results by object type
        grouped = {}
        for record in search_records_list:
            obj_type = record.get("attributes", {}).get("type", "Unknown")
            clean = {k: v for k, v in record.items() if k != "attributes"}
            if obj_type not in grouped:
                grouped[obj_type] = []
            grouped[obj_type].append(clean)

        output = {
            "totalResults": len(search_records_list),
            "resultsByObject": grouped
        }

        return json.dumps(output, indent=2, default=str)

    except Exception as e:
        return f"Salesforce search error: {str(e)}"


# --- MCP Resources ---

@mcp.resource("schema://overview")
def get_schema_overview() -> str:
    """Get a summary of the key Salesforce object schemas for LLM context."""
    try:
        sf = get_sf_connection()

        # Discover which default objects actually exist in the org
        describe_result = sf.describe()
        available = {obj["name"] for obj in describe_result.get("sobjects", []) if obj.get("queryable")}

        # Also include any custom objects
        custom_objects = sorted([o for o in available if o.endswith("__c")])

        # Combine default + custom (limit custom to top 10 to keep context manageable)
        objects_to_describe = [o for o in DEFAULT_OBJECTS if o in available]
        objects_to_describe.extend(custom_objects[:10])

        overview = ["Salesforce Schema Overview:"]
        overview.append(f"Org Instance: {sf.sf_instance}")
        overview.append("")

        for obj_name in objects_to_describe:
            try:
                obj_desc = getattr(sf, obj_name).describe()
                fields = obj_desc.get("fields", [])
                label = obj_desc.get("label", obj_name)

                # Show key fields (limit to 25 most important)
                important_fields = []
                for f in fields:
                    fname = f.get("name", "")
                    ftype = f.get("type", "")
                    # Prioritize: Id, Name, standard fields, then others
                    important_fields.append(f"{fname} ({ftype})")

                # Cap at 25 fields for context window efficiency
                field_summary = ", ".join(important_fields[:25])
                if len(important_fields) > 25:
                    field_summary += f", ... +{len(important_fields) - 25} more fields"

                overview.append(f"Object '{obj_name}' (Label: '{label}'): [{field_summary}]")
            except Exception as e:
                overview.append(f"Object '{obj_name}': [Error reading schema: {e}]")

        return "\n".join(overview)
    except Exception as e:
        return f"Error retrieving Salesforce schema: {str(e)}"


if __name__ == "__main__":
    # Start FastMCP server in Stdio mode
    mcp.run()
