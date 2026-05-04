import os
import unittest
from unittest.mock import patch

from web import server


class WebServerPathTests(unittest.TestCase):
    def test_derivatives_json_directory_is_exposed(self):
        self.assertIn("derivatives_json", server.DIR_MAP)
        self.assertTrue(server.DIR_MAP["derivatives_json"].endswith(os.path.join("outputs", "derivatives_json")))

    def test_coverage_json_directory_is_exposed(self):
        self.assertIn("coverage_json", server.DIR_MAP)
        self.assertTrue(server.DIR_MAP["coverage_json"].endswith(os.path.join("outputs", "coverage_json")))

    def test_resolve_output_file_allows_file_inside_mapped_directory(self):
        target_dir = os.path.abspath(os.path.join("outputs", "json"))

        with patch.dict(server.DIR_MAP, {"json": target_dir}, clear=True):
            resolved = server.resolve_output_file("json", "20260429.json")

        self.assertEqual(resolved, os.path.join(target_dir, "20260429.json"))

    def test_resolve_output_file_rejects_parent_directory_traversal(self):
        target_dir = os.path.abspath(os.path.join("outputs", "json"))

        with patch.dict(server.DIR_MAP, {"json": target_dir}, clear=True):
            resolved = server.resolve_output_file("json", "..\\global_json\\secret.json")

        self.assertIsNone(resolved)

    def test_resolve_output_file_rejects_common_prefix_sibling(self):
        target_dir = os.path.abspath(os.path.join("outputs", "json"))

        with patch.dict(server.DIR_MAP, {"json": target_dir}, clear=True):
            resolved = server.resolve_output_file("json", "..\\json_backup\\secret.json")

        self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
