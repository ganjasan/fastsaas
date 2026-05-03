# Runbook: Rotate JWT signing keypair

**When to do this**

- Routine rotation (≥ once per year per key-management policy).
- Suspected key compromise — do this immediately AND revoke all refresh families
  (`uv run python -c "import asyncio; from fastsaas.identity.auth.refresh import revoke_all_for_actor; ..."` or simply `FLUSHDB` against the refresh DB if the blast radius is the whole tenant).

**Background — what tokens look at**

Per ADR-008 §8a + design.md §D1 the backend has two pieces of JWT key state:

| Setting | Role | Production value |
|---|---|---|
| `JWT_SIGNING_KID` | Key id baked into every newly issued token's header. | Active kid (e.g. `prod-2026-Q2`). |
| `JWT_SIGNING_KEY_PATH` | Absolute path to the PEM-encoded private key matching that kid. | `/run/secrets/jwt/<kid>.pem`. |
| `JWT_PUBLIC_KEYS_DIR` | Directory of `<kid>.pub.pem` files. The verifier picks by kid header. | `/run/secrets/jwt/` (mounted, read-only). |

In-flight access tokens carry the OLD kid in their header. They must keep verifying until they expire naturally (15 minutes), so during rotation BOTH the old `<kid>.pub.pem` AND the new `<kid>.pub.pem` must be present in `JWT_PUBLIC_KEYS_DIR`.

**Procedure**

1. **Generate the new keypair** — locally or in your secret store:

    ```bash
    KID=prod-2026-Q3 make gen-jwt-keys
    # writes infra/dev-secrets/jwt/$KID.pem and $KID.pub.pem
    ```

    For prod, generate inside the secret manager — `dev-secrets/` is for local dev only.

2. **Publish the new public key** — drop `<new-kid>.pub.pem` into the prod `JWT_PUBLIC_KEYS_DIR` alongside the old one. After this step, both keys verify; tokens still sign under the old kid.

3. **Roll out the new private key** — set `JWT_SIGNING_KID=<new-kid>` AND `JWT_SIGNING_KEY_PATH` to the new private key, then restart backend pods. From this point new tokens use the new kid.

4. **Wait the access-token TTL plus a margin** — minimum 15 minutes (the access TTL) but 30 minutes is a safe default. During this window, both old and new tokens verify.

5. **Decommission the old key** — once the wait elapses, remove the OLD `<old-kid>.pub.pem` from `JWT_PUBLIC_KEYS_DIR` and securely destroy the old private key.

6. **Verify** — `curl /auth/me` with a freshly-minted token; decode the JWT header and confirm `kid == <new-kid>`. Older tokens issued before step 3 should now fail with `auth.token_invalid` (`unknown kid`).

**Rollback**

Before step 5 (i.e. while both keys are still published) rollback is just step 3 in reverse: flip `JWT_SIGNING_KID` and `JWT_SIGNING_KEY_PATH` back to the old kid, restart, drop the new key from the public dir.

After step 5 there's no rollback — the old private key is gone. Mistakes get repaired by a fresh rotation, not a rewind.

**Tests that exercise this path**

- `backend/tests/test_identity_jwt.py::test_token_signed_with_rotated_kid_still_verifies` — multi-kid verification under rotation.
- `backend/tests/test_identity_jwt.py::test_token_with_unknown_kid_raises_invalid` — pruned-kid rejection.
