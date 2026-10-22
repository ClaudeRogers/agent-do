"""Bounded advisory HTTP reads, caching, source adapters, and KEV enrichment."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from .model import cvss_scores, ecosystem, finding, now, timestamp
from .store import atomic_json, digest, home

NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
GHSA = "https://api.github.com/advisories"
KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


class SourceError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Endpoints are fixed authorities; do not forward credentials via redirects.
        raise SourceError("Advisory source redirected; update the source adapter")


class Client:
    def __init__(self, args):
        self.args = args
        self.receipts = []
        self.last_nvd_request = None
        self.open = urllib.request.build_opener(NoRedirect()).open

    def get(self, url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"services.nvd.nist.gov", "api.github.com", "www.cisa.gov"}:
            raise SourceError("Unapproved advisory endpoint")
        headers = {"Accept": "application/json", "User-Agent": "agent-do-security/1"}
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if parsed.hostname == "api.github.com" and token:
            headers["Authorization"] = "Bearer " + token
        if parsed.hostname == "services.nvd.nist.gov" and os.environ.get("NVD_API_KEY"):
            headers["apiKey"] = os.environ["NVD_API_KEY"]
        # Partition private cache entries by credential identity without persisting credentials.
        identity = digest((headers.get("Authorization", "") + headers.get("apiKey", "")).encode())
        path = home() / "cache" / (digest((url + identity).encode()) + ".json")
        cached = None
        try:
            cached = json.loads(path.read_text())
        except (OSError, ValueError):
            pass
        if cached and not self.args.refresh and (timestamp(now()) - timestamp(cached["fetched_at"])).total_seconds() < self.args.cache_ttl:
            self.receipts.append({"url": url, "fetched_at": cached["fetched_at"], "cache": True, "stale": False})
            return cached["body"], cached.get("headers", {})
        failure = "Network request failed"
        for attempt in range(self.args.retries + 1):
            try:
                if parsed.hostname == 'services.nvd.nist.gov' and self.last_nvd_request is not None:
                    interval = 0.6 if os.environ.get('NVD_API_KEY') else 6.0
                    delay = interval - (time.monotonic() - self.last_nvd_request)
                    if delay > 0:
                        time.sleep(delay)
                requested_at = time.monotonic()
                request = urllib.request.Request(url, headers=headers)
                with self.open(request, timeout=self.args.timeout) as response:
                    if parsed.hostname == 'services.nvd.nist.gov':
                        self.last_nvd_request = requested_at
                    body = response.read(self.args.max_bytes + 1)
                    if len(body) > self.args.max_bytes:
                        raise SourceError("Source response exceeds --max-bytes; no records discarded silently")
                    value = json.loads(body)
                    meta = {"link": response.headers.get("Link", ""), "last-modified": response.headers.get("Last-Modified", "")}
                fetched = now()
                atomic_json(path, {"fetched_at": fetched, "body": value, "headers": meta})
                self.receipts.append({"url": url, "fetched_at": fetched, "cache": False, "stale": False})
                return value, meta
            except urllib.error.HTTPError as exc:
                if parsed.hostname == 'services.nvd.nist.gov':
                    self.last_nvd_request = requested_at
                failure = "Advisory HTTP " + str(exc.code)  # Do not echo credential-bearing headers or bodies.
                retryable = exc.code in {429, 500, 502, 503, 504}
                if not retryable or attempt == self.args.retries:
                    break
                retry_after = exc.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2 ** attempt
                if delay > self.args.timeout:
                    failure += "; Retry-After exceeds --timeout; retry later"
                    break
                time.sleep(delay)
            except SourceError as exc:
                failure = str(exc)
                break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                failure = type(exc).__name__ + ": advisory fetch failed"
                break
        if cached and self.args.allow_stale:
            self.receipts.append({"url": url, "fetched_at": cached["fetched_at"], "cache": True, "stale": True, "error": failure})
            return cached["body"], cached.get("headers", {})
        raise SourceError(failure)


def nvd_row(cve):
    scores = []
    for name, metrics in (cve.get("metrics") or {}).items():
        if name.startswith("cvssMetric"):
            for metric in metrics:
                scores += cvss_scores([metric.get("cvssData", {})], metric.get("source", "NVD"))
    summary = next((x["value"] for x in cve.get("descriptions", []) if x.get("lang") == "en"), "")
    affected = []

    def visit(node):
        for match in node.get("cpeMatch", []):
            if match.get("vulnerable"):
                affected.append({"cpe": match.get("criteria"), "ranges": [match], "fixed_versions": []})
        for child in node.get("nodes", []) + node.get("children", []):
            visit(child)

    for config in cve.get("configurations", []):
        visit(config)
    return finding([cve["id"]], summary, "NVD", "https://nvd.nist.gov/vuln/detail/" + cve["id"],
                   scores=scores, published=cve.get("published"), modified=cve.get("lastModified"), affected=affected)


def ghsa_row(item):
    entries = []
    for version, score in (item.get("cvss_severities") or {}).items():
        if score:
            entries.append({**score, "version": version.replace("cvss_v", "").replace("_", ".")})
    if item.get("cvss"):
        entries.append(item["cvss"])
    affected = [{"package": v.get("package", {}), "ranges": [v.get("vulnerable_version_range")],
                 "fixed_versions": [v["first_patched_version"]] if v.get("first_patched_version") else []}
                for v in item.get("vulnerabilities", [])]
    ids = [item.get("ghsa_id"), item.get("cve_id")] + [x.get("value") for x in item.get("identifiers", [])]
    return finding(ids, item.get("summary"), "GitHub Advisory Database", item.get("html_url"),
                   scores=cvss_scores(entries, "GitHub Advisory Database"), severity=item.get("severity"),
                   published=item.get("published_at"), modified=item.get("updated_at"), affected=affected)


def discover(args, client, report):
    source = args.source
    if source == "auto":
        source = "github" if args.ecosystem or args.package else "nvd"
    if source == "nvd" and (args.ecosystem or args.package):
        raise ValueError("Use --source github for ecosystem/package discovery")
    if source == "github" and (args.vendor or args.product):
        raise ValueError("Use --source nvd for vendor/product discovery")
    report["target"] = {"kind": "advisory_query", "source": source,
                        "vendor": args.vendor, "product": args.product, "query": args.query}
    report["limitations"] += ["Discovery returns published advisory records; it does not establish repository exposure.",
                               "Coverage is limited to the selected advisory source."]
    rows, count, total, next_page = [], 0, None, None
    if source == "nvd":
        params = {"resultsPerPage": min(args.limit, 2000), "startIndex": 0}
        if args.cve:
            params["cveId"] = args.cve.upper()
        if args.query:
            params["keywordSearch"] = args.query
        if args.vendor or args.product:
            # CPE component identity is explicit: no guess that "java" means a particular JDK.
            params["virtualMatchString"] = "cpe:2.3:*:" + (args.vendor or "*") + ":" + (args.product or "*") + ":*:*:*:*:*:*:*:*"
            report["notes"].append("Vendor/product match NVD CPE component names. Use --query for broad text discovery; Java distributions have distinct CPE identities.")
        for after, before, prefix in ((args.published_after, args.published_before, "pub"), (args.updated_after, None, "lastMod")):
            if after or before:
                end = timestamp(before) if before else timestamp(now())
                start = timestamp(after) if after else end - timedelta(days=120)
                if end <= start or end - start > timedelta(days=120):
                    raise ValueError("NVD date windows must be positive and at most 120 days; provide both publication bounds")
                params[prefix + "StartDate"] = start.isoformat()
                params[prefix + "EndDate"] = end.isoformat()
        while count < args.limit:
            url = NVD + "?" + urllib.parse.urlencode(params)
            body, _ = client.get(url)
            if not isinstance(body.get("vulnerabilities"), list) or "totalResults" not in body:
                raise SourceError("Unexpected NVD response schema")
            batch = body["vulnerabilities"]
            total = body["totalResults"]
            remaining = args.limit - count
            for item in batch[:remaining]:
                if item["cve"].get("vulnStatus") != "Rejected":
                    rows.append(nvd_row(item["cve"]))
            count += min(len(batch), remaining)
            report["findings"] = rows[:]
            params["startIndex"] += len(batch)
            if params["startIndex"] >= total:
                break
            if not batch:
                raise SourceError("NVD pagination stalled before totalResults")
    else:
        params = {"per_page": min(args.limit, 100), "page": 1, "type": "reviewed"}
        if args.ecosystem:
            params["ecosystem"] = ecosystem(args.ecosystem)
        if args.package:
            params["affects"] = args.package
        if args.cve:
            params["cve_id"] = args.cve.upper()
        if args.published_after or args.published_before:
            params["published"] = (args.published_after or "*") + ".." + (args.published_before or "*")
        if args.updated_after:
            params["modified"] = ">=" + args.updated_after
        if args.query:
            raise ValueError("--query is supported by NVD; use --package for GitHub advisories")
        while count < args.limit:
            body, headers = client.get(GHSA + "?" + urllib.parse.urlencode(params))
            if not isinstance(body, list):
                raise SourceError("Unexpected GitHub advisory response schema")
            remaining = args.limit - count
            rows += [ghsa_row(x) for x in body[:remaining] if not x.get("withdrawn_at")]
            count += min(len(body), remaining)
            report["findings"] = rows[:]
            next_page = 'rel="next"' in headers.get("link", "") or len(body) > remaining
            if not next_page:
                break
            if not body:
                raise SourceError("GitHub advisory pagination stalled")
            params["page"] += 1
    truncated = count < total if total is not None else bool(next_page)
    report["coverage"].append({"source": source, "status": "truncated" if truncated else "ok",
                               "records_examined": count, "total_records": total,
                               "truncated": truncated, "limit": args.limit,
                               "receipts": client.receipts[:]})
    return rows


def enrich_kev(client, report):
    start = len(client.receipts)
    try:
        body, _ = client.get(KEV)
        if not isinstance(body.get("vulnerabilities"), list):
            raise SourceError("Unexpected KEV response schema")
        ids = {x["cveID"] for x in body["vulnerabilities"]}
        for row in report["findings"]:
            row["known_exploited"] = bool(ids & set(row["aliases"]))
            row["exploitation_source"] = {"url": KEV, "catalog_version": body.get("catalogVersion"),
                                           "fetched_at": client.receipts[-1]["fetched_at"]}
        report["coverage"].append({"source": "CISA KEV", "status": "ok", "receipts": client.receipts[start:]})
    except SourceError as exc:
        report["coverage"].append({"source": "CISA KEV", "status": "error", "error": str(exc)})
