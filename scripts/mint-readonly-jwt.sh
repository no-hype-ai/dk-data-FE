#!/usr/bin/env bash
# Mint a long-lived role=readonly JWT for PostgREST consumers.
#
# Reads JWT_SECRET from `doppler secrets get JWT_SECRET --config dk-data-prod`
# (override with $JWT_SECRET to mint against a different env, e.g. stg).
#
# Usage:
#   scripts/mint-readonly-jwt.sh <subject> [exp-days]
#
# Examples:
#   scripts/mint-readonly-jwt.sh edwards-meadow-cli         # 1-year exp (default)
#   scripts/mint-readonly-jwt.sh edwards-meadow-cli 90      # 90-day exp
#   scripts/mint-readonly-jwt.sh edwards-meadow-cli no-exp  # no exp (rotation-bound only)
#
# JWT carries the `role: readonly` claim, which PostgREST translates to the
# postgres role of the same name (CREATE ROLE readonly LOGIN in db-init).
# Pair with the JWT_SECRET rotation runbook at docs/runbooks/rotate-jwt-secret.md.
set -euo pipefail

SUBJECT="${1:-}"
EXP_DAYS="${2:-365}"
if [ -z "$SUBJECT" ]; then
  echo "Usage: $0 <subject> [exp-days|no-exp]" >&2
  exit 2
fi

if [ -z "${JWT_SECRET:-}" ]; then
  JWT_SECRET=$(doppler secrets get JWT_SECRET --plain \
      --project "${DOPPLER_PROJECT:-dk-data-fe}" \
      --config  "${DOPPLER_CONFIG:-prd}" 2>/dev/null) || {
    echo "Error: JWT_SECRET not in env and 'doppler secrets get' failed." >&2
    echo "Set JWT_SECRET=..., or DOPPLER_PROJECT/DOPPLER_CONFIG, or ensure" >&2
    echo "doppler is logged in for project dk-data-fe." >&2
    exit 1
  }
fi

export JWT_SECRET
python3 - "$SUBJECT" "$EXP_DAYS" <<'PY'
import json, os, sys, time, base64, hmac, hashlib

subject, exp_days = sys.argv[1], sys.argv[2]
secret = os.environ["JWT_SECRET"].encode()

now = int(time.time())
payload = {"role": "readonly", "iss": "dk-data-FE", "sub": subject, "iat": now}
if exp_days != "no-exp":
    payload["exp"] = now + int(exp_days) * 86400

def b64u(d): return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
header = b64u(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
body = b64u(json.dumps(payload, separators=(",", ":")).encode())
sig = b64u(hmac.new(secret, f"{header}.{body}".encode(), hashlib.sha256).digest())
print(f"{header}.{body}.{sig}")
PY
