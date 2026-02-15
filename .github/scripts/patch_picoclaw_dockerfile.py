#!/usr/bin/env python3
from pathlib import Path
import re
import sys

DOCKERFILE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Dockerfile")
GOMOD = Path(sys.argv[2]) if len(sys.argv) > 2 else DOCKERFILE.parent / "go.mod"

s = DOCKERFILE.read_text(encoding="utf-8")

# ---- Patch Go version to match go.mod (best-effort) ----
required_go = None
if GOMOD.exists():
    m = re.search(r"(?m)^\s*go\s+([0-9]+(?:\.[0-9]+)?)\s*$", GOMOD.read_text(encoding="utf-8"))
    if m:
        required_go = m.group(1)

if required_go:
    # Only replace the common pattern; if upstream changes formatting, we don't hard-fail.
    s2 = re.sub(r"(?m)^(FROM\s+golang:)[0-9.]+(-alpine\s+AS\s+builder\s*)$",
                rf"\g<1>{required_go}\2", s)
    s = s2

# ---- Non-root / home rewrite (best-effort, future-friendly) ----
s = s.replace("/root/.picoclaw", "/home/picoclaw/.picoclaw")

# If upstream already sets USER anywhere, don't inject our own USER block.
# (This avoids fighting upstream if they implement non-root themselves.)
if not re.search(r"(?m)^\s*USER\s+", s):
    inject = r"""
# Non-root runtime user (injected by downstream build)
ARG PICOCLAW_USER=picoclaw
ARG PICOCLAW_UID=1000
ARG PICOCLAW_HOME=/home/${PICOCLAW_USER}
ENV HOME=${PICOCLAW_HOME}

RUN set -eux; \
    addgroup -S -g ${PICOCLAW_UID} ${PICOCLAW_USER} 2>/dev/null || addgroup -S ${PICOCLAW_USER}; \
    adduser -S -D -h ${PICOCLAW_HOME} -u ${PICOCLAW_UID} -G ${PICOCLAW_USER} ${PICOCLAW_USER} 2>/dev/null || true; \
    mkdir -p ${PICOCLAW_HOME}/.picoclaw/workspace/skills; \
    if [ -d /opt/picoclaw/skills ]; then cp -r /opt/picoclaw/skills/* ${PICOCLAW_HOME}/.picoclaw/workspace/skills/ 2>/dev/null || true; fi; \
    chown -R ${PICOCLAW_UID}:${PICOCLAW_UID} ${PICOCLAW_HOME}/.picoclaw || true

WORKDIR ${PICOCLAW_HOME}
USER ${PICOCLAW_UID}:${PICOCLAW_UID}
""".lstrip("\n")

    # Insert right before ENTRYPOINT ["picoclaw"] if present; otherwise do nothing.
    m = re.search(r'(?m)^\s*ENTRYPOINT\s+\["picoclaw"\]\s*$', s)
    if m:
        s = s[:m.start()] + inject + s[m.start():]

DOCKERFILE.write_text(s, encoding="utf-8")
print(f"Patched {DOCKERFILE}")
