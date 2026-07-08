# Stable MCP Server

An [MCP](https://modelcontextprotocol.io) server for [Stable](https://www.usestable.com), the virtual mailbox and business address service. Connect Claude (or any MCP-capable AI assistant) to your Stable mailbox so it can:

- 📬 **List your mail** — sender, recipient, scan status, tags, check/deposit/forwarding status
- 📖 **Read scanned letters** — pulls the OCR text of a scan so your assistant can read you the actual contents ("read me that letter from the IRS")
- 🏷️ **Organize with tags** — create tags and apply or remove them across mail items
- 📍 **List your locations** — every address on your account

**Zero dependencies.** It's a single Python file that runs on the Python that ships with macOS (3.9+). No `pip install`, no Node.js, no build step.

> **Note:** Stable's public API is currently read-and-organize only. Requesting a scan, forward, shred, or check deposit still happens in the Stable dashboard.

## Setup

### 1. Get the server

```bash
git clone https://github.com/travisthetrashpanda/stable-mcp.git
```

Or just download `server.py` — it's the whole server.

### 2. Add your API key

Create an API key at [dashboard.usestable.com/settings/api-keys](https://dashboard.usestable.com/settings/api-keys), then save it next to the server:

```bash
cd stable-mcp
echo "your-api-key-here" > api_key.txt
chmod 600 api_key.txt
```

(`api_key.txt` is gitignored so it can't be committed. Alternatively, set the `STABLE_API_KEY` environment variable in your MCP client config and skip the file.)

### 3. Connect your client

**Claude Code:**

```bash
claude mcp add --scope user stable -- python3 /path/to/stable-mcp/server.py
```

**Claude Desktop** — add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "stable": {
      "command": "python3",
      "args": ["/path/to/stable-mcp/server.py"]
    }
  }
}
```

**Cursor / other MCP clients** — any client that supports stdio MCP servers works with the same command: `python3 /path/to/stable-mcp/server.py`

Restart your client after adding the server.

## Try it

Ask your assistant things like:

- "Any new mail this week?"
- "Read me the letter from Ford Credit"
- "Which mail items have checks in them?"
- "Tag everything from the county as 'Property tax'"

## Tools

| Tool | What it does |
|---|---|
| `list_mail_items` | List mail with filters (location, date range, scan status) and pagination |
| `get_mail_item` | Full detail on one mail item, including scan summary and image URLs |
| `get_mail_scan_text` | Fetch the OCR text of a scanned letter so the assistant can read it |
| `list_locations` | All addresses on the account |
| `list_tags` | All tags (id + name) |
| `create_tags` | Create new tags |
| `set_mail_item_tags` | Apply/remove tags on one or more mail items |

## Security notes

- Your API key stays on your machine. The server talks only to `api.usestable.com` (plus Stable's presigned scan-document URLs when you ask it to read a letter).
- Treat the key like a password: it grants access to your mail, which may contain sensitive documents and checks.
- Anything your assistant reads (mail contents, senders) becomes part of your conversation with it.

## Say thanks

This project is free to use, no strings attached. If it's useful to you, a ⭐ on this repo or a shout-out to [@travisthetrashpanda](https://github.com/travisthetrashpanda) is always appreciated — and if you build something on top of it, a link back here helps other Stable users find it.

Don't have Stable yet? [Sign up with my referral link](https://dashboard.usestable.com/onboard/begin?promoCode=travis-44ad84stref) — it's a zero-cost way to say thanks (full disclosure: it's a referral code, so I get credit if you join).

## License

MIT
