import os
import unittest
from unittest.mock import patch, AsyncMock, Mock
from fastapi.testclient import TestClient
from main import app, limiter
from security import sign_audit

class TestAPISecurity(unittest.TestCase):
    def setUp(self):
        try:
            limiter._storage.reset()
        except:
            pass
        self.client = TestClient(app)
        self.valid_payload = {
            "name": "Test Farm",
            "lat": 4.5,
            "lon": -74.2,
            "cf_turnstile_response": "valid_token"
        }
        self.mock_audit = {
            "audit_id": "123", "signature": "abc", "risk_score": 0, 
            "risk_level": "LOW", "eudr_status": "NO POST-2020 LOSS DETECTED",
            "farm_name": "Test Farm", "latitude": 4.5, "longitude": -74.2,
            "tree_cover": 50, "loss_year": 0, "source": "ee", "dataset_version": "Hansen 2023"
        }

    @patch("main.verify_turnstile", new_callable=AsyncMock)
    def test_turnstile_blocks_robots(self, mock_verify):
        mock_verify.return_value = False
        response = self.client.post("/eudr-check", json=self.valid_payload)
        self.assertEqual(response.status_code, 403)

    @patch("main.verify_turnstile", new_callable=AsyncMock)
    @patch("main.create_audit")
    def test_turnstile_accepts_humans(self, mock_create, mock_verify):
        mock_verify.return_value = True
        mock_create.return_value = self.mock_audit
        response = self.client.post("/eudr-check", json=self.valid_payload)
        self.assertEqual(response.status_code, 200)

    @patch("main.verify_turnstile", new_callable=AsyncMock)
    def test_boolean_coordinates_rejected(self, mock_verify):
        mock_verify.return_value = True
        payload = self.valid_payload.copy()
        payload["lat"] = True
        response = self.client.post("/eudr-check", json=payload)
        self.assertEqual(response.status_code, 400)

    @patch("main.verify_turnstile", new_callable=AsyncMock)
    def test_invalid_polygon_rejected(self, mock_verify):
        mock_verify.return_value = True
        payload = self.valid_payload.copy()
        payload["polygon"] = [[4.5, -74.2], [4.6, -74.3]]
        response = self.client.post("/eudr-check", json=payload)
        self.assertEqual(response.status_code, 400)

    @patch("main.verify_turnstile", new_callable=AsyncMock)
    def test_self_intersecting_polygon_rejected(self, mock_verify):
        mock_verify.return_value = True
        payload = self.valid_payload.copy()
        payload["polygon"] = [[4.5, -74.2], [4.6, -74.3], [4.6, -74.2], [4.5, -74.3]]
        response = self.client.post("/eudr-check", json=payload)
        self.assertEqual(response.status_code, 400)

    @patch("main.verify_turnstile", new_callable=AsyncMock)
    @patch("main.create_audit")
    def test_rate_limiting(self, mock_create, mock_verify):
        mock_verify.return_value = True
        mock_create.return_value = self.mock_audit
        for _ in range(5):
            self.client.post("/eudr-check", json=self.valid_payload)
        response = self.client.post("/eudr-check", json=self.valid_payload)
        self.assertEqual(response.status_code, 429)

    def test_new_signature_valid(self):
        sig = sign_audit("audit123")
        with patch("main.get_audit") as mock_get:
            mock_get.return_value = self.mock_audit
            response = self.client.get(f"/eudr/verify/audit123?signature={sig}")
            self.assertEqual(response.status_code, 200)

    def test_invalid_signature_rejected(self):
        response = self.client.get("/eudr/verify/audit123?signature=bad_signature")
        self.assertEqual(response.status_code, 403)
