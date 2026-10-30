import base64
import hashlib
import hmac
import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli"))
from artex_cli.commands import COMMANDS
from artex_cli.main import routes
from generate_catalog import catalog


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    key = b"test-jwt-key-of-at-least-32-bytes-long"
    records = []
    effects = []

    def log_message(self, *args):
        pass

    def reply(self, content, status=200, mime="application/json"):
        raw = json.dumps(content).encode() if mime == "application/json" else content
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def handle_request(self):
        content = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        Handler.records.append((self.command, self.path, dict(self.headers), content))
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/unauthorized":
            self.reply({"error": "expired"}, 401)
        elif path == "/api/redirect":
            self.send_response(302)
            self.send_header("Location", "/api/secret")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/api/auth/login":
            self.reply({"token": "fixture-token"})
        elif path.startswith("/api/renew/"):
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            valid = False
            try:
                head, payload, signature = token.split(".")
                expected = base64.urlsafe_b64encode(hmac.new(self.key, f"{head}.{payload}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
                claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
                valid = hmac.compare_digest(signature, expected) and claims["exp"] > time.time()
            except (ValueError, KeyError):
                pass
            if not valid or path == "/api/renew/reject":
                self.reply({"error": "token 无效或已过期"}, 401)
            elif path == "/api/renew/forbidden":
                self.reply({"error": "forbidden"}, 403)
            elif path == "/api/renew/failure":
                self.reply({"error": "failed"}, 500)
            elif path == "/api/renew/ambiguous":
                self.reply({"error": "business authentication failed"}, 401)
            else:
                Handler.effects.append((self.command, path, content))
                if path == "/api/renew/timeout":
                    time.sleep(0.3)
                try:
                    self.reply({"ok": True})
                except (BrokenPipeError, ConnectionResetError):
                    pass
        elif path == "/api/tasks":
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            if token and token != "fixture-token":
                head, body, signature = token.split(".")
                expected = base64.urlsafe_b64encode(hmac.new(self.key, f"{head}.{body}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
                if signature != expected:
                    self.reply({"error": "bad signature"}, 401)
                    return
            self.reply({"tasks": [], "active": ""})
        elif path == "/api/tasks/finished":
            self.reply({"id": "finished", "status": "done"})
        elif path == "/api/tasks/failed":
            self.reply({"id": "failed", "status": "failed"})
        elif path == "/api/tasks/paused":
            self.reply({"id": "paused", "status": "paused"})
        elif path == "/api/workspace/download":
            self.reply(bytes(range(256)) * 100, mime="application/octet-stream")
        elif path == "/api/report":
            self.reply("# 中文报告\n".encode(), mime="text/markdown")
        elif path in ("/api/events", "/api/idle"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.flush()
            if path == "/api/idle":
                time.sleep(0.8)
            else:
                try:
                    self.wfile.write(b': ping\n\nid: 9\nevent: activity\ndata: {"a":1}\n\ndata: first\ndata: second\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            self.close_connection = True
        else:
            self.reply({"method": self.command, "path": self.path, "body": json.loads(content) if content.startswith(b"{") else None})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_request


class CLITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = pathlib.Path(self.tmp.name) / "config.json"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("ARTEX_")}
        Handler.records.clear()
        Handler.effects.clear()

    def cli(self, *args, code=0, stdin=None, env=None):
        command = [sys.executable, str(ROOT / "bin/artexctl"), "--config", str(self.config), "--url", self.url, *args]
        result = subprocess.run(command, input=stdin, capture_output=True, env=env or self.env, timeout=8)
        self.assertEqual(result.returncode, code, result.stderr.decode())
        return result

    @unittest.skipUnless((ROOT / "server").is_dir(), "catalog freshness needs the backend source tree")
    def test_catalog_is_current_and_every_alias_exists(self):
        self.assertEqual(routes(), catalog())
        known = {(r["method"], r["path"]) for r in routes()}
        for group, verb, method, path, *_ in COMMANDS:
            self.assertIn((method, path), known, (group, verb))
        self.assertEqual(len({c[:2] for c in COMMANDS}), len(COMMANDS))

    def test_json_errors_and_auth_status(self):
        result = self.cli("api", "request", "GET", "/api/unauthorized", code=3)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(json.loads(result.stderr)["status"], 401)

    def test_task_create_unicode_and_arrays(self):
        self.cli("tasks", "create", "--name", "中文", "--description", "authorized local", "--goal", "fixture",
                 "--llm-profile-id", "2", "--llm-profile-id", "3", "--company-id", "4", "-s", "coverage_enabled=false")
        body = json.loads(Handler.records[-1][3])
        self.assertEqual(body["name"], "中文")
        self.assertEqual(body["llm_profile_ids"], [2, 3])
        self.assertFalse(body["coverage_enabled"])

    def test_task_control_named_semantics(self):
        result = self.cli("tasks", "pause", "7", "--set", "action=resume")
        self.assertEqual(json.loads(result.stdout)["body"], {"action": "pause"})

    def test_task_query_vs_finding_filter(self):
        result = self.cli("findings", "list", "--task", "7", "--severity", "high", "--search", "a&b 中文", "-q", "severity=low")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(json.loads(result.stdout)["path"]).query)
        self.assertEqual(query, {"task_id": ["7"], "severity": ["low"], "q": ["a&b 中文"], "limit": ["200"]})

    def test_findings_filter_defaults_to_paginated_branch(self):
        def query_of(*args):
            result = self.cli("findings", "list", *args)
            return urllib.parse.parse_qs(urllib.parse.urlsplit(json.loads(result.stdout)["path"]).query)
        # Filters without explicit pagination must gain a page size instead of
        # hitting the backend's unfiltered summary branch.
        self.assertEqual(query_of("--task", "7"), {"task_id": ["7"], "limit": ["200"]})
        self.assertEqual(query_of("--severity", "critical"), {"severity": ["critical"], "limit": ["200"]})
        self.assertEqual(query_of("--status", "confirmed"), {"status": ["confirmed"], "limit": ["200"]})
        # User-provided pagination, in either spelling, wins.
        self.assertEqual(query_of("--task", "7", "--limit", "50"), {"task_id": ["7"], "limit": ["50"]})
        self.assertEqual(query_of("--task", "7", "--page", "2"), {"task_id": ["7"], "page": ["2"]})
        self.assertEqual(query_of("--task", "7", "-q", "limit=9"), {"task_id": ["7"], "limit": ["9"]})
        # No filters keeps the summary branch (bare array) untouched.
        self.assertEqual(query_of(), {})
        # Raw `task` param selects the per-task branch, which needs no paging.
        self.assertEqual(query_of("-q", "task=7"), {"task": ["7"]})

    def test_generic_named_operation(self):
        op = next(r["operation"] for r in routes() if r["path"] == "/api/skills/{name}/files/{file...}" and r["method"] == "GET")
        result = self.cli("api", "call", op, "--path", "name=demo", "--path", "file=references/说明.md")
        self.assertIn("/files/references/%E8%AF%B4%E6%98%8E.md", json.loads(result.stdout)["path"])
        self.cli("api", "call", op, "--path", "name=demo", code=2)

    def test_path_params_are_encoded(self):
        result = self.cli("tasks", "get", "a?task=8&x=y", "--dry-run")
        self.assertEqual(json.loads(result.stdout)["path"], "/api/tasks/a%3Ftask%3D8%26x%3Dy")

    def test_body_name_does_not_replace_skill_path_name(self):
        result = self.cli("skills", "meta", "demo", "--name", "new-name", "--dry-run")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["path"], "/api/skills/demo/meta")
        self.assertEqual(payload["body"], {"name": "new-name"})

    def test_json_file_stdin_and_content_file(self):
        path = pathlib.Path(self.tmp.name) / "hello.txt"
        path.write_text("你好\n")
        result = self.cli("workspace", "write", "--data", "-", "--content-file", str(path), stdin=b'{"path":"cli/hello.txt"}')
        self.assertEqual(json.loads(result.stdout)["body"], {"path": "cli/hello.txt", "content": "你好\n"})
        result = self.cli("skills", "write", "demo", "SKILL.md", "--content-file", str(path))
        self.assertEqual(json.loads(result.stdout)["body"], {"content": "你好\n"})

    def test_multipart_unicode_and_binary(self):
        path = pathlib.Path(self.tmp.name) / "样本.bin"
        content = bytes(range(256)) * 4096
        path.write_bytes(content)
        self.cli("workspace", "upload", "-q", "path=cli", "-F", f"file=@{path}", "-F", "note=中文")
        _, _, headers, body = Handler.records[-1]
        self.assertIn(content, body)
        self.assertIn('filename="样本.bin"'.encode(), body)
        self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_raw_file_body(self):
        path = pathlib.Path(self.tmp.name) / "body.bin"
        path.write_bytes(b"\x00test")
        self.cli("api", "request", "PUT", "/api/raw", "--body-file", str(path))
        self.assertEqual(Handler.records[-1][3], b"\x00test")

    def test_explicit_empty_json_on_delete(self):
        self.cli("api", "request", "DELETE", "/api/delete", "--data", "{}")
        self.assertEqual(Handler.records[-1][3], b"{}")
        self.cli("api", "request", "DELETE", "/api/delete", "--data", "{}", "-F", "note=test", code=2)

    def test_download_is_exact_and_failure_preserves_file(self):
        path = pathlib.Path(self.tmp.name) / "download.bin"
        self.cli("workspace", "download", "-q", "path=fixture.bin", "-o", str(path))
        self.assertEqual(path.read_bytes(), bytes(range(256)) * 100)
        self.cli("api", "request", "GET", "/api/unauthorized", "-o", str(path), code=3)
        self.assertEqual(path.read_bytes(), bytes(range(256)) * 100)

    def test_markdown(self):
        self.assertEqual(self.cli("tasks", "report", "--task", "7").stdout.decode(), "# 中文报告\n")

    def test_stream_ndjson_and_event_limit(self):
        result = self.cli("api", "request", "GET", "/api/events", "--stream", "--max-events", "2")
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events, [{"id": "9", "event": "activity", "data": {"a": 1}}, {"event": "message", "data": "first\nsecond"}])
        result = self.cli("api", "request", "GET", "/api/events", "--max-events", "1")
        self.assertEqual(len(result.stdout.splitlines()), 1)

    def test_idle_stream_duration(self):
        start = time.monotonic()
        self.cli("api", "request", "GET", "/api/idle", "--duration", "0.15")
        self.assertLess(time.monotonic() - start, 0.7)

    def test_dry_run_does_not_connect(self):
        result = self.cli("tasks", "create", "--url", "http://127.0.0.1:1", "--ssh", "does-not-exist", "--description", "test", "--dry-run")
        self.assertEqual(json.loads(result.stdout)["body"]["description"], "test")

    def test_login_config_permissions_and_redaction(self):
        result = self.cli("auth", "login", "--password-stdin", stdin=b"private-password\n")
        self.assertNotIn(b"fixture-token", result.stdout)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.config.read_text())["profiles"]["default"]["token"], "fixture-token")
        result = self.cli("profile", "list")
        self.assertNotIn(b"fixture-token", result.stdout)
        self.cli("auth", "logout", "--dry-run")
        self.assertIn("token", json.loads(self.config.read_text())["profiles"]["default"])
        self.cli("auth", "logout")
        self.assertNotIn("token", json.loads(self.config.read_text())["profiles"]["default"])

    def test_local_key_login(self):
        path = pathlib.Path(self.tmp.name) / "jwt.key"
        path.write_bytes(Handler.key)
        self.cli("auth", "key-login", "--key-file", str(path), "--ttl", "120")
        token = json.loads(self.config.read_text())["profiles"]["default"]["token"]
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        self.assertEqual(payload["sub"], "ARTEX")
        self.assertEqual(payload["exp"] - payload["iat"], 120)

    def key_login(self, *args):
        path = pathlib.Path(self.tmp.name) / "jwt.key"
        path.write_bytes(Handler.key)
        self.cli("auth", "key-login", "--key-file", str(path), *args)
        return path

    def expire_token(self, remaining=-1):
        data = json.loads(self.config.read_text())
        token = data["profiles"]["default"]["token"]
        head, payload, _ = token.split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        claims["exp"] = int(time.time()) + remaining
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        signature = base64.urlsafe_b64encode(hmac.new(Handler.key, f"{head}.{payload}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        data["profiles"]["default"]["token"] = f"{head}.{payload}.{signature}"
        self.config.write_text(json.dumps(data))
        return data["profiles"]["default"]["token"]

    def test_expired_token_renews_before_write_and_preserves_profiles(self):
        path = self.key_login()
        expired = self.expire_token()
        data = json.loads(self.config.read_text())
        data["profiles"]["other"] = {"url": "https://example.test", "token": "other-token"}
        self.config.write_text(json.dumps(data))
        Handler.records.clear()
        result = self.cli("api", "request", "POST", "/api/renew/write", "--data", '{"message":"中文"}')
        self.assertEqual(json.loads(result.stdout), {"ok": True})
        self.assertEqual(len(Handler.effects), 1)
        self.assertEqual(json.loads(Handler.effects[0][2]), {"message": "中文"})
        self.assertEqual(sum(r[1] == "/api/renew/write" for r in Handler.records), 1)
        saved = json.loads(self.config.read_text())
        self.assertNotEqual(saved["profiles"]["default"]["token"], expired)
        self.assertEqual(saved["profiles"]["default"]["key_login"]["key_file"], str(path.resolve()))
        self.assertEqual(saved["profiles"]["other"], data["profiles"]["other"])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(saved["profiles"]["default"]["token"].encode(), result.stdout + result.stderr)

    def test_near_expiry_renews_and_fresh_token_is_reused(self):
        key_path = self.key_login()
        near_expiry = self.expire_token(remaining=120)
        self.cli("api", "request", "GET", "/api/renew/read")
        self.assertNotEqual(json.loads(self.config.read_text())["profiles"]["default"]["token"], near_expiry)
        key_path.unlink()
        before = self.config.read_bytes()
        Handler.records.clear()
        self.cli("api", "request", "GET", "/api/renew/read")
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual([r[1] for r in Handler.records], ["/api/renew/read"])

    def test_key_rotation_retries_upload_once_with_complete_body(self):
        key_path = self.key_login()
        self.addCleanup(setattr, Handler, "key", Handler.key)
        Handler.key = b"rotated-test-jwt-key-of-at-least-32-bytes"
        key_path.write_bytes(Handler.key)
        path = pathlib.Path(self.tmp.name) / "样本.bin"
        content = bytes(range(256)) * 1024
        path.write_bytes(content)
        Handler.records.clear()
        self.cli("api", "request", "POST", "/api/renew/upload", "-F", f"file=@{path}")
        attempts = [r for r in Handler.records if r[1] == "/api/renew/upload"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0][3], attempts[1][3])
        self.assertIn(content, attempts[1][3])
        self.assertEqual(len(Handler.effects), 1)

    def test_repeated_401_is_bounded_and_other_failures_do_not_retry(self):
        self.key_login()
        for resource, code, attempts in (("reject", 3, 2), ("forbidden", 3, 1), ("failure", 4, 1), ("ambiguous", 3, 1)):
            with self.subTest(resource=resource):
                Handler.records.clear()
                self.cli("api", "request", "POST", f"/api/renew/{resource}", "--data", "{}", code=code)
                self.assertEqual(sum(r[1] == f"/api/renew/{resource}" for r in Handler.records), attempts)
        Handler.records.clear()
        self.cli("api", "request", "POST", "/api/renew/timeout", "--data", "{}", "--timeout", "0.05", code=1)
        self.assertEqual(sum(r[1] == "/api/renew/timeout" for r in Handler.records), 1)
        self.assertEqual(len(Handler.effects), 1)

    def test_failed_renewal_preserves_credentials_and_does_not_write(self):
        key_path = self.key_login()
        self.expire_token()
        key_path.unlink()
        before = self.config.read_bytes()
        self.cli("api", "request", "POST", "/api/renew/write", "--data", "{}", code=1)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(Handler.effects, [])

    def test_explicit_credentials_do_not_auto_renew(self):
        key_path = self.key_login()
        self.expire_token()
        key_path.unlink()
        before = self.config.read_bytes()
        for options, env in (([], {**self.env, "ARTEX_TOKEN": "external-token"}),
                             (["-H", "Authorization=Bearer explicit-token"], self.env)):
            with self.subTest(options=options):
                self.cli("api", "request", "GET", "/api/renew/read", *options, env=env, code=3)
                self.assertEqual(self.config.read_bytes(), before)

    def test_endpoint_override_does_not_reuse_key_login(self):
        key_path = self.key_login()
        self.expire_token()
        key_path.unlink()
        before = self.config.read_bytes()
        self.cli("api", "request", "GET", "/api/renew/read", "--url", self.url + "/changed", code=0)
        self.assertNotIn("Authorization", Handler.records[-1][2])
        self.assertEqual(self.config.read_bytes(), before)
        self.cli("profile", "set", "default", "--url", self.url + "/changed")
        saved = json.loads(self.config.read_text())["profiles"]["default"]
        self.assertNotIn("key_login", saved)
        self.assertNotIn("token", saved)

    def test_logout_password_login_and_opt_out_disable_renewal(self):
        self.key_login()
        self.cli("auth", "logout")
        saved = json.loads(self.config.read_text())["profiles"]["default"]
        self.assertNotIn("key_login", saved)
        self.assertNotIn("token", saved)
        self.cli("api", "request", "GET", "/api/renew/read", code=3)
        self.key_login()
        self.cli("auth", "login", "--password-stdin", stdin=b"test\n")
        self.assertNotIn("key_login", json.loads(self.config.read_text())["profiles"]["default"])
        self.key_login("--no-auto-renew")
        self.assertNotIn("key_login", json.loads(self.config.read_text())["profiles"]["default"])

    def test_dry_run_and_health_do_not_renew(self):
        key_path = self.key_login()
        self.expire_token()
        key_path.unlink()
        before = self.config.read_bytes()
        self.cli("api", "request", "POST", "/api/renew/write", "--data", "{}", "--dry-run")
        self.cli("health")
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(Handler.effects, [])

    def test_concurrent_commands_share_one_renewal(self):
        self.key_login()
        self.expire_token()
        Handler.records.clear()
        command = [sys.executable, str(ROOT / "bin/artexctl"), "--config", str(self.config),
                   "api", "request", "GET", "/api/renew/read"]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env) for _ in range(4)]
        for proc in processes:
            stdout, stderr = proc.communicate(timeout=8)
            self.assertEqual(proc.returncode, 0, stderr.decode())
            self.assertTrue(json.loads(stdout)["ok"])
        self.assertEqual(len(Handler.effects), 4)
        self.assertEqual(sum(r[1] == "/api/tasks?size=1" for r in Handler.records), 1)

    def test_redirect_does_not_forward_credentials(self):
        self.cli("api", "request", "GET", "/api/redirect", code=4)
        self.assertNotEqual(Handler.records[-1][1], "/api/secret")

    def test_task_wait_success_failure_timeout(self):
        self.cli("tasks", "wait", "finished")
        self.cli("tasks", "wait", "failed", code=5)
        self.cli("tasks", "wait", "paused", "--interval", "0.02", "--wait-timeout", "0.05", code=6)

    def test_invalid_input_and_mutually_exclusive_bodies(self):
        self.cli("tasks", "create", "--data", "[]", code=2)
        self.cli("tasks", "create", "--set", "missing-equals", code=2)
        self.cli("tasks", "create", "--data", "{}", "--message", "test", "-F", "file=@absent", code=2)
        self.cli("health", "--timeout", "0", code=2)
        self.cli("health", "--url", "file:///etc/passwd", code=2)
        self.cli("health", "--ssh=-option", code=2)

    def test_profile_switch_discards_token(self):
        self.cli("auth", "login", "--password-stdin", stdin=b"test\n")
        self.cli("profile", "set", "default", "--url", "http://127.0.0.1:9")
        self.assertNotIn("token", json.loads(self.config.read_text())["profiles"]["default"])


if __name__ == "__main__":
    unittest.main()
