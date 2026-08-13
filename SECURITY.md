# Security

AFI-OS keeps OAuth credentials, API tokens and provider keys outside the repository.
The macOS setup flow stores runtime credentials in Keychain. Local `.env` files,
OAuth client JSON, databases, backups and logs must never be committed.

Before publishing a change, verify that only `.env.example` is tracked and that it
contains placeholders or non-secret defaults. Revoke and rotate any credential that
is ever committed, even if the commit is later deleted.
