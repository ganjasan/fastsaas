# Dev secrets — DEV ONLY

These are fake secrets for the local dev environment. They MUST NOT be used in
staging or production. The repo is private today; even so, treat anything here
as throwaway and **rotate immediately if a real environment ever loads them**.

## What's here

- `jwt/dev-1.pem` — RS256 private key signing development JWTs (kid = `dev-1`).
- `jwt/dev-1.pub.pem` — matching public key.

## Regeneration

Regenerate (and replace) at any time:

```bash
make gen-jwt-keys           # Wipes infra/dev-secrets/jwt/ and writes a new keypair.
```

## Production

Production keys live outside the repo. Set:

- `JWT_SIGNING_KEY_PATH=/run/secrets/jwt/<kid>.pem`
- `JWT_PUBLIC_KEYS_DIR=/run/secrets/jwt`
- `JWT_SIGNING_KID=<kid>`

via your secret manager. See `docs/runbooks/rotate-jwt-keys.md` for rotation.
