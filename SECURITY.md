# Security policy

## Supported scope

This repository is a private research prototype, not a production gateway. It
must bind to loopback by default and must not be exposed publicly without an
authenticated reverse proxy, TLS, rate limits, isolated credentials, and an
explicit security review.

## Reporting

Do not open a public issue containing an unreleased product name, endpoint,
prompt, token, credential, customer record, or reproduction that can harm a
third party. Contact the repository owner privately and include:

- affected version and configuration;
- exact trust boundary;
- harmless reproduction steps;
- expected and actual behavior;
- redacted evidence and timestamps;
- proposed mitigation.

## Secrets

Never commit `.env`, API keys, SSH passwords, cookies, raw authorization
headers, production logs, proprietary system prompts, or unredacted user data.
Rotate any credential that has appeared in chat, terminal history, screenshots,
or a previous commit before sharing the repository with another person.

## Public deployment warning

The approval console can view and modify sensitive model traffic. An
unauthenticated public deployment is equivalent to granting strangers control
over the model channel. Public deployment is outside the supported scope.
