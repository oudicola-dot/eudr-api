import unittest
from unittest.mock import patch
import eudr
import sqlite3
import os
import math

class TestEUDRLogic(unittest.TestCase):
    
    # --- Tests sur compute_risk_ee (Calcul brut) ---
    
    @patch('eudr.EE_INITIALIZED', True)
    @patch('eudr.ee')
    def test_histogram_empty(self, mock_ee):
        mock_ee.Image.return_value.select.return_value.reduceRegion.return_value.get.return_value.getInfo.side_effect = [80, 1000, {}]
        res = eudr.compute_risk_ee(4.5, -74.2)
        self.assertTrue(res["insufficient_data"])

    @patch('eudr.EE_INITIALIZED', True)
    @patch('eudr.ee')
    def test_histogram_mismatch(self, mock_ee):
        # Somme de l'histogramme (500) != valid_pixels (1000)
        mock_ee.Image.return_value.select.return_value.reduceRegion.return_value.get.return_value.getInfo.side_effect = [80, 1000, {'0': 500}]
        res = eudr.compute_risk_ee(4.5, -74.2)
        self.assertTrue(res["insufficient_data"])

    @patch('eudr.EE_INITIALIZED', True)
    @patch('eudr.ee')
    def test_histogram_nan(self, mock_ee):
        mock_ee.Image.return_value.select.return_value.reduceRegion.return_value.get.return_value.getInfo.side_effect = [80, 1000, {'0': 1000, '22': float('nan')}]
        res = eudr.compute_risk_ee(4.5, -74.2)
        self.assertTrue(res["insufficient_data"])

    @patch('eudr.EE_INITIALIZED', True)
    @patch('eudr.ee')
    def test_histogram_invalid_year(self, mock_ee):
        mock_ee.Image.return_value.select.return_value.reduceRegion.return_value.get.return_value.getInfo.side_effect = [80, 1000, {'0': 900, '99': 100}]
        res = eudr.compute_risk_ee(4.5, -74.2)
        self.assertTrue(res["insufficient_data"])

    # --- Tests sur compute_risk (Orchestrateur de statuts) ---

    @patch('eudr.compute_risk_ee')
    def test_orchestrator_invalid_loss_pct(self, mock_ee):
        # Test des valeurs invalides : None, NaN, Infinity, -5
        invalid_values = [None, float('nan'), float('inf'), -5.0]
        for val in invalid_values:
            with self.subTest(val=val):
                mock_ee.return_value = {
                    "tree_cover_mean_ee": 50, 
                    "loss_percentage": val, 
                    "last_loss_year": 0, 
                    "source": "ee", 
                    "insufficient_data": False,
                    "estimated_coverage_pct": 100.0,
                    "valid_pixels": 100,
                    "nominal_pixels_estimate": 100,
                    "insufficient_reason": None,
                    "treecover_reason": None
                }
                res = eudr.compute_risk(4.5, -74.2)
                self.assertEqual(res["eudr_status"], "INSUFFICIENT DATA")

    @patch('eudr.compute_risk_ee')
    def test_orchestrator_thresholds(self, mock_ee):
        # Test des 5 seuils critiques
        test_cases = [
            (0.0, "NO POST-2020 LOSS DETECTED", "LOW"),
            (0.5, "BELOW TDM SCREENING THRESHOLD", "LOW"),
            (1.0, "POTENTIAL LOSS SIGNAL", "MEDIUM"),
            (5.0, "POTENTIAL LOSS SIGNAL", "MEDIUM"),
            (5.1, "POTENTIAL LOSS SIGNAL", "HIGH")
        ]
        for loss_pct, expected_status, expected_level in test_cases:
            with self.subTest(loss_pct=loss_pct):
                mock_ee.return_value = {
                    "tree_cover_mean_ee": 50, 
                    "loss_percentage": loss_pct, 
                    "last_loss_year": 2022, 
                    "source": "ee", 
                    "insufficient_data": False,
                    "estimated_coverage_pct": 100.0,
                    "valid_pixels": 100,
                    "nominal_pixels_estimate": 100,
                    "insufficient_reason": None,
                    "treecover_reason": None
                }
                res = eudr.compute_risk(4.5, -74.2)
                self.assertEqual(res["eudr_status"], expected_status)
                self.assertEqual(res["risk_level"], expected_level)

    # --- Tests SQLite ---

    def test_sqlite_migration_and_read_null(self):
        test_db = "test_eudr.db"
        if os.path.exists(test_db): os.remove(test_db)
        with patch('eudr.DB_PATH', test_db):
            eudr.init_db()
            conn = sqlite3.connect(test_db)
            c = conn.cursor()
            c.execute("INSERT INTO audits (audit_id, farm_name, latitude, longitude, risk_score, risk_level, eudr_compliant, tree_cover, loss_year, source, status, issuer, signature, created_at) VALUES ('old', 'Farm', 0, 0, 0, 'LOW', 'NO', 0, 0, 'ee', 'OK', 'TDM', 'sig', 'date')")
            conn.commit()
            conn.close()
            audit = eudr.get_audit('old')
            self.assertIsNone(audit['dataset_version'])
        if os.path.exists(test_db): os.remove(test_db)

    def test_sqlite_create_and_read_new(self):
        test_db = "test_eudr.db"
        if os.path.exists(test_db): os.remove(test_db)
        with patch('eudr.DB_PATH', test_db):
            eudr.init_db()
            with patch('eudr.compute_risk') as mock_risk:
                mock_risk.return_value = {
                    "risk_score": 50, 
                    "risk_level": "MEDIUM", 
                    "eudr_status": "POTENTIAL LOSS SIGNAL",
                    "tree_cover": 80, 
                    "loss_year": 2022, 
                    "source": "ee", 
                    "dataset_version": "TEST_V1",
                    "valid_pixels": 100,
                    "nominal_pixels_estimate": 100,
                    "estimated_coverage_pct": 100.0,
                    "insufficient_reason": None,
                    "treecover_reason": None
                }
                audit = eudr.create_audit("New Farm", 4.5, -74.2)
                read_audit = eudr.get_audit(audit["audit_id"])
                self.assertEqual(read_audit["dataset_version"], "TEST_V1")
        if os.path.exists(test_db): os.remove(test_db)

if __name__ == '__main__':
    unittest.main()
