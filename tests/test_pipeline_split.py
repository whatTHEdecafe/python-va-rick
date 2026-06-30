"""
Tests for Version 9 pipeline split: vision vs logistics.
"""

import hashlib
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

# Version 9 Gemini package
V9_GEMINI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Version 9", "Gemini",
)
if V9_GEMINI not in sys.path:
    sys.path.insert(0, V9_GEMINI)

_UI_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "UI App")
if _UI_APP not in sys.path:
    sys.path.insert(0, _UI_APP)

import importlib.util

from pipeline_utils import hash_uploaded_files

from modules.item_enrichment import enrich_items
from modules.calculator import MovingCalculator

_agent_path = os.path.join(V9_GEMINI, "vision-agent.py")
_spec = importlib.util.spec_from_file_location("vision_agent_test", _agent_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
MoovEZVisionAnalyzerV7 = _mod.MoovEZVisionAnalyzerV7


class _MockUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


class TestUploadFingerprint(unittest.TestCase):
    def test_same_content_different_mtime_and_path(self):
        data = b"fake image bytes for fingerprint test"
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            p1 = os.path.join(d1, "room.jpg")
            p2 = os.path.join(d2, "room.jpg")
            with open(p1, "wb") as f:
                f.write(data)
            time.sleep(0.05)
            with open(p2, "wb") as f:
                f.write(data)
            os.utime(p2, (time.time() + 100, time.time() + 100))

            fp_upload = hash_uploaded_files([_MockUpload("room.jpg", data)])
            self.assertEqual(
                fp_upload,
                hash_uploaded_files([_MockUpload("room.jpg", data)]),
            )

            # Path/mtime style hash would differ; content hash must not
            def path_mtime_fingerprint(path):
                st = os.stat(path)
                part = f"{os.path.basename(path)}:{st.st_size}:{int(st.st_mtime)}"
                return hashlib.sha256(part.encode()).hexdigest()

            self.assertNotEqual(path_mtime_fingerprint(p1), path_mtime_fingerprint(p2))

    def test_different_bytes_different_fingerprint(self):
        a = hash_uploaded_files([_MockUpload("a.jpg", b"one")])
        b = hash_uploaded_files([_MockUpload("a.jpg", b"two")])
        self.assertNotEqual(a, b)


class TestEnrichItems(unittest.TestCase):
    def setUp(self):
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Data")
        db_path = os.path.join(data_dir, "converted_items_lowered.json")
        if not os.path.isfile(db_path):
            self.skipTest("converted_items_lowered.json not found")
        self.calculator = MovingCalculator(items_file=db_path)

    def test_enrich_fills_weight_and_volume(self):
        raw = [{"name": "sofa", "quantity": 1, "location": "living room"}]
        enriched = enrich_items(self.calculator, raw)
        self.assertEqual(len(enriched), 1)
        item = enriched[0]
        self.assertIn("weight", item)
        self.assertIn("volume", item)
        self.assertGreater(item["weight"], 0)
        self.assertGreater(item["volume"], 0)
        self.assertIn(item["size"], ("small", "medium", "large"))


class TestLogisticsWithoutGemini(unittest.TestCase):
    def setUp(self):
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Data")
        db_path = os.path.join(data_dir, "converted_items_lowered.json")
        if not os.path.isfile(db_path):
            self.skipTest("database not found")

        mock_client = MagicMock()
        mock_client.model_name = "test-model"
        mock_client.generate_content = MagicMock(side_effect=AssertionError("Gemini should not be called"))
        self.analyzer = MoovEZVisionAnalyzerV7(ai_client=mock_client, items_file=db_path)

    def test_compute_logistics_no_gemini(self):
        items = self.analyzer.enrich_items([
            {"name": "sofa", "quantity": 1, "location": "living room"},
        ])
        result = self.analyzer.compute_logistics(
            items,
            {"type": "ground", "floors": 0},
            {"type": "ground", "floors": 0},
            travel_time=30,
            pre_move_travel=30,
        )
        self.assertIsNotNone(result)
        self.assertIn("pricing", result)
        self.assertIn("material", result)
        mock_client = self.analyzer.ai_client
        mock_client.generate_content.assert_not_called()

    def test_analyze_media_calls_gemini_once(self):
        mock_client = self.analyzer.ai_client
        mock_client.get_vision_prompt = MagicMock(return_value="prompt")
        mock_client.parse_response = MagicMock(return_value={
            "items": [{"name": "chair", "quantity": 2, "location": "office"}],
            "summary": {"totalItems": 2},
        })
        mock_client.upload_file = MagicMock(return_value=MagicMock(name="f", state=MagicMock(name="ACTIVE")))
        mock_client.wait_for_file_processing = MagicMock(return_value=True)
        mock_client.cleanup_file = MagicMock(return_value=True)
        mock_client.generate_content = MagicMock(return_value=MagicMock())

        with patch.object(self.analyzer.file_factory, "classify_files", return_value={
            "images": ["/tmp/fake.jpg"],
            "videos": [],
            "unsupported": [],
        }), patch.object(
            self.analyzer.file_factory, "get_handler"
        ) as mock_handler:
            h = MagicMock()
            h.get_file_info.return_value = {"dimensions": "100x100"}
            mock_handler.return_value = h
            with patch("os.path.exists", return_value=True):
                vision = self.analyzer.analyze_media(["/tmp/fake.jpg"])

        self.assertIsNotNone(vision)
        self.assertEqual(len(vision["items"]), 1)
        mock_client.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
