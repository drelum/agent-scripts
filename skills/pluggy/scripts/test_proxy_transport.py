"""Regressões CONNECT/TLS com curl real, proxy local e certificado de teste."""
import json
import os
from pathlib import Path
import select
import shutil
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import restish_bridge as bridge


@unittest.skipUnless(shutil.which('curl') and shutil.which('openssl'), 'Requer curl e openssl')
class ProxyTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bridge.STATE.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix='proxy-test-', dir=bridge.STATE)
        cls.fixture = Path(cls.temp.name)
        cls.cert = cls.fixture / 'cert.pem'
        key = cls.fixture / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cls.cert), '-days', '1',
                        '-subj', '/CN=proxy-test.invalid',
                        '-addext', 'subjectAltName=DNS:proxy-test.invalid'],
                       check=True, capture_output=True)
        # Deve ser ignorado: uma configuração do usuário não pode desligar TLS.
        (cls.fixture / '.curlrc').write_text('insecure\n')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.requests = []
        self.connects = []
        received = self.requests

        class Origin(BaseHTTPRequestHandler):
            def respond(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                received.append((self.command, self.path, body))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            do_GET = respond
            do_POST = respond

            def log_message(self, *_):
                pass

        self.origin = ThreadingHTTPServer(('127.0.0.1', 0), Origin)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, self.fixture / 'key.pem')
        self.origin.socket = context.wrap_socket(self.origin.socket, server_side=True)
        upstream = self.origin.server_address
        connects = self.connects

        class Tunnel(socketserver.StreamRequestHandler):
            def handle(self):
                connects.append(self.rfile.readline().decode().strip())
                while self.rfile.readline() not in (b'\r\n', b'\n', b''):
                    pass
                with socket.create_connection(upstream, timeout=5) as target:
                    self.wfile.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
                    self.wfile.flush()
                    while True:
                        ready, _, _ = select.select([self.connection, target], [], [], 5)
                        if not ready:
                            return
                        for source in ready:
                            data = source.recv(65536)
                            if not data:
                                return
                            (target if source is self.connection else self.connection).sendall(data)

        class Proxy(socketserver.ThreadingTCPServer):
            daemon_threads = True

            def handle_error(self, *_):
                pass  # Handshake TLS rejeitado pelo cliente é esperado nos testes.

        self.proxy = Proxy(('127.0.0.1', 0), Tunnel)
        self.threads = []
        for server in (self.origin, self.proxy):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.environment = {
            'PATH': os.environ['PATH'],
            'HTTPS_PROXY': f'http://127.0.0.1:{self.proxy.server_address[1]}',
            'NO_PROXY': '', 'CURL_HOME': str(self.fixture),
        }

    def tearDown(self):
        for server in (self.origin, self.proxy):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=5)

    def test_proxy_resolves_destination_and_tunnels_verified_tls_get_and_post(self):
        payload = {'clientId': 'fixture-client', 'clientSecret': 'fixture-secret'}
        with patch.dict(os.environ, dict(self.environment, CURL_CA_BUNDLE=str(self.cert)), clear=True):
            self.assertEqual(bridge.https_json('https://proxy-test.invalid/spec'), {'ok': True})
            self.assertEqual(bridge.https_json('https://proxy-test.invalid/auth', payload), {'ok': True})
        self.assertEqual(self.connects, ['CONNECT proxy-test.invalid:443 HTTP/1.1'] * 2)
        self.assertEqual(self.requests[0], ('GET', '/spec', b''))
        self.assertEqual(self.requests[1][:2], ('POST', '/auth'))
        self.assertEqual(json.loads(self.requests[1][2]), payload)

    def test_untrusted_tls_fails_even_with_insecure_in_curlrc(self):
        with patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, r'curl 60'):
                bridge.https_json('https://proxy-test.invalid/auth', {'clientSecret': 'fixture-secret'})
        self.assertEqual(len(self.connects), 1)
        self.assertEqual(self.requests, [])

    def test_trusted_certificate_still_requires_correct_hostname(self):
        with patch.dict(os.environ, dict(self.environment, CURL_CA_BUNDLE=str(self.cert)), clear=True):
            with self.assertRaisesRegex(RuntimeError, r'curl 60'):
                bridge.https_json('https://wrong-host.invalid/auth', {'clientSecret': 'fixture-secret'})
        self.assertEqual(self.connects, ['CONNECT wrong-host.invalid:443 HTTP/1.1'])
        self.assertEqual(self.requests, [])


class MemoryTransportTests(unittest.TestCase):
    def test_secret_payload_only_on_stdin_and_proxy_environment_preserved(self):
        result = subprocess.CompletedProcess([], 0, stdout=b'{"apiKey":"fixture-key"}\n200', stderr=b'')
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://proxy.example:8080',
                                    'PLUGGY_CLIENT_SECRET': 'fixture-secret',
                                    'SSLKEYLOGFILE': '/unused'}, clear=True), \
             patch.object(bridge.subprocess, 'run', return_value=result) as run:
            data = bridge.https_json('https://api.pluggy.ai/auth', {'clientSecret': 'fixture-secret'})
        self.assertEqual(data['apiKey'], 'fixture-key')
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ['curl', '--disable'])
        self.assertNotIn('fixture-secret', command)
        self.assertNotIn('fixture-key', command)
        self.assertEqual(json.loads(run.call_args.kwargs['input']), {'clientSecret': 'fixture-secret'})
        self.assertEqual(run.call_args.kwargs['env'], {'HTTPS_PROXY': 'http://proxy.example:8080'})
        self.assertTrue(run.call_args.kwargs['capture_output'])

    def test_http_and_transport_errors_do_not_expose_bodies_or_stderr(self):
        for code, stdout, stderr in ((0, b'fixture-secret\n401', b''),
                                     (56, b'fixture-key', b'proxy password fixture-secret')):
            with self.subTest(code=code), patch.object(bridge.subprocess, 'run', return_value=
                    subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)):
                with self.assertRaises(RuntimeError) as raised:
                    bridge.https_json('https://api.pluggy.ai/auth', {})
                self.assertNotIn('fixture-secret', str(raised.exception))
                self.assertNotIn('fixture-key', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
