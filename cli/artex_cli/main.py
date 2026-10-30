"""ARTEX CLI: JSON API client with SSH transport and no third-party dependencies."""
import argparse
import base64
import binascii
import contextlib
import getpass
import importlib.resources
import json
import mimetypes
import os
import pathlib
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import __version__
from .commands import COMMANDS


class CLIError(Exception):
    def __init__(self, message, code=1, **details):
        super().__init__(message)
        self.code, self.details = code, details


def emit(value, pretty=False, file=None):
    print(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None),
          file=file or sys.stdout, flush=True)


def routes():
    return json.loads(importlib.resources.files("artex_cli").joinpath("catalog.json").read_text())


def split_pair(value):
    if "=" not in value or not value.split("=", 1)[0]:
        raise CLIError(f"Expected KEY=VALUE: {value}", 2)
    return tuple(value.split("=", 1))


def json_value(value):
    try:
        return json.loads(value)
    except ValueError:
        return value


def config_path(args):
    return pathlib.Path(getattr(args, "config", None) or os.environ.get("ARTEX_CLI_CONFIG") or
                        pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")) / "artex/config.json").expanduser()


def load_config(path):
    if not path.exists():
        return {"profiles": {}}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("profiles", {}), dict):
            raise ValueError("profiles must be an object")
        return data
    except (ValueError, OSError) as exc:
        raise CLIError(f"Invalid CLI config {path}: {exc}", 2) from exc


