#!/usr/bin/env python3
"""
Validate and update the web management console (server.py + templates/index.html)
when PicoClaw's upstream config.example.json introduces new configuration options.

Uses the an LLM to analyse differences and propose updates.

Environment variables
---------------------
LLM_API_KEY       : (required) API key for LLM
UPSTREAM_VERSION    : (optional) git tag to fetch config from; defaults to 'main'
GITHUB_OUTPUT       : (set by Actions) path to write step outputs
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "minimax/minimax-m2.5"

MAX_RETRIES = 3
INITIAL_BACKOFF_S = 5       # 5 → 15 → 45
BACKOFF_MULTIPLIER = 3
REQUEST_TIMEOUT_S = 120

UPSTREAM_CONFIG_URL_TPL = (
    "https://raw.githubusercontent.com/sipeed/picoclaw/{ref}/config/config.example.json"
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SERVER_PY = os.path.join(REPO_ROOT, "server.py")
INDEX_HTML = os.path.join(REPO_ROOT, "templates", "index.html")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[config-validator] {msg}", flush=True)


def set_output(name: str, value: str) -> None:
    """Write a GitHub Actions output variable."""
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch a URL and return the body as text."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Structural diff
# ---------------------------------------------------------------------------


def _flatten(obj: object, prefix: str = "") -> dict[str, object]:
    """Flatten a nested dict to dot-separated paths."""
    items: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            items.update(_flatten(v, new_key))
    elif isinstance(obj, list):
        items[prefix] = obj
    else:
        items[prefix] = obj
    return items


def get_config_analysis(upstream: dict, current_defaults: dict) -> dict:
    """Analyze configuration differences for LLM context."""
    flat_upstream = _flatten(upstream)
    flat_current = _flatten(current_defaults)
    
    upstream_keys = set(flat_upstream.keys())
    current_keys = set(flat_current.keys())
    
    new_keys = upstream_keys - current_keys
    
    return {
        "upstream_config": upstream,
        "known_fields": list(current_keys),
        "upstream_keys": list(upstream_keys),
        "new_keys": list(new_keys)
    }


def extract_json_from_response(response: str) -> dict | None:
    """Extract and parse JSON from LLM response (handling markdown blocks)."""
    try:
        # Extract JSON from response (handle potential markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            json_str = response.strip()
        return json.loads(json_str)
    except Exception:
        return None


def extract_default_config_json(server_src: str) -> dict | None:
    """Try to extract the dict returned by default_config() in server.py."""
    try:
        tree = ast.parse(server_src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "default_config":
                for stmt in node.body:
                    if isinstance(stmt, ast.Return) and stmt.value:
                        # ast.literal_eval can evaluate a Dict node if it contains only literals
                        assert stmt.value is not None
                        return ast.literal_eval(stmt.value)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Python and JavaScript/HTML developer specializing in web configuration interfaces.

    Your task is to analyze the upstream PicoClaw configuration schema and determine if the web management console (server.py and index.html) needs updates to expose new or changed configuration options.

    RESPONSE FORMAT (JSON only, no other text):
    {
      "changes_needed": true/false,
      "server_py_changes": {
        "needed": true/false,
        "description": "Description of changes needed",
        "modified_code": "full modified server.py content if needed, null otherwise"
      },
      "index_html_changes": {
        "needed": true/false,
        "description": "Description of changes needed", 
        "modified_code": "full modified index.html content if needed, null otherwise"
      },
      "new_config_options": ["list of new config options detected"],
      "removed_config_options": ["list of removed/deprecated config options"],
      "summary": "Brief summary of changes"
    }

    GUIDELINES:
    1. Only suggest changes if NEW configuration options exist in upstream that aren't exposed in the web UI
    2. Maintain the existing code style and structure
    3. Ensure Alpine.js bindings are correct in HTML
    4. Preserve all existing functionality
    5. Use appropriate input types (password for secrets, checkbox for booleans, etc.)
    6. Group related settings logically
    7. DO NOT remove existing configuration options even if not in upstream
    8. The server.py default_config() function should include defaults for new options
    9. SECRET_FIELDS set should include any new secret fields
""")



