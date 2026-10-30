"""Convenience commands. Every route also remains callable through `api call`."""

# group, verb, method, path; optional fixed JSON body and fixed query values.
COMMANDS = []


def resource(group, path, actions="list create get update delete", update="PATCH", key="id"):
    for verb in actions.split():
        method = dict(list="GET", create="POST", get="GET", update=update, delete="DELETE")[verb]
        suffix = "/{" + key + "}" if verb in ("get", "update", "delete") else ""
        COMMANDS.append((group, verb, method, path + suffix, {}, {}))


def command(group, verb, method, path, body=None, query=None):
    COMMANDS.append((group, verb, method, path, body or {}, query or {}))


resource("tasks", "/api/tasks")
for action in ("pause", "resume"):
    command("tasks", action, "POST", "/api/tasks/{id}/control", {"action": action})
for action in ("coverage", "coverage-graph", "asset-refs", "intent-assets", "scope", "goals", "constraints", "intercept-rules"):
    command("tasks", action, "GET", "/api/tasks/{id}/" + action)
for action in ("scope", "goals", "constraints", "assets"):
    command("tasks", "add-" + action, "POST", "/api/tasks/{id}/" + action)
for action, param in (("scope", "sid"), ("goals", "gid"), ("constraints", "cid"), ("assets", "assetID")):
    command("tasks", "remove-" + action, "DELETE", "/api/tasks/{id}/" + action + "/{" + param + "}")
for action, param in (("goals", "gid"), ("constraints", "cid")):
    command("tasks", "update-" + action, "PATCH", "/api/tasks/{id}/" + action + "/{" + param + "}")
for verb, tail in (("archive", "archive"), ("rerun-blocked", "intents/rerun-blocked"), ("stop-chat", "chat/stop")):
    command("tasks", verb, "POST", "/api/tasks/{id}/" + tail)
command("tasks", "llm", "PUT", "/api/tasks/{id}/llm")
command("tasks", "llm-resolution", "GET", "/api/tasks/{id}/llm/resolution")
command("tasks", "chat", "POST", "/api/chat")
command("tasks", "report", "GET", "/api/report")
command("tasks", "events", "GET", "/api/exploration/activity/stream")
command("tasks", "activity", "GET", "/api/exploration/activity/history")
command("tasks", "sessions", "GET", "/api/exploration/main-sessions")
command("tasks", "new-session", "POST", "/api/exploration/main-session/new")
command("tasks", "control-batch", "POST", "/api/tasks/control/batch")
command("tasks", "archive-batch", "POST", "/api/tasks/archive/batch")
resource("categories", "/api/task-categories", "list create update delete")
resource("templates", "/api/task-templates", "list create update delete")
resource("archives", "/api/task-archives", "list get delete")
command("archives", "restore", "POST", "/api/task-archives/{id}/restore")
for action in ("pause", "resume", "cancel"):
    command("intents", action, "POST", "/api/tasks/{id}/intents/{iid}/control", {"action": action})
command("intents", "message", "POST", "/api/tasks/{id}/intents/{iid}/messages")
command("intents", "rerun", "POST", "/api/tasks/{id}/intents/{iid}/rerun")
command("intents", "list", "GET", "/api/exploration/intents")
resource("findings", "/api/exploration/findings", "list get update delete")
for action in ("stats", "groups", "asset-tree"):
    command("findings", action, "GET", "/api/exploration/findings/" + action)
for action in ("lineage", "retests", "traffic"):
    command("findings", action, "GET", "/api/exploration/findings/{id}/" + action)
command("findings", "retest", "POST", "/api/exploration/findings/{id}/retests")
command("findings", "deepen", "POST", "/api/exploration/findings/{id}/deepen")
command("findings", "bind-traffic", "POST", "/api/exploration/findings/{id}/traffic")
command("findings", "export", "GET", "/api/exploration/findings/export", query={"scope": "filtered", "format": "md-single"})
resource("assets", "/api/assets", "list create")
command("assets", "delete", "DELETE", "/api/assets")
command("assets", "counts", "GET", "/api/assets/counts")
resource("companies", "/api/companies", "list create get delete")
command("companies", "scope", "POST", "/api/companies/{id}/scope")
command("companies", "reattribute", "POST", "/api/companies/reattribute")
resource("conversations", "/api/conversations", "list create update delete")
command("conversations", "messages", "GET", "/api/conversations/{id}/messages")
command("conversations", "send", "POST", "/api/conversations/{id}/messages")
command("conversations", "stop", "POST", "/api/conversations/{id}/stop")
command("conversations", "profile", "PATCH", "/api/conversations/{id}/profile")
for verb, route in (("pending", "pending"), ("get", "pending/{id}"), ("history", "history"), ("detail", "history/{id}"), ("execution", "history/{id}/execution")):
    command("approvals", verb, "GET", "/api/intercept/" + route)
for verb, decision in (("allow", "allowed"), ("deny", "denied")):
    command("approvals", verb, "POST", "/api/intercept/pending/{id}/decide", {"decision": decision})
