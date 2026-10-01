"""Verificar fronteira de comandos, cofre e especificação curada."""
import copy
import os
import unittest
from unittest.mock import patch
import subprocess
import restish_bridge as bridge


class BridgeTests(unittest.TestCase):
    def test_full_help_requires_neither_vault_nor_api_authentication(self):
        result = subprocess.CompletedProcess([], 0, stdout=b'help', stderr=b'')
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(bridge.subprocess, 'run', return_value=result) as run, \
             patch.object(bridge, 'https_json') as connection, \
             patch.object(bridge.sys, 'stdout'):
            for args in (['--help-all'], ['investments-list', '--help-all']):
                self.assertEqual(bridge.main(args), 0)
                self.assertTrue(run.call_args.args[0][0].endswith('/restish'))
            connection.assert_not_called()

    def test_reject_secret_output_host_override_and_mutations(self):
        for args in (["post"], ["loans-list"], ["accounts-list", "x", "-v"],
                     ["accounts-list", "x", "--rsh-server=https://other.example"],
                     ["accounts-list", "x", "--rsh-print", "H"],
                     ["accounts-list", "x", "--rsh-insecure"],
                     ["accounts-list", "x", "--rsh-ignore-status-code"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                bridge.validate(args)

    def test_keep_filters_and_financial_parameters(self):
        bridge.validate(["transactions-list-by-cursor", "x", "--date-from", "2026-09-01",
                         "--rsh-filter-lang=jq", "-f", ".body.results | length"])

    def test_environment_drops_ambient_secrets_and_restish_overrides(self):
        with patch.dict(os.environ, {"PLUGGY_API_KEY": "fixture", "INFISICAL_TOKEN": "fixture",
                                    "RSH_SERVER": "other", "SSLKEYLOGFILE": "/unused",
                                    "PATH": "/bin"}, clear=True):
            self.assertEqual(bridge.clean_env(), {"PATH": "/bin"})

    def test_curated_spec_only_selected_gets_and_no_origin_override(self):
        spec = {"servers": [{"url": "https://other.example"}], "paths": {
            path: {"get": {"operationId": "original", "servers": [{"url": "https://other.example"}],
                           "x-cli-config": {"auth": "external-tool"}}, "delete": {}}
            for path in bridge.OPERATIONS}}
        spec["paths"]["/loans"] = {"get": {}}
        original = copy.deepcopy(spec)
        result = bridge.curate(spec)
        self.assertEqual(set(result["paths"]), set(bridge.OPERATIONS))
        for entry in result["paths"].values():
            self.assertEqual(set(entry), {"get"})
            self.assertNotIn("servers", entry["get"])
            self.assertNotIn("x-cli-config", entry["get"])
        self.assertEqual(spec, original)

    def test_warning_discards_partial_financial_output(self):
        result = subprocess.CompletedProcess([], 0, stdout=b'private financial records',
                                             stderr=b'pagination warning')
        with patch.object(bridge.subprocess, 'run', return_value=result), \
             patch.object(bridge.sys, 'stdout') as output:
            self.assertEqual(bridge.main(['accounts-list', 'x', '--help']), 0)
            output.buffer.write.assert_called_once()
        with patch.object(bridge.subprocess, 'run', return_value=result), \
             patch.object(bridge, 'https_json', return_value={'apiKey': 'fixture'}), \
             patch.dict(os.environ, {'PLUGGY_CLIENT_ID': 'fixture',
                                     'PLUGGY_CLIENT_SECRET': 'fixture'}, clear=True), \
             patch.object(bridge.sys, 'stdout') as output, \
             patch.object(bridge.sys, 'stderr'):
            self.assertEqual(bridge.main(['--injected', 'accounts-list', 'x']), 1)
            output.buffer.write.assert_not_called()

    def test_paged_default_and_token_transport(self):
        with patch.object(bridge.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, stdout=b'{}', stderr=b'')) as run, \
             patch.object(bridge, 'https_json', return_value={'apiKey': 'fixture-token'}), \
             patch.dict(os.environ, {'PLUGGY_CLIENT_ID': 'fixture-client',
                                     'PLUGGY_CLIENT_SECRET': 'fixture-secret',
                                     'PLUGGY_ITEM_ID': 'fixture-item'}, clear=True), \
             patch.object(bridge.sys, 'stdout'):
            self.assertEqual(bridge.main(['--injected', 'investments-list', '@item']), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[-2:], ['--page', '1'])
            self.assertIn('fixture-item', command)
            self.assertNotIn('fixture-token', command)
            self.assertEqual(run.call_args.kwargs['env']['PLUGGY_API_KEY'], 'fixture-token')
            self.assertNotIn('PLUGGY_CLIENT_SECRET', run.call_args.kwargs['env'])


if __name__ == "__main__":
    unittest.main()
