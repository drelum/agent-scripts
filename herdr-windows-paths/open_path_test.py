"""Regressões da seleção de paths; sem abrir o Explorer."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("open_path", Path(__file__).with_name("open_path.py"))
open_path = importlib.util.module_from_spec(spec)
spec.loader.exec_module(open_path)


class PathSelectionTests(unittest.TestCase):
    def test_preserves_hidden_relative_and_parent_paths(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / ".fixture").touch()
            child = base / "child"
            child.mkdir()
            for selected, cwd in [(".fixture", root), ("./.fixture", root), ("../.fixture", str(child))]:
                with self.subTest(selected=selected), patch.object(open_path, "wslpath_w", return_value="converted") as convert:
                    self.assertEqual(open_path.from_selection(selected, cwd), "converted")
                    convert.assert_called_once_with(str(base / ".fixture"))

    def test_preserves_spaces_and_trailing_period_in_existing_filename(self):
        with tempfile.TemporaryDirectory() as root:
            name = "arquivo  com espaço."
            target = Path(root) / name
            target.touch()
            with patch.object(open_path, "wslpath_w", return_value="converted") as convert:
                self.assertEqual(open_path.from_selection(f"`{name}`", root), "converted")
                convert.assert_called_once_with(str(target))

    def test_missing_file_does_not_call_converter(self):
        with tempfile.TemporaryDirectory() as root, patch.object(open_path, "wslpath_w") as convert:
            self.assertIsNone(open_path.from_selection("missing.txt", root))
            convert.assert_not_called()

    def test_wrappers_do_not_remove_filename_parentheses(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("relatório (final)", "relatório (final", "(relatório)"):
                (Path(root) / name).touch()
            for selected, name in [
                ("relatório (final)", "relatório (final)"),
                ("`relatório (final)`", "relatório (final)"),
                ("(relatório)", "(relatório)"),
                ("[(`relatório (final)`)]", "relatório (final)"),
            ]:
                with self.subTest(selected=selected), patch.object(open_path, "wslpath_w", return_value="converted") as convert:
                    self.assertEqual(open_path.from_selection(selected, root), "converted")
                    convert.assert_called_once_with(str(Path(root) / name))

    def test_uri_and_windows_selection_keep_unicode_and_spaces(self):
        self.assertEqual(open_path.from_file_uri("file:///C:/Pasta%20com%20espa%C3%A7o/a.txt"), "C:\\Pasta com espaço\\a.txt")
        self.assertEqual(open_path.from_file_uri("file://wsl.localhost/Ubuntu/home/a.txt"), "\\\\wsl.localhost\\Ubuntu\\home\\a.txt")
        self.assertEqual(open_path.from_selection("`C:\\Pasta  com espaço\\a.txt`", None), "C:\\Pasta  com espaço\\a.txt")


if __name__ == "__main__":
    unittest.main()
