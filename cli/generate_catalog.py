#!/usr/bin/env python3
"""Regenerate the CLI API catalog from ARTEX route registrations.

Literal routes are discovered automatically. The two computed route families
are expanded explicitly so new registration styles require a conscious review.
"""
import argparse
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "cli/artex_cli/catalog.json"


def kebab(name):
    name = re.sub(r"^(?:pg|fs)(?=[A-Z])", "", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name).lower()


def catalog(root=ROOT):
    if not (root / "server").is_dir():
        raise SystemExit("Regenerating the API catalog requires the ARTEX backend source tree (server/*.go).")
    routes = []
    sources = {p: p.read_text() for p in sorted((root / "server").glob("*.go"))
               if not p.name.endswith("_test.go")}
    functions = {}
    types = {}
    for path, source in sources.items():
        for match in re.finditer(r"^type (\w+) struct \{(.*?)^}", source, re.M | re.S):
            types[match[1]] = match[2]
        for match in re.finditer(r"^func \(s \*Server\) (\w+)\([^\n]*\{", source, re.M):
            end = source.find("\n}", match.end())
            functions[match[1]] = (path, source[match.start():end + 2])

    def add(method, path, handler):
        src, body = functions.get(handler, (root / "server/server.go", ""))
        # These are discovery hints, not a complete schema: helpers can read more.
        queries = sorted(set(re.findall(r'(?:Query\(\)|\bq|\bquery)\.Get\("([^"]+)"\)', body)))
        request_types = re.findall(r"var (?:req|request|body) (\w+)\b", body)
        request_source = body + "\n" + "\n".join(types.get(t, "") for t in request_types)
        fields = sorted(set(re.findall(r'json:"([^",]+)', request_source)))
        routes.append(dict(operation=kebab(handler), method=method, path=path,
                           handler=handler, source=str(src.relative_to(root)),
                           query_hints=queries, body_field_hints=fields))

    literal = r'mux\.HandleFunc\("(GET|POST|PUT|PATCH|DELETE) (/api/[^" ]+)"\s*,\s*s\.(\w+)\)'
    computed_traffic = r'mux\.HandleFunc\("(\w+) "\+base(?:\+"([^"]+)")?, s\.(\w+)\)'
    computed_side = 'mux.HandleFunc(method+" "+route.path+"/side-questions",'
    for path, source in sources.items():
        for line in source.splitlines():
            if "mux.HandleFunc(" in line and not re.search(literal, line):
                known = (path.name == "finding_traffic.go" and re.search(computed_traffic, line)) or (path.name == "side_questions.go" and computed_side in line)
                assert known, f"Unrecognized route registration in {path.name}: {line.strip()}"
        for m in re.finditer(literal, source):
            add(m[1], m[2], m[3])
    traffic = sources[root / "server/finding_traffic.go"]
    base = re.search(r'base := "([^"]+)"', traffic)[1]
    for m in re.finditer(computed_traffic, traffic):
        add(m[1], base + (m[2] or ""), m[3])
    side_parents = re.findall(r'\{"(/api/[^"]+)", "(?:conversation|main|worker)"}', functions["registerSideRoutes"][1])
    assert side_parents, "No side-question parent routes found"
    for parent in side_parents:
        for method in ("GET", "POST", "DELETE"):
            add(method, parent + "/side-questions", "handleSideQuestions")
    counts = {}
    for route in routes:
        counts[route["operation"]] = counts.get(route["operation"], 0) + 1
    for route in routes:
        if counts[route["operation"]] > 1:
            route["operation"] = route["method"].lower() + "-" + re.sub(r"[^a-zA-Z0-9]+", "-", route["path"].removeprefix("/api/")).strip("-").lower()
    routes.sort(key=lambda r: (r["path"], r["method"]))
    keys = [(r["method"], r["path"]) for r in routes]
    assert len(keys) == len(set(keys)), "duplicate route"
    assert len({r["operation"] for r in routes}) == len(routes), "duplicate operation"
    return routes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(catalog(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not DEST.exists() or DEST.read_text() != content:
            parser.exit(1, "API catalog is stale; run python3 cli/generate_catalog.py\n")
    else:
        DEST.write_text(content)
    print(f"{len(catalog())} routes")