def save_config(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def config_lock(path):
    """Serialize credential renewal and config edits across CLI processes."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600), "r+b") as lock:
        if os.name == "nt":
            import msvcrt
            if not lock.read(1):
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            acquire = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        deadline = time.monotonic() + 60
        while True:
            try:
                acquire()
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise CLIError("Timed out waiting for CLI config lock") from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            release()


def resolved(args):
    data = load_config(config_path(args))
    name = getattr(args, "profile", None) or os.environ.get("ARTEX_PROFILE") or data.get("current", "default")
    profile = dict(data.get("profiles", {}).get(name, {}))
    original_endpoint = (profile.get("url", "http://127.0.0.1:8787"), profile.get("ssh"))
    for key, env in (("url", "ARTEX_URL"), ("ssh", "ARTEX_SSH"), ("token", "ARTEX_TOKEN")):
        if env in os.environ:
            profile[key] = os.environ[env]
        if hasattr(args, key):
            profile[key] = getattr(args, key)
    profile.setdefault("url", "http://127.0.0.1:8787")
    if "ARTEX_TOKEN" not in os.environ and (profile["url"], profile.get("ssh")) != original_endpoint:
        profile.pop("token", None)
    if (profile["url"], profile.get("ssh")) != original_endpoint:
        profile.pop("key_login", None)
    profile["name"] = name
    return data, profile


def ssh_prefix(host):
    if not host or host.startswith("-") or any(c.isspace() for c in host):
        raise CLIError("--ssh must be one SSH host alias or user@host", 2)
    return ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host]


def validate_url(value):
    url = urllib.parse.urlsplit(value)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise CLIError("URL must be http(s)://host[:port][/prefix], without credentials/query/fragment", 2)
    try:
        _ = url.port
    except ValueError as exc:
        raise CLIError(str(exc), 2) from exc
    return url


@contextlib.contextmanager
def transport(profile):
    url = validate_url(profile["url"])
    if not profile.get("ssh"):
        yield profile["url"].rstrip("/")
        return
    # HTTPS uses its original hostname for certificate validation. An SSH tunnel
    # is already encrypted; use the backend's loopback HTTP listener for SSH.
    if url.scheme != "http":
        raise CLIError("SSH transport expects the remote HTTP listener, e.g. http://127.0.0.1:8787", 2)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    target = url.hostname
    if ":" in target:
        target = f"[{target}]"
    command = ssh_prefix(profile["ssh"])
    command[1:1] = ["-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2", "-L", f"127.0.0.1:{port}:{target}:{url.port or 80}"]
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            deadline = time.monotonic() + 15
            while True:
                if proc.poll() is not None:
                    errors.seek(0)
                    raise CLIError("SSH tunnel failed: " + errors.read().decode(errors="replace").strip())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise CLIError("SSH tunnel did not become ready within 15 seconds")
                    time.sleep(0.05)
            yield f"http://127.0.0.1:{port}{url.path.rstrip('/')}"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward bearer credentials to a redirected origin.


def _open_request(base, path, method, body, content_type, profile, args):
    if not path.startswith("/api/") or "#" in path or "\r" in path or "\n" in path:
        raise CLIError("API path must begin with /api/ and contain no fragment or newlines", 2)
    headers = {"Accept": "application/json", "User-Agent": f"artexctl/{__version__}"}
    if profile.get("token"):
        headers["Authorization"] = "Bearer " + profile["token"]
    if content_type:
        headers["Content-Type"] = content_type
    for pair in getattr(args, "header", []):
        key, value = split_pair(pair)
        headers[key] = value
    if getattr(args, "stream", False):
        headers["Accept"] = "text/event-stream"
    # SSH's local transport must not follow HTTP_PROXY/ALL_PROXY from the caller.
    handlers = [NoRedirect()]
    if profile.get("ssh") or urllib.parse.urlsplit(base).hostname in ("127.0.0.1", "localhost", "::1"):
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    try:
        return opener.open(request, timeout=getattr(args, "timeout", 60))
    except urllib.error.HTTPError as exc:
        with exc:
            message = exc.read(65536).decode("utf-8", errors="replace")
        try:
            message = json.loads(message).get("error", message)
        except (ValueError, AttributeError):
            pass
        # These two responses come from requireAuth before dispatching a handler.
        # Other 401s (e.g. wrong password) must never replay a business request.
        auth_rejected = exc.code == 401 and message in ("未授权", "token 无效或已过期")
        if exc.code == 401:
            message = f"{message}; run auth login or auth key-login to renew credentials"
        error = CLIError(str(message), 3 if exc.code in (401, 403) else 4,
                         status=exc.code, method=method, path=path)
        error.auth_rejected = auth_rejected
        raise error from exc


def open_request(base, path, method, body, content_type, profile, args):
    if not path.startswith("/api/") or "#" in path or "\r" in path or "\n" in path:
        raise CLIError("API path must begin with /api/ and contain no fragment or newlines", 2)
    resource = urllib.parse.urlsplit(path).path
    renewable = (bool(profile.get("key_login")) and "ARTEX_TOKEN" not in os.environ
                 and args.group != "auth" and resource != "/api/health"
                 and not resource.startswith("/api/auth/")
                 and not any(split_pair(pair)[0].lower() == "authorization"
                             for pair in getattr(args, "header", [])))
    if renewable and token_needs_renewal(profile):
        renew_credentials(base, profile, args)
    position = body.tell() if renewable and hasattr(body, "tell") else None
    try:
        return _open_request(base, path, method, body, content_type, profile, args)
    except CLIError as exc:
        if not renewable or not getattr(exc, "auth_rejected", False):
            raise
        renew_credentials(base, profile, args, rejected_token=profile.get("token"))
        if position is not None:
            body.seek(position)
        # Exactly one retry after a definite pre-dispatch rejection; never retry
        # a timeout, transport failure, 403, or a response already being consumed.
        return _open_request(base, path, method, body, content_type, profile, args)


@contextlib.contextmanager
def multipart(forms):
    boundary = "artex-" + uuid.uuid4().hex
    with tempfile.TemporaryFile() as body:
        for pair in forms:
            key, value = split_pair(pair)
            if any(c in key for c in '\r\n"'):
                raise CLIError("Invalid multipart field name", 2)
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"".encode())
            if value.startswith("@"):
                path = pathlib.Path(value[1:]).expanduser()
                name = path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
                mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                body.write(f'; filename="{name}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
                with path.open("rb") as source:
                    shutil.copyfileobj(source, body)
            else:
                body.write(b"\r\n\r\n" + value.encode())
            body.write(b"\r\n")
        body.write(f"--{boundary}--\r\n".encode())
        length = body.tell()
        body.seek(0)
        yield body, f"multipart/form-data; boundary={boundary}", length


def stream_events(response, args):
    count, fields, data = 0, {}, []
    duration = getattr(args, "duration", 0)
    timer = None
    expired = threading.Event()
    if duration:
        def stop():
            expired.set()
            # Shutdown interrupts a blocked readline, including a silent stream.
            try:
                response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
            except (AttributeError, OSError):
                response.close()
        timer = threading.Timer(duration, stop)
        timer.daemon = True
        timer.start()
    try:
        while not expired.is_set():
            raw = response.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                if data:
                    payload = "\n".join(data)
                    emit({**fields, "event": fields.get("event", "message"), "data": json_value(payload)})
                    count += 1
                    if getattr(args, "max_events", 0) and count >= args.max_events:
                        break
                fields, data = {}, []
            elif not line.startswith(":"):
                key, _, value = line.partition(":")
                value = value.removeprefix(" ")
                if key == "data":
                    data.append(value)
                elif key in ("id", "event", "retry"):
                    fields[key] = value
    except (OSError, ValueError):
        if not expired.is_set():
            raise
    finally:
        if timer:
            timer.cancel()


def read_response(response, args):
    if "text/event-stream" in response.headers.get("Content-Type", ""):
        if getattr(args, "output", None):
            raise CLIError("SSE emits NDJSON on stdout; redirect stdout to save it", 2)
        stream_events(response, args)
        return
    output = getattr(args, "output", None)
    if output and output != "-":
        dest = pathlib.Path(output).expanduser()
        fd, tmp = tempfile.mkstemp(prefix="." + dest.name + "-", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as file:
                shutil.copyfileobj(response, file)
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        emit({"saved": str(dest.resolve())})
        return
    content = response.read()
    if not content:
        emit(None)
    elif output == "-" or getattr(args, "format", "json") == "raw":
        sys.stdout.buffer.write(content)
        sys.stdout.buffer.flush()
    elif "json" in response.headers.get("Content-Type", ""):
        emit(json.loads(content), getattr(args, "format", "json") == "pretty")
    elif response.headers.get("Content-Type", "").startswith("text/"):
        sys.stdout.write(content.decode("utf-8"))
        sys.stdout.flush()
    else:
        raise CLIError("Binary response: save with --output PATH or --output -", 2)


def common_parser():
    parser = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    for name, help_text in (("profile", "Connection profile"), ("config", "CLI config path"), ("url", "Backend URL (remote URL with --ssh)"), ("ssh", "SSH host alias, e.g. myvps")):
        parser.add_argument("--" + name, help=help_text)
    parser.add_argument("--timeout", type=float, help="Socket timeout in seconds (default 60; 0 is invalid)")
    parser.add_argument("--format", choices=("json", "pretty", "raw"), help="Response format (default json)")
    parser.add_argument("-o", "--output", help="Save response bytes atomically; - writes bytes to stdout")
    for short, name, help_text in (("-q", "query", "Query KEY=VALUE (repeatable)"), ("-s", "set", "JSON body KEY=VALUE; parses JSON scalars/arrays"), ("-F", "form", "Multipart KEY=@file or KEY=value (repeatable)"), ("-H", "header", "HTTP header KEY=VALUE (repeatable)")):
        parser.add_argument(short, "--" + name, action="append", help=help_text)
    parser.add_argument("-d", "--data", help="JSON object, @file.json, or - for stdin")
    parser.add_argument("--body-file", help="Raw request body file (for raw API extensions)")
    parser.add_argument("--content-type", help="Raw request content type")
    parser.add_argument("--stream", action="store_true", help="Request SSE; events become NDJSON")
    parser.add_argument("--max-events", type=int, help="Stop SSE after this many data events")
    parser.add_argument("--duration", type=float, help="Stop SSE after this many seconds, even if idle")
    parser.add_argument("--dry-run", action="store_true", help="Print request without connecting or mutating")
    for name in ("task", "limit", "page", "size", "severity", "status", "search"):
        parser.add_argument("--" + name, help="Query filter" if name not in ("severity", "status") else "Query filter; JSON field on writes")
    for name in ("name", "description", "goal", "message", "text", "kind", "value", "reason", "notes", "decision", "action", "agent-key", "title", "request-id"):
        parser.add_argument("--" + name, help="JSON body field")
    for name in ("llm-profile-id", "company-id"):
        parser.add_argument("--" + name, type=int, action="append", help="Repeatable numeric ID")
    parser.add_argument("--content-file", help="Read UTF-8 file into JSON content field")
    parser.add_argument("--export-format", choices=("md-single", "md-zip", "csv", "json"), help="Findings export format")
    return parser


def make_parser():
    common = common_parser()
    parser = argparse.ArgumentParser(prog="artexctl", parents=[common], description="ARTEX remote CLI · JSON stdout, errors on stderr; Python 3.10+")
    parser.add_argument("--version", action="version", version=f"artexctl {__version__}")
    subs = parser.add_subparsers(dest="group", required=True)
    for group, path in (("health", "/api/health"), ("stats", "/api/stats"), ("audit", "/api/audit")):
        leaf = subs.add_parser(group, parents=[common])
        leaf.set_defaults(spec=("GET", path, {}, {}))
    grouped = {}
    for group, verb, method, path, body, query in COMMANDS:
        if group not in grouped:
            grouped[group] = subs.add_parser(group).add_subparsers(dest="verb", required=True)
        leaf = grouped[group].add_parser(verb, parents=[common], description=f"{method} {path}")
        for param in re.findall(r"\{([^}]+)\}", path):
            key = param.removesuffix("...")
            leaf.add_argument("path_" + key, metavar=key)
        leaf.set_defaults(spec=(method, path, body, query))
    wait = grouped["tasks"].add_parser("wait", parents=[common], description="Poll a task until terminal; paused/queued remain waiting")
    wait.add_argument("id")
    wait.add_argument("--interval", type=float, default=3)
    wait.add_argument("--wait-timeout", type=float, default=600)
    api = subs.add_parser("api").add_subparsers(dest="verb", required=True)
    listing = api.add_parser("list", parents=[common], help="List all backend operations")
    listing.add_argument("filter", nargs="?", default="")
    describe = api.add_parser("describe", parents=[common])
    describe.add_argument("operation")
    call = api.add_parser("call", parents=[common])
    call.add_argument("operation")
    call.add_argument("--path", action="append", default=[], metavar="KEY=VALUE")
    request = api.add_parser("request", parents=[common], help="Call a raw API path, including newer server extensions")
    request.add_argument("method", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    request.add_argument("path")
    auth = subs.add_parser("auth").add_subparsers(dest="verb", required=True)
    for verb in ("status", "login", "init", "logout", "key-login", "change-password"):
        leaf = auth.add_parser(verb, parents=[common])
        if verb in ("login", "init", "change-password"):
            leaf.add_argument("--password-stdin", action="store_true", help="Read password from stdin (old/new on separate lines for change-password)")
        if verb == "login":
            leaf.add_argument("--username", default="ARTEX")
        if verb == "key-login":
            leaf.add_argument("--key-file", required=True, help="Server JWT key path, read on --ssh host; key never leaves server")
            leaf.add_argument("--ttl", type=int, default=86400, help="Token lifetime, 60..604800 seconds (default 1 day)")
            leaf.add_argument("--no-auto-renew", action="store_true", help="Do not remember this key-login method for automatic renewal")
    profile = subs.add_parser("profile").add_subparsers(dest="verb", required=True)
    for verb in ("list", "set", "use", "delete"):
        leaf = profile.add_parser(verb, parents=[common])
        if verb != "list":
            leaf.add_argument("profile_name")
    return parser


def build_request(args):
    supplied = {}
    if args.group == "api":
        if args.verb == "request":
            method, path, fixed, query = args.method, args.path, {}, {}
        else:
            operation = next((r for r in routes() if r["operation"] == args.operation), None)
            if operation is None:
                raise CLIError("Unknown operation; use api list", 2)
            method, path, fixed, query = operation["method"], operation["path"], {}, {}
            supplied = dict(split_pair(p) for p in args.path)
            required = {p.removesuffix("...") for p in re.findall(r"\{([^}]+)\}", path)}
            if set(supplied) != required:
                raise CLIError(f"--path keys must be exactly: {', '.join(sorted(required)) or '(none)'}", 2)
    else:
        method, path, fixed, query = args.spec
        supplied = {param.removesuffix("..."): getattr(args, "path_" + param.removesuffix("..."))
                    for param in re.findall(r"\{([^}]+)\}", path)}
    for param in re.findall(r"\{([^}]+)\}", path):
        value = str(supplied[param.removesuffix("...")])
        if not value or value in (".", ".."):
            raise CLIError("Path parameters must be nonempty and cannot be . or ..", 2)
        path = path.replace("{" + param + "}", urllib.parse.quote(value, safe="/" if param.endswith("...") else ""))
    pairs = list(urllib.parse.parse_qsl(urllib.parse.urlsplit(path).query, keep_blank_values=True))
    path = urllib.parse.urlsplit(path).path
    query = dict(query)
    for key in ("task", "limit", "page", "size", "search"):
        if hasattr(args, key):
            target = "q" if key == "search" else key
            if key == "task" and path.startswith("/api/exploration/findings"):
                target = "task_id"
            query[target] = getattr(args, key)
    for key in ("status", "severity"):
        if hasattr(args, key) and method == "GET":
            query[key] = getattr(args, key)
    if hasattr(args, "export_format"):
        query["format"] = args.export_format
    # Explicit -q overrides both convenience flags and command defaults.
    extra = [split_pair(p) for p in getattr(args, "query", [])]
    overridden = {p[0] for p in extra}
    # The flat findings endpoint applies filters only in its paginated branch;
    # without page/limit it serves an unfiltered summary array that silently
    # drops task_id/severity/status. Default the page size so filters work.
    if (method == "GET" and path == "/api/exploration/findings"
            and not {"page", "limit"} & (query.keys() | overridden)
            and {"task_id", "severity", "status", "vulnclass", "q", "sort", "asset_scope"} & (query.keys() | overridden)):
        query["limit"] = 200
    pairs = [(k, v) for k, v in pairs if k not in query and k not in overridden]
    pairs.extend((k, v) for k, v in query.items() if k not in overridden)
    pairs.extend(extra)
    if pairs:
        path += "?" + urllib.parse.urlencode(pairs)
    data = {}
    if hasattr(args, "data"):
        source = args.data
        raw = sys.stdin.read() if source == "-" else pathlib.Path(source[1:]).expanduser().read_text() if source.startswith("@") else source
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise CLIError("JSON body must be an object", 2)
    for key in ("name", "description", "goal", "message", "text", "kind", "value", "reason", "notes", "decision", "action", "agent_key", "title", "request_id"):
        if hasattr(args, key):
            data[key] = getattr(args, key)
    for key in ("status", "severity"):
        if hasattr(args, key) and method != "GET":
            data[key] = getattr(args, key)
    if hasattr(args, "company_id"):
        data["company_ids"] = args.company_id
    if hasattr(args, "llm_profile_id"):
        if path.startswith("/api/conversations"):
            if len(args.llm_profile_id) != 1:
                raise CLIError("Conversations accept one --llm-profile-id", 2)
            data["llm_profile_id"] = args.llm_profile_id[0]
        else:
            data["llm_profile_ids"] = args.llm_profile_id
    if hasattr(args, "content_file"):
        data["content"] = pathlib.Path(args.content_file).expanduser().read_text()
    for pair in getattr(args, "set", []):
        key, value = split_pair(pair)
        data[key] = json_value(value)
    # Semantic commands such as pause/deny always retain their named action.
    data.update(fixed)
    if args.group == "intents" and args.verb == "message":
        data.setdefault("request_id", str(uuid.uuid4()))
    if method == "GET" and data:
        raise CLIError("GET does not accept a JSON body; use --query KEY=VALUE", 2)
    if sum((bool(getattr(args, "form", None)), bool(getattr(args, "body_file", None)), bool(data) or hasattr(args, "data"))) > 1:
        raise CLIError("Choose JSON, --form, or --body-file", 2)
    return method, path, data


def run_request(args, profile):
    method, path, data = build_request(args)
    if getattr(args, "dry_run", False):
        emit({"method": method, "path": path, "body": data or None, "upload": getattr(args, "form", []),
              "body_file": getattr(args, "body_file", None), "url": profile["url"], "ssh": profile.get("ssh")})
        return
    with contextlib.ExitStack() as stack:
        content_type, body = None, None
        if getattr(args, "form", None):
            body, content_type, length = stack.enter_context(multipart(args.form))
            args.header = [*getattr(args, "header", []), f"Content-Length={length}"]
        elif getattr(args, "body_file", None):
            body = stack.enter_context(open(pathlib.Path(args.body_file).expanduser(), "rb"))
            content_type = getattr(args, "content_type", "text/plain; charset=utf-8")
            args.header = [*getattr(args, "header", []), f"Content-Length={os.fstat(body.fileno()).st_size}"]
        elif data or hasattr(args, "data") or method in ("POST", "PUT", "PATCH"):
            body, content_type = json.dumps(data, ensure_ascii=False).encode(), "application/json"
        base = stack.enter_context(transport(profile))
        response = stack.enter_context(open_request(base, path, method, body, content_type, profile, args))
        read_response(response, args)


# Sign on the server, returning only a time-limited token. This is an explicit
# operator login for users who already control the backend's JWT key file.
KEY_LOGIN_SCRIPT = '''import base64,hashlib,hmac,json,pathlib,sys,time
cfg=json.load(sys.stdin)
key=pathlib.Path(cfg["key_file"]).expanduser().read_bytes().strip()
if len(key)<32: raise SystemExit("JWT key must contain at least 32 bytes")
def enc(x): return base64.urlsafe_b64encode(x).rstrip(b"=")
now=int(time.time())
head=enc(b'{"alg":"HS256","typ":"JWT"}')
payload=enc(json.dumps({"sub":"ARTEX","iat":now,"exp":now+cfg["ttl"]},separators=(",",":")).encode())
message=head+b"."+payload
print((message+b"."+enc(hmac.new(key,message,hashlib.sha256).digest())).decode())
'''


def key_login_token(profile, settings):
    if not isinstance(settings, dict):
        raise CLIError("Invalid key-login configuration", 2)
    key_file, ttl = settings.get("key_file"), settings.get("ttl", 86400)
    if not isinstance(key_file, str) or not key_file or not isinstance(ttl, int) or not 60 <= ttl <= 604800:
        raise CLIError("Key login requires a key file and --ttl between 60 and 604800 seconds", 2)
    cmd = [sys.executable, "-c", KEY_LOGIN_SCRIPT]
    if profile.get("ssh"):
        cmd = ssh_prefix(profile["ssh"]) + ["python3 -c " + shlex.quote(KEY_LOGIN_SCRIPT)]
    result = subprocess.run(cmd, input=json.dumps({"key_file": key_file, "ttl": ttl}),
                            text=True, capture_output=True, timeout=20)
    if result.returncode:
        raise CLIError("Key login failed: " + result.stderr.strip())
    if not result.stdout.strip():
        raise CLIError("Key login returned no token", 3)
    return result.stdout.strip()


def token_needs_renewal(profile):
    # Decode only to schedule renewal, never to decide whether a token is valid.
    # The backend validates the signature before any refreshed token is saved.
    try:
        part = profile["token"].split(".")[1]
        expiry = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))["exp"]
        margin = min(300, profile["key_login"].get("ttl", 86400) / 10)
        return not isinstance(expiry, (int, float)) or not expiry > time.time() + margin
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, binascii.Error):
        return True


def verify_credentials(base, profile, args):
    # Do not forward upload Content-Length, custom headers, or SSE options to
    # the authentication probe, which has no request body.
    probe_args = argparse.Namespace(timeout=getattr(args, "timeout", 60))
    with _open_request(base, "/api/tasks?size=1", "GET", None, None, profile, probe_args) as response:
        response.read()


def renew_credentials(base, profile, args, rejected_token=None):
    with config_lock(config_path(args)):
        data = load_config(config_path(args))
        current = dict(data.get("profiles", {}).get(profile["name"], {}))
        if (current.get("url", "http://127.0.0.1:8787"), current.get("ssh"), current.get("key_login")) != (
                profile["url"], profile.get("ssh"), profile.get("key_login")):
            raise CLIError("Connection or login settings changed; rerun the command", 3)
        rejected = rejected_token is not None and current.get("token") == rejected_token
        if rejected or token_needs_renewal(current):
            candidate = {**current, "token": key_login_token(current, current["key_login"])}
            verify_credentials(base, candidate, args)
            data["profiles"][profile["name"]] = candidate
            save_config(config_path(args), data)
            current = candidate
        profile["token"] = current["token"]


def auth(args, data, profile):
    name = profile["name"]
    if getattr(args, "dry_run", False):
        emit({"auth": args.verb, "profile": name, "url": profile["url"], "ssh": profile.get("ssh")})
        return
    if args.verb == "logout":
        with config_lock(config_path(args)):
            data = load_config(config_path(args))
            saved = data.setdefault("profiles", {}).setdefault(name, {})
            saved.pop("token", None)
            saved.pop("key_login", None)
            save_config(config_path(args), data)
        emit({"profile": name, "logged_out": True})
        return
    token = None
    profile.pop("key_login", None)
    if args.verb == "key-login":
        key_file = args.key_file if profile.get("ssh") else str(pathlib.Path(args.key_file).expanduser().resolve())
        settings = {"key_file": key_file, "ttl": args.ttl}
        token = key_login_token(profile, settings)
        if not getattr(args, "no_auto_renew", False):
            profile["key_login"] = settings
    else:
        path = {"status": "/api/auth/status", "login": "/api/auth/login", "init": "/api/auth/init", "change-password": "/api/auth/change-password"}[args.verb]
        request = {}
        if args.verb != "status":
            def password(prompt):
                if args.password_stdin:
                    return sys.stdin.readline().rstrip("\r\n")
                if not sys.stdin.isatty():
                    raise CLIError("Use --password-stdin in noninteractive sessions", 2)
                return getpass.getpass(prompt)
            if args.verb == "change-password":
                request = {"old_password": password("Current password: "), "new_password": password("New password: ")}
            else:
                request = {"password": password("Password: ")}
                if args.verb == "login":
                    request["username"] = args.username
            if not all(request.values()):
                raise CLIError("Password must not be empty", 2)
        with transport(profile) as base:
            with open_request(base, path, "GET" if args.verb == "status" else "POST", json.dumps(request).encode() if request else None,
                              "application/json" if request else None, profile, args) as response:
                result = json.load(response)
        if args.verb == "status":
            emit(result)
            return
        token = result.get("token")
    if not token:
        raise CLIError("Server did not return a token")
    # Verify a protected read before persisting credentials (also detects key mismatch).
    profile["token"] = token
    with transport(profile) as base:
        verify_credentials(base, profile, args)
    with config_lock(config_path(args)):
        data = load_config(config_path(args))
        data.setdefault("profiles", {})[name] = {k: v for k, v in profile.items() if k != "name"}
        data.setdefault("current", name)
        save_config(config_path(args), data)
    emit({"profile": name, "authenticated": True, "config": str(config_path(args))})


def wait_task(args, profile):
    if args.interval <= 0 or args.wait_timeout <= 0:
        raise CLIError("--interval and --wait-timeout must be positive", 2)
    deadline = time.monotonic() + args.wait_timeout
    path = "/api/tasks/" + urllib.parse.quote(args.id, safe="")
    if getattr(args, "dry_run", False):
        emit({"method": "GET", "path": path, "wait_timeout": args.wait_timeout})
        return
    with transport(profile) as base:
        while True:
            with open_request(base, path, "GET", None, None, profile, args) as response:
                task = json.load(response)
            if task.get("status") in ("done", "failed"):
                emit(task)
                if task["status"] == "failed":
                    raise CLIError("Task finished with failed status", 5, task_id=args.id)
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CLIError("Task wait timed out", 6, task_id=args.id, status=task.get("status"))
            time.sleep(min(args.interval, remaining))


def run(args):
    if getattr(args, "timeout", 60) <= 0 or getattr(args, "duration", 0) < 0 or getattr(args, "max_events", 0) < 0:
        raise CLIError("Timeout must be positive; duration/max-events must be nonnegative", 2)
    if args.group == "api" and args.verb in ("list", "describe"):
        catalog = routes()
        if args.verb == "list":
            emit([r for r in catalog if args.filter.lower() in json.dumps(r).lower()], getattr(args, "format", "json") == "pretty")
        else:
            operation = next((r for r in catalog if r["operation"] == args.operation), None)
            if operation is None:
                raise CLIError("Unknown operation; use api list", 2)
            emit(operation, True)
        return
    data, profile = resolved(args)
    if args.group == "profile":
        if args.verb == "list":
            emit({"current": data.get("current", "default"), "profiles": {k: {**{x: y for x, y in v.items() if x != "token"}, "authenticated": bool(v.get("token"))} for k, v in data.get("profiles", {}).items()}})
            return
        name = args.profile_name
        # Dry runs stay entirely read-only, including the lock file.
        lock = contextlib.nullcontext() if getattr(args, "dry_run", False) else config_lock(config_path(args))
        with lock:
            data = load_config(config_path(args))
            if args.verb == "set":
                old = data.setdefault("profiles", {}).get(name, {})
                updated = {**old, **{k: getattr(args, k) for k in ("url", "ssh") if hasattr(args, k)}}
                validate_url(updated.get("url", "http://127.0.0.1:8787"))
                if any(updated.get(k) != old.get(k) for k in ("url", "ssh")):
                    updated.pop("token", None)  # Do not carry credentials to another endpoint.
                    updated.pop("key_login", None)
                data["profiles"][name] = updated
            elif args.verb == "use":
                if name not in data.get("profiles", {}):
                    raise CLIError("Profile does not exist", 2)
                data["current"] = name
            else:
                data.get("profiles", {}).pop(name, None)
                if data.get("current") == name:
                    data.pop("current", None)
            if not getattr(args, "dry_run", False):
                save_config(config_path(args), data)
        emit({"profile": name, "action": args.verb, "dry_run": getattr(args, "dry_run", False)})
    elif args.group == "auth":
        auth(args, data, profile)
    elif args.group == "tasks" and args.verb == "wait":
        wait_task(args, profile)
    else:
        run_request(args, profile)


def main(argv=None):
    try:
        run(make_parser().parse_args(argv))
        return 0
    except CLIError as exc:
        emit({"error": str(exc), **exc.details}, file=sys.stderr)
        return exc.code
    except (ValueError, KeyError) as exc:
        emit({"error": str(exc)}, file=sys.stderr)
        return 2
    except (OSError, urllib.error.URLError, subprocess.SubprocessError) as exc:
        emit({"error": str(exc)}, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def entrypoint():
    raise SystemExit(main())
