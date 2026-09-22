# Security policy

## Supported versions

Security fixes are applied to the actively maintained release line and current development branch.

## Reporting a security or privacy issue

Please **do not** open a public issue containing any of the following:

- Moj Elektro API tokens
- EIMM or GSRN identifiers
- names, addresses, owner/contact data
- raw diagnostics you have not reviewed
- screenshots/logs containing private meter/account data

If a problem can be demonstrated without sensitive data, open a normal GitHub issue and use redacted examples.

If sensitive material has already been posted publicly, revoke/replace the exposed API token immediately and remove the sensitive material from the public report.

## Diagnostics

The integration attempts to keep diagnostics safe to share by redacting credentials and omitting measurement values and personal account fields. Always review diagnostics before publishing them because upstream schemas can evolve.
