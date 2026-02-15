#!/usr/bin/env python3
from pathlib import Path
import re
import sys

DOCKERFILE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Dockerfile")
GOMOD = Path(sys.argv[2]) if len(sys.argv) > 2 else DOCKERFILE.parent / "go.mod"

s = DOCKERFILE.read_text(encoding="utf-8")

# ---- Determine required Go version (prefer toolchain directive if present) ----
required_go = None
if GOMOD.exists():
    gm = GOMOD.read_text(encoding="utf-8")

    # toolchain go1.25.7  (Go 1.21+)
    m = re.search(r"(?m)^\s*toolchain\s+go([0-9]+(?:\.[0-9]+){1,2})\s*$", gm)
    if m:
        required_go = m.group(1)
    else:
        # go 1.25.7  or go 1.25
        m = re.search(r"(?m)^\s*go\s+([0-9]+(?:\.[0-9]+){1,2})\s*$", gm)
        if m:
            required_go = m.group(1)

# ---- Patch golang builder image tag(s) ----
if required_go:
    # Replace any "FROM golang:<ver><suffix>" with "FROM golang:<required_go><same suffix>"
    # Suffix examples: -alpine, -alpine3.21, etc.
    s = re.sub(
        r"(?m)^(FROM\s+golang:)([0-9]+(?:\.[0-9]+){1,2})([^ \t\r\n]*)(.*)$",
        rf"\g<1>{required_go}\g<3>\g<4>",
        s,
    )

# ---- Rewrite /root usage (best-effort) ----
s = s.replace("/root/.picoclaw", "/home/picoclaw/.picoclaw")

# ---- Inject non-root block only if upstream hasn't done it and we haven't injected before ----
marker = "Non-root runtime user (injected by downstream build)"
if marker not in s and not re.search(r"(?m)^\s*USER\s+", s):
    inject = f"""
# {marker}
ARG PICOCLAW_USER=picoclaw
ARG PICOCLAW_UID=1000
ARG PICOCLAW_HOME=/home/${{PICOCLAW_USER}}
ENV HOME=${{PICOCLAW_HOME}}

RUN set -eux; \\
    addgroup -S -g ${{PICOCLAW_UID}} ${{PICOCLAW_USER}} 2>/dev/null || addgroup -S ${{PICOCLAW_USER}}; \\
    adduser  -S -D -h ${{PICOCLAW_HOME}} -u ${{PICOCLAW_UID}} -G ${{PICOCLAW_USER}} ${{PICOCLAW_USER}} 2>/dev/null || true; \\
    mkdir -p ${{PICOCLAW_HOME}}/.picoclaw/workspace/skills; \\
    if [ -d /opt/picoclaw/skills ]; then cp -r /opt/picoclaw/skills/* ${{PICOCLAW_HOME}}/.picoclaw/workspace/skills/ 2>/dev/null || true; fi; \\
    chown -R ${{PICOCLAW_UID}}:${{PICOCLAW_UID}} ${{PICOCLAW_HOME}}/.picoclaw || true

WORKDIR ${{PICOCLAW_HOME}}
USER ${{PICOCLAW_USER}}
""".lstrip("\n")

    # Insert before ENTRYPOINT if present, else before CMD, else append.
    m = re.search(r"(?m)^\s*ENTRYPOINT\s+.*$", s)
    if m:
        s = s[:m.start()] + inject + s[m.start():]
    else:
        m = re.search(r"(?m)^\s*CMD\s+.*$", s)
        if m:
            s = s[:m.start()] + inject + s[m.start():]
        else:
            s = s.rstrip() + "\n\n" + inject

DOCKERFILE.write_text(s, encoding="utf-8")
print(f"Patched {DOCKERFILE} (required_go={required_go})")
