import os
import re
import json
import logging
from typing import List, Dict, Any
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed

logger = logging.getLogger("salesforce-service")

def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """Recursively flatten nested dictionary keys using dot notation, skipping Salesforce metadata 'attributes'."""
    items = []
    for k, v in d.items():
        if k == 'attributes':
            continue
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

class SalesforceService:
    """
    Direct Salesforce operations service.
    Replaces the MCP server tool implementations with direct python methods.
    """
    
    def __init__(self, username: str = "", password: str = "", security_token: str = "", domain: str = "login", session_id: str = None, instance_url: str = None):
        self.username = username
        self.password = password
        self.security_token = security_token
        self.domain = domain
        self.session_id = session_id
        self.instance_url = instance_url
        self._sf = None

    def get_connection(self) -> Salesforce:
        """Establish or return connection to Salesforce."""
        if self._sf:
            return self._sf

        # Mode 1: Session ID passthrough
        if self.session_id and self.instance_url:
            logger.info("Connecting to Salesforce via Session ID passthrough...")
            self._sf = Salesforce(session_id=self.session_id, instance_url=self.instance_url)
            return self._sf

        # Mode 2: Username/Password authentication
        if not self.username or not self.password:
            raise ValueError(
                "Salesforce credentials not configured. Please supply username and password."
            )

        logger.info(f"Connecting to Salesforce as '{self.username}' via {self.domain}.salesforce.com...")
        try:
            self._sf = Salesforce(
                username=self.username,
                password=self.password,
                security_token=self.security_token,
                domain=self.domain
            )
            logger.info(f"Successfully connected to Salesforce. Instance: {self._sf.sf_instance}")
            return self._sf
        except SalesforceAuthenticationFailed as e:
            logger.error(f"Salesforce authentication failed: {e}")
            raise e

    def is_soql_safe(self, query: str) -> bool:
        """Ensure the query is a read-only SELECT statement."""
        cleaned = query.strip().upper()
        if not cleaned.startswith("SELECT"):
            return False
        destructive_keywords = [
            "INSERT", "UPDATE", "DELETE", "UPSERT", "MERGE",
            "UNDELETE", "CREATE", "DROP", "ALTER", "TRUNCATE"
        ]
        for keyword in destructive_keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, cleaned):
                return False
        return True

    def list_objects(self) -> str:
        """
        List key Salesforce objects available for querying.
        """
        try:
            sf = self.get_connection()
            describe_result = sf.describe()
            sobjects = describe_result.get("sobjects", [])

            queryable = [
                obj["name"] for obj in sobjects
                if obj.get("queryable", False) and not obj.get("deprecatedAndHidden", False)
            ]

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

    def describe_object(self, object_name: str) -> str:
        """
        Get field details and schema of a specific Salesforce object.
        """
        if not re.match(r"^[a-zA-Z0-9_]+$", object_name):
            return "Error: Invalid object name format."

        try:
            sf = self.get_connection()
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

                type_info = field_type
                if length and field_type in ("string", "textarea", "url", "email", "phone"):
                    type_info = f"{field_type}({length})"

                if field_type == "reference":
                    ref_to = field.get("referenceTo", [])
                    if ref_to:
                        type_info = f"reference -> {', '.join(ref_to)}"

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

    def execute_soql(self, soql_query: str) -> str:
        """
        Execute read-only SOQL query against Salesforce. Limit defaults to 200 records.
        """
        if not self.is_soql_safe(soql_query):
            return json.dumps({"error": "Error: Forbidden query. Only read-only SOQL SELECT statements are allowed."})

        try:
            sf = self.get_connection()
            limit_match = re.search(r"\bLIMIT\b\s+\d+", soql_query, re.IGNORECASE)
            executed_query = soql_query.strip().rstrip(";")
            if not limit_match:
                is_aggregate = re.search(r"\b(COUNT\s*\(\s*\)|COUNT\s*\(|SUM\s*\(|AVG\s*\(|MIN\s*\(|MAX\s*\()", soql_query, re.IGNORECASE)
                is_grouped = re.search(r"\bGROUP\s+BY\b", soql_query, re.IGNORECASE)
                if not (is_aggregate and not is_grouped):
                    executed_query += " LIMIT 200"

            logger.info(f"Executing SOQL directly: {executed_query}")
            result = sf.query(executed_query)

            records = result.get("records", [])
            total_size = result.get("totalSize", 0)

            if total_size == 0:
                return json.dumps({
                    "totalSize": 0,
                    "recordsReturned": 0,
                    "records": []
                })

            cleaned_records = []
            for record in records:
                cleaned_records.append(flatten_dict(record))

            output = {
                "totalSize": total_size,
                "recordsReturned": len(cleaned_records),
                "records": cleaned_records
            }
            return json.dumps(output, indent=2, default=str)

        except Exception as e:
            return json.dumps({"error": f"Salesforce query error: {str(e)}"})

    def search_records(self, sosl_query: str) -> str:
        """
        Perform cross-object search using SOSL.
        """
        try:
            sf = self.get_connection()
            logger.info(f"Executing SOSL directly: {sosl_query}")
            result = sf.search(sosl_query)
            search_records_list = result.get("searchRecords", [])

            if not search_records_list:
                return json.dumps({"totalResults": 0, "resultsByObject": {}})

            grouped = {}
            for record in search_records_list:
                obj_type = record.get("attributes", {}).get("type", "Unknown")
                clean = flatten_dict(record)
                if obj_type not in grouped:
                    grouped[obj_type] = []
                grouped[obj_type].append(clean)

            output = {
                "totalResults": len(search_records_list),
                "resultsByObject": grouped
            }
            return json.dumps(output, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"Salesforce search error: {str(e)}"})

    def get_schema_overview(self) -> str:
        """Get summary of custom and default objects for LLM context."""
        try:
            sf = self.get_connection()
            describe_result = sf.describe()
            available = {obj["name"] for obj in describe_result.get("sobjects", []) if obj.get("queryable")}

            default_objects = ["Doctor__c", "Rep_Details__c", "Rep_Manager__c"]
            custom_objects = sorted([o for o in available if o.endswith("__c")])

            objects_to_describe = [o for o in default_objects if o in available]
            # Add other custom objects (limit top 10)
            for custom_obj in custom_objects[:10]:
                if custom_obj not in objects_to_describe:
                    objects_to_describe.append(custom_obj)

            overview = ["Salesforce Schema Overview:"]
            overview.append(f"Org Instance: {sf.sf_instance}")
            overview.append("")

            for obj_name in objects_to_describe:
                try:
                    obj_desc = getattr(sf, obj_name).describe()
                    fields = obj_desc.get("fields", [])
                    label = obj_desc.get("label", obj_name)

                    important_fields = []
                    for f in fields:
                        important_fields.append(f"{f.get('name')} ({f.get('type')})")

                    field_summary = ", ".join(important_fields[:25])
                    if len(important_fields) > 25:
                        field_summary += f", ... +{len(important_fields) - 25} more fields"

                    overview.append(f"Object '{obj_name}' (Label: '{label}'): [{field_summary}]")
                except Exception as e:
                    overview.append(f"Object '{obj_name}': [Error reading schema: {e}]")

            return "\n".join(overview)
        except Exception as e:
            return f"Error retrieving Salesforce schema: {str(e)}"
