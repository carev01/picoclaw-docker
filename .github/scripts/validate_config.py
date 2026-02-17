#!/usr/bin/env python3
"""
Validate and update the web management console (server.py + templates/index.html)
when PicoClaw's upstream config.example.json introduces new configuration options.

Uses the Zhipu z.ai GLM-5-Code model to analyse differences and propose updates.

Environment variables
---------------------
ZHIPU_API_KEY       : (required) API key for z.ai
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

API_URL = "https://api.z.ai/api/paas/v4/chat/completions"
MODEL = "GLM-5-Code"
MAX_TOKENS = 16384
TEMPERATURE = 0.1

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


def structural_diff(upstream: dict, current: dict) -> dict:
    """Return keys added/removed/changed between upstream and current configs."""
    flat_up = _flatten(upstream)
    flat_cur = _flatten(current)
    added = {k: v for k, v in flat_up.items() if k not in flat_cur}
    removed = {k: v for k, v in flat_cur.items() if k not in flat_up}
    changed = {
        k: {"upstream": flat_up[k], "current": flat_cur[k]}
        for k in flat_up
        if k in flat_cur and flat_up[k] != flat_cur[k]
    }
    return {"added": added, "removed": removed, "changed": changed}


def extract_default_config_json(server_src: str) -> dict | None:
    """Try to extract the dict returned by default_config() in server.py."""
    m = re.search(
        r"def\s+default_config\s*\(\s*\)\s*:\s*\n\s*return\s*(\{.+?\n\s*})",
        server_src,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        # The source uses Python dict syntax; eval is safe here as we control the input.
        return json.loads(json.dumps(ast.literal_eval(m.group(1))))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior software engineer. You will be given:
    1. An upstream config.example.json for PicoClaw.
    2. The current server.py (a Starlette web management console).
    3. The current templates/index.html (an Alpine.js + Tailwind CSS frontend).
    4. A structural diff showing what config keys were added, removed, or changed.

    Your task:
    - Update BOTH server.py and templates/index.html so that **every** configuration
      key present in the upstream config.example.json is properly handled:
      • server.py: update default_config(), SECRET_FIELDS, mask_secrets(), and
        merge_secrets() as needed.
      • templates/index.html: add/remove/modify UI controls (inputs, checkboxes,
        selects) to expose all configuration options. Follow the existing code style
        exactly (Alpine.js x-model bindings, Tailwind classes, section layout).
    - Do NOT remove any existing functionality that is still in the upstream config.
    - DO NOT remove existing configuration options even if not in upstream anymore
    - Keep all existing code style, structure, and conventions intact.
    - If NO changes are needed (the files already match upstream), respond with
      exactly: NO_CHANGES_NEEDED

    Respond with the COMPLETE updated file contents in fenced code blocks:

    ```python
    # === server.py ===
    <full file contents>
    ```

    ```html
    <!-- === index.html === -->
    <full file contents>
    ```

    CRITICAL: Output the COMPLETE files, not partial diffs.
""")


def build_user_prompt(
    upstream_json: str,
    diff_summary: dict,
    server_src: str,
    index_src: str,
) -> str:
    return textwrap.dedent(f"""\
        ## Upstream config.example.json

        ```json
        {upstream_json}
        ```

        ## Structural diff (what changed upstream vs. current defaults)

        ```json
        {json.dumps(diff_summary, indent=2)}
        ```

        ## Current server.py

        ```python
        {server_src}
        ```

        ## Current templates/index.html

        ```html
        {index_src}
        ```

        Please update both files so they fully reflect the upstream configuration.
    """)


def call_llm(api_key: str, system: str, user: str) -> str:
    """Call the z.ai chat completions API with retry and backoff."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = json.dumps({
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
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


def extract_fenced_block(text: str, language: str) -> str | None:
    """Extract the content of a fenced code block for the given language."""
    pattern = rf"```{re.escape(language)}\s*\n(.*?)```"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Validation
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
    api_key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if not api_key:
        log("ERROR: ZHIPU_API_KEY environment variable is not set")
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

    # --- Diff -----------------------------------------------------------
    current_config = extract_default_config_json(server_src)
    if current_config is None:
        log("WARNING: Could not extract default_config() from server.py; sending full context to LLM")
        diff_summary = {"note": "Could not parse current defaults; full analysis required"}
    else:
        diff_summary = structural_diff(upstream_config, current_config)
        if not diff_summary["added"] and not diff_summary["removed"] and not diff_summary["changed"]:
            log("No config differences detected — nothing to do")
            set_output("config_changed", "false")
            set_output("files_updated", "false")
            return 0

    log(f"Config diff: +{len(diff_summary.get('added', {}))} added, "
        f"-{len(diff_summary.get('removed', {}))} removed, "
        f"~{len(diff_summary.get('changed', {}))} changed")
    set_output("config_changed", "true")

    # --- Call LLM -------------------------------------------------------
    user_prompt = build_user_prompt(upstream_json_str, diff_summary, server_src, index_src)

    try:
        response = call_llm(api_key, SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        log(f"ERROR: LLM call failed: {e}")
        log("Continuing build without config updates (fail-open)")
        set_output("files_updated", "false")
        return 0

    # --- Check for no-change signal ------------------------------------
    if "NO_CHANGES_NEEDED" in response:
        log("LLM determined no changes are needed")
        set_output("files_updated", "false")
        return 0

    # --- Extract file contents ------------------------------------------
    new_server = extract_fenced_block(response, "python")
    new_index = extract_fenced_block(response, "html")

    if new_server is None or new_index is None:
        log("WARNING: Could not extract both files from LLM response")
        log("Response preview (first 500 chars):")
        log(response[:500])
        log("Continuing build without config updates (fail-open)")
        set_output("files_updated", "false")
        return 0

    # Narrow types — guaranteed non-None by the guard above
    assert new_server is not None
    assert new_index is not None

    # --- Validate -------------------------------------------------------
    py_errors = validate_python(new_server)
    if py_errors:
        log("Python validation FAILED:")
        for err in py_errors:
            log(f"  • {err}")
        log("Continuing build without config updates (fail-open)")
        set_output("files_updated", "false")
        return 0

    html_errors = validate_html(new_index)
    if html_errors:
        log("HTML validation FAILED:")
        for err in html_errors:
            log(f"  • {err}")
        log("Continuing build without config updates (fail-open)")
        set_output("files_updated", "false")
        return 0

    # --- Write files ----------------------------------------------------
    log("Validation passed — writing updated files")
    write_file(SERVER_PY, new_server)
    write_file(INDEX_HTML, new_index)
    set_output("files_updated", "true")
    log("Done — files updated successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
