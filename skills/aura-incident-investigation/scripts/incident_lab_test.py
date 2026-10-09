import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch, Mock, MagicMock

SKILL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lab", SKILL / "scripts/incident_lab.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
BASE = "https://us.posthog.com/project/331102/replay/01a11b7c-5e53-795c-b83b-9e9d12562164"


class ReadOnlyTests(unittest.TestCase):
    def test_comments_and_multiple_statements_rejected(self):
        for sql in ("SELECT 1; DELETE FROM aura.cart", "SELECT 1;;", "SELECT 1 /*! INTO OUTFILE 'x' */", "/* hi */ SELECT 1", "SELECT 1 -- hi", "SELECT 1 # hi"):
            with self.subTest(sql=sql), self.assertRaises(lab.LabError):
                lab.assert_read_only(sql)

    def test_semicolon_and_keywords_inside_literal(self):
        self.assertEqual(lab.assert_read_only("SELECT 'DELETE; --; #', 'a'';b';"), "SELECT 'DELETE; --; #', 'a'';b'")

    def test_write_cte_outfile_and_server_settings_rejected(self):
        for sql in ("WITH x AS (SELECT 1) DELETE FROM cart", "SELECT 1 INTO OUTFILE 'x'", "EXPLAIN UPDATE cart SET id=1", "SELECT 1 SETTINGS readonly=0", "SELECT url('https://x')", "SELECTevil 1", "SELECT 'unfinished"):
            with self.subTest(sql=sql), self.assertRaises(lab.LabError):
                lab.assert_read_only(sql)


class SecretTests(unittest.TestCase):
    def test_nested_secrets_and_url_credentials_removed(self):
        original = {"token": "private", "nested": {"headers": {"Authorization": "private"}}, "path": "https://user:private@example.com/cart?token=private#private", "text": "Bearer private"}
        cleaned = json.dumps(lab.sanitize(original))
        self.assertNotIn("private", cleaned)
        self.assertIn("https://example.com/cart", cleaned)

    def test_column_names_govern_secret_redaction(self):
        self.assertEqual(lab.safe_rows(["id", "api_token"], [(1, "private")]), [[1, "[REDACTED]"]])

    def test_errors_do_not_echo_process_payload(self):
        failed = Mock(returncode=1, stdout="private-secret", stderr="403 private-secret")
        with patch.object(lab.subprocess, "run", return_value=failed), self.assertRaises(lab.LabError) as error:
            lab.command(["gcloud", "dummy"])
        self.assertNotIn("private", str(error.exception))
        self.assertIn("Acesso negado", str(error.exception))

    def test_redirects_never_forward_authorization(self):
        self.assertIsNone(lab.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))