resource("rules", "/api/intercept/rules", "list create update delete", update="PUT")
resource("asset-rules", "/api/asset-intercept/rules", "list create update delete", update="PUT")
for verb, method, route in (("list", "GET", "list"), ("read", "GET", "read"), ("write", "POST", "write"), ("mkdir", "POST", "mkdir"), ("delete", "DELETE", "delete"), ("download", "GET", "download"), ("upload", "POST", "upload")):
    command("workspace", verb, method, "/api/workspace/" + route)
for verb, method, route in (("list", "GET", ""), ("hosts", "GET", "/hosts"), ("get", "GET", "/exchange"), ("blob", "GET", "/blob"), ("delete", "DELETE", ""), ("delete-all", "DELETE", "/all")):
    command("traffic", verb, method, "/api/traffic" + route)
resource("agents", "/api/agents", key="key")
for verb, method in (("config", "PUT"), ("prompt", "PUT"), ("wrapup", "PUT"), ("visibility", "GET"), ("prompts", "GET"), ("variables", "GET")):
    command("agents", verb, method, "/api/agents/{key}/" + verb)
command("agents", "reset-prompt", "POST", "/api/agents/{key}/prompt/reset")
command("tools", "list", "GET", "/api/tools")
command("tools", "update", "PUT", "/api/tools/{key}")
command("tools", "reset", "POST", "/api/tools/{key}/reset")
resource("custom-tools", "/api/tools/custom", "create update delete", update="PUT", key="key")
command("custom-tools", "test", "POST", "/api/tools/custom/test")
resource("mcp", "/api/mcp", "list create delete")
for verb, method in (("tools", "GET"), ("refresh", "POST")):
    command("mcp", verb, method, "/api/mcp/{id}/" + verb)
resource("skills", "/api/skills", "list create delete", key="name")
for verb in ("files", "usage"):
    command("skills", verb, "GET", "/api/skills/{name}/" + verb)
for verb, method in (("read", "GET"), ("write", "PUT"), ("delete-file", "DELETE")):
    command("skills", verb, method, "/api/skills/{name}/files/{file...}")
command("skills", "upload", "POST", "/api/skills/upload")
command("skills", "missing", "GET", "/api/skills/missing")
command("skills", "meta", "PUT", "/api/skills/{name}/meta")
for verb, method, path in (("get", "GET", "/api/llm"), ("set", "POST", "/api/llm"), ("test", "POST", "/api/llm/test"), ("models", "POST", "/api/llm/models"), ("profiles", "GET", "/api/llm/profiles"), ("save-profile", "POST", "/api/llm/profiles"), ("delete-profile", "DELETE", "/api/llm/profiles/{id}"), ("activate", "POST", "/api/llm/profiles/active"), ("pool", "GET", "/api/llm/pool"), ("reset-pool", "POST", "/api/llm/pool/reset"), ("retry-policy", "GET", "/api/llm/retry-policy"), ("set-retry-policy", "POST", "/api/llm/retry-policy")):
    command("llm", verb, method, path)
for verb, method in (("get", "GET"), ("set", "PUT")):
    command("settings", verb, method, "/api/settings")
for verb, path in (("history", "/api/logs/history"), ("list", "/api/logs"), ("follow", "/api/logs/stream")):
    command("logs", verb, "GET", path)
for group, path in (("commands", "/api/commands"), ("llm-records", "/api/llm/records")):
    command(group, "list", "GET", path)
command("commands", "stats", "GET", "/api/commands/stats")
command("llm-records", "get", "GET", "/api/llm/records/{id}")
resource("notify", "/api/notify/channels", "list create update delete")
command("notify", "test", "POST", "/api/notify/channels/{id}/test")
command("notify", "deliveries", "GET", "/api/notify/deliveries")
command("notify", "retry", "POST", "/api/notify/deliveries/{id}/retry")
for verb in ("usage", "daily", "conversations"):
    command("tokens", verb, "GET", "/api/tokens/" + verb)
for verb, method, path in (("fofa-config", "GET", "fofa/config"), ("fofa-set", "POST", "fofa/config"), ("fofa-quota", "GET", "fofa/quota"), ("fofa-preview", "POST", "fofa/preview"), ("fofa-import", "POST", "fofa/import"), ("status", "GET", "scopesentry/status"), ("datasource", "POST", "scopesentry/datasource"), ("projects", "GET", "scopesentry/projects"), ("tasks", "GET", "scopesentry/tasks"), ("run", "POST", "scopesentry/sync")):
    command("sync", verb, method, "/api/sync/" + path)
for verb, method in (("check", "GET"), ("apply", "POST"), ("rollback", "POST"), ("stream", "GET")):
    command("update", verb, method, "/api/update/" + verb)
for verb in ("frontier", "graph", "nodes", "activity", "tokens"):
    command("exploration", verb, "GET", "/api/exploration/" + verb)