def generate_llm_prompt(
    analysis: dict,
    server_src: str,
    index_src: str,
) -> str:
    return textwrap.dedent(f"""\
        Analyze the PicoClaw configuration files for necessary updates.

        ## Upstream Configuration Schema
        ```json
        {json.dumps(analysis['upstream_config'], indent=2)}
        ```

        ## Current server.py
        ```python
        {server_src}
        ```

        ## Current templates/index.html
        ```html
        {index_src}
        ```

        ## Analysis Summary
        - Known fields in current implementation: {sorted(analysis['known_fields'])}
        - Fields in upstream config: {sorted(analysis['upstream_keys'])}
        - Potentially new fields: {sorted(analysis['new_keys'])}

        Determine if updates are needed to expose any new configuration options in the web management console. Return ONLY valid JSON.
    """)


def call_llm(api_key: str, system: str, user: str) -> str:
    """Call the LLM chat completions API with retry and backoff."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")

    backoff = INITIAL_BACKOFF_S

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"LLM request attempt {attempt}/{MAX_RETRIES} …")
            req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                log(f"LLM responded ({len(content)} chars)")
                return content

        except urllib.error.HTTPError as e:
            status = e.code
            log(f"HTTP {status} from API")

            if status == 429:
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else backoff
                log(f"Rate limited. Waiting {wait}s …")
                time.sleep(wait)
            elif 500 <= status < 600:
                log(f"Server error. Waiting {backoff}s …")
                time.sleep(backoff)
            else:
                # 4xx (non-429) — not retryable
                body = e.read().decode("utf-8", errors="replace")
                log(f"Non-retryable error: {body}")
                raise

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log(f"Network error: {e}. Waiting {backoff}s …")
            time.sleep(backoff)

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log(f"Malformed response: {e}. Waiting {backoff}s …")
            time.sleep(backoff)

        backoff *= BACKOFF_MULTIPLIER

    raise RuntimeError("LLM request failed after all retries")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------





def validate_python(src: str) -> list[str]:
    """Validate that the Python source is syntactically correct and contains key markers."""
    errors: list[str] = []
    try:
        ast.parse(src)
    except SyntaxError as e:
        errors.append(f"Python syntax error: {e}")
        return errors  # No point checking further

    required_markers = ["default_config", "SECRET_FIELDS", "Route"]
    for marker in required_markers:
        if marker not in src:
            errors.append(f"Missing expected identifier: {marker}")

    return errors


def validate_html(src: str) -> list[str]:
    """Basic validation for the HTML template."""
    errors: list[str] = []

    if "<!DOCTYPE html>" not in src and "<!doctype html>" not in src.lower():
        errors.append("Missing <!DOCTYPE html>")

    # Check balanced <script>…</script>
    opens = len(re.findall(r"<script[\s>]", src, re.IGNORECASE))
    closes = len(re.findall(r"</script>", src, re.IGNORECASE))
    if opens != closes:
        errors.append(f"Unbalanced <script> tags: {opens} opens vs {closes} closes")

    # Must still have Alpine.js patterns
    if "x-data=" not in src:
        errors.append("Missing Alpine.js x-data binding")
    if "x-model=" not in src:
        errors.append("Missing Alpine.js x-model binding")

    # Must still have defaultConfig function
    if "defaultConfig()" not in src and "function defaultConfig" not in src:
        errors.append("Missing defaultConfig() function")

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        log("ERROR: LLM_API_KEY environment variable is not set")
        return 1

    upstream_ref = os.environ.get("UPSTREAM_VERSION", "main").strip() or "main"
    config_url = UPSTREAM_CONFIG_URL_TPL.format(ref=upstream_ref)

    # --- Fetch upstream config ------------------------------------------
    log(f"Fetching upstream config from {config_url}")
    try:
        upstream_json_str = fetch_url(config_url)
        upstream_config = json.loads(upstream_json_str)
    except Exception as e:
        log(f"WARNING: Could not fetch upstream config: {e}")
        log("Falling back to main branch …")
        try:
            config_url = UPSTREAM_CONFIG_URL_TPL.format(ref="main")
            upstream_json_str = fetch_url(config_url)
            upstream_config = json.loads(upstream_json_str)
        except Exception as e2:
            log(f"ERROR: Could not fetch upstream config from main either: {e2}")
            set_output("config_changed", "false")
            set_output("files_updated", "false")
            return 0  # fail-open

    # --- Read current files ---------------------------------------------
    log("Reading current server.py and index.html")
    try:
        server_src = read_file(SERVER_PY)
        index_src = read_file(INDEX_HTML)
    except FileNotFoundError as e:
        log(f"ERROR: {e}")
        return 1

    # --- Analysis -------------------------------------------------------
    current_config = extract_default_config_json(server_src)
    if current_config is None:
        log("WARNING: Could not extract default_config() from server.py; sending full context to LLM")
        # Ensure we have a valid structure even if current defaults extraction fails
        analysis = {
            "upstream_config": upstream_config,
            "known_fields": [],
            "upstream_keys": list(upstream_config.keys()),
            "new_keys": list(upstream_config.keys())
        }
    else:
        analysis = get_config_analysis(upstream_config, current_config)
        if not analysis["new_keys"]:
            log("No new config keys detected — nothing to do")
            set_output("config_changed", "false")
            set_output("files_updated", "false")
            return 0

    log(f"Config analysis: {len(analysis['new_keys'])} new keys found: {analysis['new_keys']}")
    set_output("config_changed", "true")

    # --- Call LLM -------------------------------------------------------
    user_prompt = generate_llm_prompt(analysis, server_src, index_src)

    try:
        response = call_llm(api_key, SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        log(f"ERROR: LLM call failed: {e}")
        with open("latest_llm_error.txt", "w", encoding="utf-8") as f:
            f.write(str(e))
        log("Saved error details to latest_llm_error.txt")
        log("Continuing build without config updates (fail-open)")
        set_output("files_updated", "false")
        return 0

    # --- Parse Response -------------------------------------------------
    result = extract_json_from_response(response)
    if not result:
        log("ERROR: Could not parse LLM response as JSON")
        log("Response preview (first 500 chars):")
        log(response[:500])
        set_output("files_updated", "false")
        return 0

    if not result.get("changes_needed", False):
        log("LLM determined no changes are needed")
        set_output("files_updated", "false")
        return 0
    
    # --- Apply Changes --------------------------------------------------
    files_modified = False
    
    # Apply server.py changes
    server_changes = result.get("server_py_changes", {})
    if server_changes.get("needed") and server_changes.get("modified_code"):
        new_server = server_changes["modified_code"]
        py_errors = validate_python(new_server)
        if not py_errors:
            write_file(SERVER_PY, new_server)
            log(f"Updated server.py: {server_changes.get('description')}")
            files_modified = True
        else:
            log("Python validation FAILED for suggested server.py changes:")
            for err in py_errors:
                log(f"  • {err}")
    
    # Apply index.html changes
    html_changes = result.get("index_html_changes", {})
    if html_changes.get("needed") and html_changes.get("modified_code"):
        new_index = html_changes["modified_code"]
        html_errors = validate_html(new_index)
        if not html_errors:
            write_file(INDEX_HTML, new_index)
            log(f"Updated index.html: {html_changes.get('description')}")
            files_modified = True
        else:
            log("HTML validation FAILED for suggested index.html changes:")
            for err in html_errors:
                log(f"  • {err}")

    # Log new/removed options
    new_options = result.get("new_config_options", [])
    if new_options:
        log(f"New config options detected by LLM: {new_options}")
    
    files_updated_str = "true" if files_modified else "false"
    set_output("files_updated", files_updated_str)
    
    if files_modified:
        log("Done — files updated successfully")
    else:
        log("Done — no files were updated (validation failed or no changes provided)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