class ReplayTests(unittest.TestCase):
    def test_timing_sao_paulo_and_upper_bound(self):
        result = lab.replay_link(BASE, "2026-10-08T12:00:00Z", "2026-10-08T12:08:21Z", "2026-10-08T12:15:00Z")
        self.assertEqual(result["offset_seconds"], 491)
        self.assertTrue(result["url"].endswith("?t=491"))
        self.assertEqual(result["error_sp"], "08/10/2026 09:08:21")
        self.assertTrue(result["bounds_verified"])

    def test_subsecond_and_start_clamp(self):
        result = lab.replay_link(BASE + "?t=90", "2026-10-08T12:00:00Z", "2026-10-08T09:00:04.900-03:00")
        self.assertEqual(result["offset_seconds"], 0)
        self.assertFalse(result["bounds_verified"])

    def test_bad_bounds_timezone_and_url_rejected(self):
        for base, start, error, end, before in (
            (BASE, "2026-10-08T12:00:00", "2026-10-08T12:00:01Z", None, 10),
            (BASE, "2026-10-08T12:00:00Z", "2026-10-08T11:59:59Z", None, 10),
            (BASE, "2026-10-08T12:00:00Z", "2026-10-08T12:00:05Z", "2026-10-08T12:00:04Z", 10),
            (BASE + "?token=private", "2026-10-08T12:00:00Z", "2026-10-08T12:00:05Z", None, 10),
            (BASE, "2026-10-08T12:00:00Z", "2026-10-08T12:00:05Z", None, float("nan")),
        ):
            with self.subTest(base=base, error=error), self.assertRaises(lab.LabError):
                lab.replay_link(base, start, error, end, before)

    def test_two_windows_preserve_absolute_timestamps_without_input_values(self):
        data = {"w1": [{"type": 2, "timestamp": 1000, "data": {"text": "private"}}], "w2": [{"type": 3, "timestamp": 5000, "data": {"source": 5, "text": "private", "id": 1}}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            path.write_text(json.dumps(data))
            result = lab.replay_summary(path)
        self.assertEqual(result["windows"][1]["first_timestamp_ms"], 5000)
        self.assertFalse(result["visual_review"])
        self.assertNotIn("private", json.dumps(result))


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.config = lab.load_config(SKILL / "config.example.json")

    def test_offline_clean_environment_needs_no_credentials(self):
        with patch.dict(lab.os.environ, {}, clear=True), patch.object(lab.shutil, "which", return_value=None), patch.object(lab, "command", side_effect=AssertionError("network unexpected")):
            result = lab.doctor(self.config, False)
        self.assertFalse(result["live_verified"])
        self.assertFalse(result["infisical_required"])
        self.assertFalse(any(result["tools"].values()))

    def test_failure_of_one_source_does_not_skip_other_sources(self):
        with patch.object(lab, "command", return_value="[]"), patch.object(lab, "clickhouse", side_effect=lab.LabError("blocked")), patch.object(lab, "mysql", return_value={"ok": True}), patch.object(lab, "project_probe", return_value={"id": 331102}):
            result = lab.doctor(self.config, True)
        self.assertEqual(result["checks"]["clickhouse"]["status"], "blocked")
        self.assertEqual(result["checks"]["mysql"]["status"], "ok")
        self.assertEqual(result["checks"]["posthog"]["status"], "ok")
        self.assertFalse(result["live_verified"])

    def test_wrong_posthog_project_rejected(self):
        with patch.object(lab, "posthog", return_value={"id": 1, "api_token": "private"}), self.assertRaises(lab.LabError):
            lab.project_probe(self.config)

    def test_password_injection_does_not_require_gcloud(self):
        with patch.dict(lab.os.environ, {"INCIDENT_CLICKHOUSE_PASSWORD": "private"}, clear=True), patch.object(lab, "command", side_effect=AssertionError("gcloud unexpected")):
            self.assertEqual(lab.secret(self.config), "private")

    def test_mysql_limit_read_only_transaction_and_cleanup(self):
        identity, rows = MagicMock(), MagicMock()
        identity.__enter__.return_value = identity
        rows.__enter__.return_value = rows
        identity.fetchone.return_value = ("agent-read@%",)
        rows.description = [("ok",)]
        rows.fetchmany.return_value = [(1,), (2,), (3,)]
        connection = Mock(open=True)
        connection.cursor.side_effect = [identity, rows]
        driver = SimpleNamespace(connect=Mock(return_value=connection), MySQLError=type("DBError", (Exception,), {}))
        with patch.dict(lab.sys.modules, {"pymysql": driver}), patch.object(lab, "command", return_value="token"), patch.object(lab, "mysql_proxy", return_value=nullcontext(12345)):
            result = lab.mysql(self.config, "SELECT id FROM aura.cart", 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["rows"]), 2)
        rows.execute.assert_called_once_with("SELECT * FROM (SELECT id FROM aura.cart) AS incident_lab_rows LIMIT 3")
        self.assertIn(unittest.mock.call("START TRANSACTION READ ONLY"), identity.execute.call_args_list)
        self.assertEqual(driver.connect.call_args.kwargs["host"], "127.0.0.1")
        connection.close.assert_called_once()

    def test_mysql_identity_mismatch_stops_before_business_query(self):
        identity = MagicMock()
        identity.__enter__.return_value = identity
        identity.fetchone.return_value = ("admin@%",)
        connection = Mock(open=True)
        connection.cursor.return_value = identity
        driver = SimpleNamespace(connect=Mock(return_value=connection), MySQLError=type("DBError", (Exception,), {}))
        with patch.dict(lab.sys.modules, {"pymysql": driver}), patch.object(lab, "command", return_value="token"), patch.object(lab, "mysql_proxy", return_value=nullcontext(12345)), self.assertRaises(lab.LabError):
            lab.mysql(self.config, "SELECT id FROM aura.cart", 2)
        self.assertEqual(identity.execute.call_count, 1)
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
