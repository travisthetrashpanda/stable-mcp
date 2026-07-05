#!/usr/bin/env python3
"""MCP server for Stable (usestable.com) — virtual mailbox.

A zero-dependency MCP server that connects AI assistants (Claude, Cursor,
or any MCP client) to the Stable API, so they can list your mail, read
scanned letters via OCR, and organize mail with tags.

Requires only Python 3.9+ (the version preinstalled on macOS). No pip
installs, no Node.js.

Setup: put your Stable API key (from
https://dashboard.usestable.com/settings/api-keys) in a file named
`api_key.txt` next to this script, or set the STABLE_API_KEY environment
variable. See README.md for client configuration.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error

API_BASE = "https://api.usestable.com"
SERVER_NAME = "stable"
SERVER_VERSION = "1.0.0"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_api_key():
    key = os.environ.get("STABLE_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(os.path.join(SCRIPT_DIR, "api_key.txt")) as f:
            key = f.read().strip()
    except OSError:
        key = ""
    return key


def api_request(method, path, query=None, body=None):
    key = get_api_key()
    if not key:
        raise RuntimeError(
            "No Stable API key found. Save your key (from "
            "https://dashboard.usestable.com/settings/api-keys) in %s "
            "or set the STABLE_API_KEY environment variable."
            % os.path.join(SCRIPT_DIR, "api_key.txt")
        )
    url = API_BASE + path
    if query:
        clean = {k: v for k, v in query.items() if v not in (None, "")}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    data = None
    headers = {"x-api-key": key, "accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError("Stable API error %d for %s %s: %s" % (e.code, method, path, detail))
    except urllib.error.URLError as e:
        raise RuntimeError("Could not reach Stable API: %s" % e.reason)
    if not raw:
        return {}
    return json.loads(raw)


def fetch_url_text(url, limit=60000):
    """Fetch a (presigned) URL and return best-effort plain text."""
    req = urllib.request.Request(url, headers={"accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    text = raw.decode("utf-8", "replace")
    try:
        data = json.loads(text)
    except ValueError:
        return text[:limit]
    # OCR payloads vary; harvest string values under text-ish keys.
    pieces = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and k.lower() in ("text", "detectedtext", "content", "fulltext"):
                    pieces.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    if pieces:
        return "\n".join(pieces)[:limit]
    return text[:limit]


def simplify_mail_item(item):
    recipients = item.get("recipients") or {}
    line1 = (recipients.get("line1") or {}).get("text")
    line2 = (recipients.get("line2") or {}).get("text")
    scan = item.get("scanDetails") or {}
    out = {
        "id": item.get("id"),
        "from": item.get("from"),
        "recipient": " / ".join(x for x in (line1, line2) if x) or None,
        "createdAt": item.get("createdAt"),
        "readAt": item.get("readAt"),
        "archivedAt": item.get("archivedAt"),
        "scanStatus": scan.get("status"),
        "scanSummary": scan.get("summary"),
        "tags": [t.get("name") for t in item.get("tags") or []],
        "checks": len(item.get("checks") or []),
        "location": (item.get("location") or {}).get("name") or (item.get("location") or {}).get("id"),
    }
    forward = item.get("forwardDetails") or {}
    deposit = item.get("depositDetails") or {}
    if forward.get("status"):
        out["forwardStatus"] = forward.get("status")
    if deposit.get("status"):
        out["depositStatus"] = deposit.get("status")
    if item.get("isReturnedToSender"):
        out["isReturnedToSender"] = True
    return {k: v for k, v in out.items() if v not in (None, [], 0)}


TOOLS = [
    {
        "name": "list_mail_items",
        "description": (
            "List mail items in the Stable virtual mailbox, newest info about each piece of "
            "physical mail (sender, recipient, scan status/summary, tags). Supports filtering "
            "and cursor pagination."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "location_id": {"type": "string", "description": "Filter to one location"},
                "created_after": {"type": "string", "description": "ISO date/time, e.g. 2026-06-01"},
                "created_before": {"type": "string", "description": "ISO date/time"},
                "scan_status": {"type": "string", "description": "Filter by scan status, e.g. completed or processing"},
                "limit": {"type": "integer", "description": "Max items to return (default 20)"},
                "after_cursor": {"type": "string", "description": "Cursor from a previous call's pageInfo.endCursor"},
            },
        },
    },
    {
        "name": "get_mail_item",
        "description": (
            "Get full details of one mail item by id: sender, recipients, scan details and "
            "summary, checks, deposit/forward tracking, tags, image URLs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Mail item id"}},
            "required": ["id"],
        },
    },
    {
        "name": "get_mail_scan_text",
        "description": (
            "Fetch the OCR text of a mail item's scanned contents (the letter inside), so the "
            "actual document can be read. Uses the scan OCR results if available, otherwise the "
            "envelope OCR."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Mail item id"}},
            "required": ["id"],
        },
    },
    {
        "name": "list_locations",
        "description": "List all Stable locations (addresses) on the account.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_tags",
        "description": "List all tags on the Stable account (id and name).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_tags",
        "description": "Create one or more new tags by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"}, "description": "Tag names to create"}
            },
            "required": ["names"],
        },
    },
    {
        "name": "set_mail_item_tags",
        "description": (
            "Assign and/or remove tags on one or more mail items. Use list_tags first to get "
            "tag ids."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mail_item_ids": {"type": "array", "items": {"type": "string"}},
                "add_tag_ids": {"type": "array", "items": {"type": "string"}},
                "remove_tag_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["mail_item_ids"],
        },
    },
]


def tool_list_mail_items(args):
    query = {
        "locationId": args.get("location_id"),
        "createdAt_gte": args.get("created_after"),
        "createdAt_lte": args.get("created_before"),
        "scan.status": args.get("scan_status"),
        "first": str(args.get("limit") or 20),
        "after": args.get("after_cursor"),
    }
    data = api_request("GET", "/v1/mail-items", query=query)
    items = [simplify_mail_item(e.get("node") or {}) for e in data.get("edges") or []]
    page = data.get("pageInfo") or {}
    return {
        "totalCount": data.get("totalCount"),
        "items": items,
        "hasNextPage": page.get("hasNextPage"),
        "endCursor": page.get("endCursor"),
    }


def tool_get_mail_item(args):
    return api_request("GET", "/v1/mail-items/" + args["id"])


def tool_get_mail_scan_text(args):
    item = api_request("GET", "/v1/mail-items/" + args["id"])
    scan = item.get("scanDetails") or {}
    urls = scan.get("ocrResultUrls") or item.get("ocrResultUrls") or []
    if not urls:
        status = scan.get("status")
        if status == "processing":
            return "The scan is still processing — try again in a bit."
        return (
            "No OCR text is available for this mail item. "
            "It may not have been scanned yet (request a scan in the Stable dashboard)."
        )
    parts = []
    for i, url in enumerate(urls):
        try:
            parts.append(fetch_url_text(url))
        except Exception as e:  # noqa: BLE001 - report per-page failures inline
            parts.append("[page %d failed to fetch: %s]" % (i + 1, e))
    header = "OCR text for mail item %s (from: %s)\n\n" % (item.get("id"), item.get("from"))
    return header + "\n\n--- page break ---\n\n".join(parts)


def tool_list_locations(args):
    return api_request("GET", "/v1/locations")


def tool_list_tags(args):
    return api_request("GET", "/v1/tags")


def tool_create_tags(args):
    body = {"tags": [{"name": n} for n in args["names"]]}
    return api_request("POST", "/v1/tags", body=body)


def tool_set_mail_item_tags(args):
    tags = [{"id": t, "isApplied": True} for t in args.get("add_tag_ids") or []]
    tags += [{"id": t, "isApplied": False} for t in args.get("remove_tag_ids") or []]
    if not tags:
        raise RuntimeError("Provide add_tag_ids and/or remove_tag_ids.")
    body = {"mailItemIds": args["mail_item_ids"], "tags": tags}
    return api_request("POST", "/v1/mail-items/tags", body=body)


TOOL_HANDLERS = {
    "list_mail_items": tool_list_mail_items,
    "get_mail_item": tool_get_mail_item,
    "get_mail_scan_text": tool_get_mail_scan_text,
    "list_locations": tool_list_locations,
    "list_tags": tool_list_tags,
    "create_tags": tool_create_tags,
    "set_mail_item_tags": tool_set_mail_item_tags,
}


def handle_request(msg):
    method = msg.get("method")
    params = msg.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion") or "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            raise RuntimeError("Unknown tool: %s" % name)
        try:
            result = handler(params.get("arguments") or {})
        except Exception as e:  # noqa: BLE001 - surface as tool error, keep server alive
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        if not isinstance(result, str):
            result = json.dumps(result, indent=1)
        return {"content": [{"type": "text", "text": result}]}
    raise RuntimeError("Method not found: %s" % method)


def main():
    stdin = sys.stdin
    stdout = sys.stdout
    while True:
        line = stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:
            continue  # notification — nothing to do
        response = {"jsonrpc": "2.0", "id": msg["id"]}
        try:
            response["result"] = handle_request(msg)
        except Exception as e:  # noqa: BLE001 - JSON-RPC error envelope
            response["error"] = {"code": -32603, "message": str(e)}
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()


if __name__ == "__main__":
    main()
