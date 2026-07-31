import unittest
from app.semantic.loader import SemanticModelLoader

class TestSemanticModelLoader(unittest.TestCase):
    def setUp(self):
        self.loader = SemanticModelLoader()

    def test_load_yaml(self):
        self.assertIsNotNone(self.loader.model_data)
        model = self.loader.model_data.get("semantic_model", {})
        self.assertEqual(model.get("name"), "pharma_commercial_command_centre")

    def test_primary_ui_tables_present(self):
        """All 4 primary UI tables must be in the prompt"""
        prompt = self.loader.get_semantic_context_prompt()
        primary_tables = [
            "Leakage_Activity", "fatigue_score",
            "leakage_history", "Compliance_Table"
        ]
        for table in primary_tables:
            self.assertIn(table, prompt, f"Primary UI table '{table}' missing from prompt")

    def test_transaction_and_reference_tables_present(self):
        """Transaction and reference tables must be in the prompt"""
        prompt = self.loader.get_semantic_context_prompt()
        tables = [
            "copay_Claims_Transactions", "Product_Master", "hcp_master",
            "Zip_Geography_Master", "Payer_Master", "campaign_master",
            "hcp_engagement_logs", "Reverse_Claims", "Reject_Code_Master",
            "territory_master"
        ]
        for table in tables:
            self.assertIn(table, prompt, f"Table '{table}' missing from prompt")

    def test_mapping_rules_present(self):
        prompt = self.loader.get_semantic_context_prompt()
        self.assertIn("BUSINESS TO DATABASE MAPPING RULES", prompt)
        self.assertIn("Leakage Metrics", prompt)
        self.assertIn("Fatigue Scores", prompt)
        self.assertIn("Copay Claims", prompt)
        self.assertIn("Column Name Safety", prompt)

    def test_verified_join_paths_present(self):
        prompt = self.loader.get_semantic_context_prompt()
        self.assertIn("EXPLICIT JOIN PATHS", prompt)
        # copay_Claims_Transactions joins (primary claims table)
        self.assertIn("copay_Claims_Transactions.Prescriber_NPI = hcp_master.Prescriber_NPI", prompt)
        self.assertIn("copay_Claims_Transactions.payer_id = Payer_Master.payer_id", prompt)
        self.assertIn("copay_Claims_Transactions.reject_code = Reject_Code_Master.reject_code", prompt)
        # Engagement joins
        self.assertIn("hcp_engagement_logs.Campaign_ID = campaign_master.campaign_id", prompt)
        self.assertIn("hcp_engagement_logs.HCP_ID = hcp_master.Prescriber_NPI", prompt)
        # Compliance join
        self.assertIn("Compliance_Table.Payer_id = Payer_Master.payer_id", prompt)

    def test_measures_present(self):
        prompt = self.loader.get_semantic_context_prompt()
        self.assertIn("PRE-DEFINED SQL MEASURES", prompt)
        self.assertIn("top_leakage_by_hcp", prompt)
        self.assertIn("rejected_claims_by_specialty", prompt)
        self.assertIn("claims_by_payer_type", prompt)
        self.assertIn("hcp_fatigue_summary", prompt)
        self.assertIn("email_open_rate_by_campaign", prompt)
        self.assertIn("compliance_by_payer", prompt)

    def test_copay_prioritized_over_reverse_claims(self):
        """Ensure copay_Claims_Transactions is the primary claims table"""
        prompt = self.loader.get_semantic_context_prompt()
        self.assertIn("copay_Claims_Transactions", prompt)
        self.assertIn("713 rows", prompt)

if __name__ == "__main__":
    unittest.main()
