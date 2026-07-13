# backend/verify_connections.py
"""Offline sanity check for the Google Workspace connector.
Run inside the backend container:  python verify_connections.py
No network is required; live OAuth calls are NOT made here."""
import logging
logging.basicConfig(level=logging.INFO)

from app.services.connections.vault import TokenVault
from app.services.connections.oauth import GoogleOAuth, SCOPES
from app.services.connections.drive import _label, EXPORT_MAP
from app.services.connections.manager import ConnectionManager

ok = True

# [1] vault round-trips and never stores plaintext
v = TokenVault()
secret = "not-a-real-refresh-token-fixture"
ct = v.encrypt(secret)
assert secret not in ct, "plaintext leaked into ciphertext"
assert v.decrypt(ct) == secret, "decrypt did not recover the token"
print("[1] vault encrypt/decrypt OK (key_id=%s, plaintext not present)" % v.key_id)

# [2] oauth builds a consent url with offline access + PKCE (no network)
o = GoogleOAuth()
print("[2] oauth configured:", o.configured, "| scope:", SCOPES)
if o.configured:
    url, verifier = o.build_auth_url("teststate")
    for need in ("access_type=offline", "code_challenge", "response_type=code"):
        assert need in url, "auth url missing " + need
    print("    auth url contains offline + PKCE + code params")
else:
    print("    (client id/secret/redirect not set - expected in dev)")

# [3] drive label mapping + native export targets
assert _label("application/vnd.google-apps.spreadsheet", "x") == "Sheet"
assert ".xlsx" in {ext for _, ext in EXPORT_MAP.values()}, "sheets must export as xlsx"
print("[3] drive type labels + Sheets-as-xlsx export mapping OK")

# [4] manager runs with db=None (offline) without crashing
m = ConnectionManager(db=None)
assert m.status(workspace_id="w1") == {"connected": False}
assert m.disconnect(workspace_id="w1")["status"] == "disconnected"
print("[4] manager offline (db=None) status/disconnect OK")

# [5] punctuation: no em dash / en dash / ellipsis in user-facing strings
import pathlib
bad = {"\u2014", "\u2013", "\u2026"}
hits = []
for p in pathlib.Path("app/services/connections").rglob("*.py"):
    t = p.read_text(encoding="utf-8")
    for ch in bad:
        if ch in t:
            hits.append((p.name, repr(ch)))
assert not hits, "forbidden punctuation: %s" % hits
print("[5] punctuation clean (no em/en dash, no ellipsis)")

print("[OK] connector imports and runs." if ok else "[FAIL]")
