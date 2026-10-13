# Spacelift read-only provider

`agent-do spacelift` is the single Spacelift integration for this repository.
Consumers such as incident tooling should call it instead of maintaining a
second Spacelift client. It is intentionally inspection-only: it does not
trigger runs, apply, approve, cancel, override policy, or remediate drift.

## What to ask your Spacelift administrator for

Create a **secret-based Spacelift API key** (a machine user), scoped to the
smallest set of spaces the agent must inspect and granted reader access. Do not
use an admin key. Spacelift API keys consist of an ID and secret and can be
exchanged for a short-lived GraphQL bearer JWT. See Spacelift's [GraphQL API
documentation](https://docs.spacelift.io/integrations/api).

Alternatively, a ready bearer JWT can be used for a short-lived session.

## Configure credentials

Set the account URL in the environment; it is not a secret and is deliberately
not accepted as a command argument:

```bash
export SPACELIFT_API_ENDPOINT="https://your-account.app.spacelift.io"
```

Choose exactly one authentication option.

### Recommended: machine API key

```bash
agent-do creds store SPACELIFT_API_KEY_ID --stdin
agent-do creds store SPACELIFT_API_KEY_SECRET --stdin
agent-do spacelift doctor --json
```

For each invocation, agent-do exchanges the pair with Spacelift for a
short-lived JWT in memory. It does not print or persist that JWT. This
authentication exchange is the only GraphQL mutation the provider makes; all
subsequent provider requests are queries.

### Temporary session: ready JWT

```bash
agent-do creds store SPACELIFT_API_TOKEN --stdin
agent-do spacelift doctor --json
```

If both forms are present, `SPACELIFT_API_TOKEN` wins. This is useful for an
interactive session or when another trusted tool has already minted a token.

Check the declared setup without revealing secrets:

```bash
agent-do creds required spacelift --json
agent-do creds check --tool spacelift --json
```

## Commands

```bash
# Prove that credentials work with one bounded authenticated read.
agent-do spacelift doctor --json

# Inspect stacks and a particular stack.
agent-do spacelift stacks --limit 50 --json
agent-do spacelift stack payments-production --json

# Find the commit, outcome, and policy result for a stack's runs.
agent-do spacelift runs --stack payments-production --limit 25 --json
agent-do spacelift run <run-id> --json

# Report recorded drift information. This never starts detection.
agent-do spacelift drift --stack payments-production --json
```

`--json` emits exactly one normalized JSON document, including failures. List
responses report `pagination.truncated` rather than silently discarding rows.
The API/schema does not expose a verified cursor for this provider's run query;
passing `--cursor` fails explicitly rather than producing a misleading page.

## Reading results safely

`run` keeps policy and Terraform failures distinct: `policy_failed` is based on
the policy result, while `terraform_apply_failed` reports a non-policy failure
message. `drift` always returns `checked_now: false`; it describes the latest
recorded detection run and returns `unknown` where the provider did not expose
a conclusive drift result.

Errors redact the configured JWT, API key ID, and API key secret. Never put
credentials on a command line, in a prompt, or in a checked-in `.env` file.

## Handoff prompt for a work agent

> Configure `agent-do spacelift` using `docs/SPACELIFT.md`. Prefer a
> least-privilege, secret-based Spacelift machine API key stored through
> `agent-do creds`; set `SPACELIFT_API_ENDPOINT` for the account. Run
> `agent-do spacelift doctor --json` before using the provider. Use only its
> read commands and do not create a separate Spacelift API client.

## Troubleshooting

- **Missing credential:** store a JWT, or both API-key values, with
  `agent-do creds store … --stdin`.
- **Rejected credential or missing permission:** confirm the machine key has
  reader access to the relevant Spacelift spaces and that the account endpoint
  is correct.
- **Expired JWT:** replace it, or use the API-key configuration so agent-do
  obtains a fresh JWT for each command.
- **Unknown drift:** no recorded drift-detection run exposed a conclusive state;
  this provider will not run detection to fill that gap.
