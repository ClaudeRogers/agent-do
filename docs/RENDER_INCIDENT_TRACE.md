# Render incident trace

`agent-do render trace` collects a compact, read-only evidence packet for one Render service. It is intended for the planned incident tracker, which can save the JSON beside GitHub Actions, Kubernetes, and other provider evidence without making raw Render API calls itself.

```bash
agent-do render trace payments-api --since 30m --max-log-bytes 65536 --json
```

The result identifies the service and its source repository, branch, build filter, and auto-deploy settings. It then includes the ten newest deployments with their full commit SHAs, the hundred newest service events, and up to one hundred recent log entries in the requested time window.

## Why this is a separate command

Render already has commands for services, deploy history, events, and logs. An incident needs their facts together, in a predictable shape, and with limits that keep an evidence packet safe to store and review. `trace` combines only those reads. It never starts a deploy, changes a service, reads environment variables, or reveals credentials.

## Bounds and privacy

The command asks Render for at most ten deployments, one hundred events, and one hundred logs. It additionally limits the normalized log collection to 256 KiB at most; `--max-log-bytes` may lower that cap. The JSON says when Render has more log entries and when the local byte limit removed entries.

Common credential-shaped values in event details, log messages, and service configuration are replaced with `[REDACTED]`. This is a safety net rather than a promise that application logs contain no sensitive information. Operators should still limit access to incident evidence and avoid logging credentials.

## Errors

On a Render API failure, the command exits non-zero and writes a small JSON error object. That lets the incident tracker record unavailable evidence separately from a service that simply had no events or logs in the requested window.
