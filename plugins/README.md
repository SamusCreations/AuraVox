# Creating a Plugin for AuraVox

Each subfolder inside `plugins/` is a plugin. If it contains `manifest.json` and `plugin.py`, AuraVox automatically discovers it on startup and displays it under **Shared Settings → Plugins**.

Look at `plugins/dice_example/` to see a complete working example in ~35 lines of code.

---

## 1. Folder Structure

```text
plugins/
  my_plugin/
    manifest.json
    plugin.py
```

The folder name (`my_plugin`) is the plugin identifier: only lowercase letters, numbers, and `_` are allowed.

---

## 2. `manifest.json`

```json
{
  "name": "Visible Name",
  "version": "1.0",
  "description": "What this plugin adds to the assistants (one sentence).",
  "enabled_by_default": false,
  "settings": [
    {
      "key": "url",
      "label": "Server URL",
      "type": "text",
      "default": "http://127.0.0.1:8123",
      "placeholder": "http://..."
    },
    {
      "key": "api_key",
      "label": "Access Token",
      "type": "password",
      "default": ""
    }
  ]
}
```

- `settings` is optional. Supported field types (`type`): `"text"`, `"password"`, `"number"`, `"checkbox"`.
- What the user enters in the Settings UI is saved to `config/plugins.json` and passed to your functions inside the `settings` dictionary.

---

## 3. `plugin.py`

Must define `TOOLS` (a list of tools in Ollama/OpenAI function-calling format) and `execute(tool_name, args, ctx)`:

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "do_something",
            "description": "Explain to the AI model WHEN to use this tool (in English).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look up."},
                },
                "required": ["query"],
            },
        },
    },
]


def execute(name: str, args: dict, ctx: dict) -> str:
    """Runs when the assistant invokes one of the tools in TOOLS.
    Must return a plain text string with the result (which the assistant will read to formulate its reply).
    """
    settings = ctx["settings"]          # values configured by the user in the Web UI
    assistant = ctx["assistant"]        # name of the assistant invoking the tool
    if name == "do_something":
        q = args.get("query", "")
        return f"Result for {q} using {settings.get('url')}"
    return f"(unknown tool: {name})"


def prompt_Note(settings: dict) -> str:
    """Optional: extra instruction appended to the assistant's system prompt while the plugin is enabled."""
    return ""
```

After creating the folder, click **Reload** under **Shared Settings → Plugins** (or restart AuraVox) and toggle it on.
