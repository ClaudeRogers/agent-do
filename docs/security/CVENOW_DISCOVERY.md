# Optional cve.now advisory discovery

`find --source cve-now` reads public advisory data from [cve.now](https://cve.now/).
It complements NVD/GitHub discovery; `auto`, repository scanning and runtime/vendor
assessment remain unchanged. No MCP installation, account or API key is needed.
The plugin never uploads lockfiles, source, repository URLs or deployment inventory
to this service. Only public IDs and feed selectors/cursors are sent via GET.

## Commands

```bash
# Public CVE detail, with original description, aliases, affected ranges and sources.
agent-do security find --source cve-now --cve CVE-2021-44228 --json

# Attach the service's polling and historical-coverage metadata.
agent-do security find --source cve-now --cve CVE-2021-44228 --source-status --json

# Examine up to ten recent global catalog records (details fetched for each).
agent-do security find --source cve-now --limit 10 --json

# Bounded recent Maven or Spring feeds, with local presentation filters.
agent-do security find --source cve-now --ecosystem java --limit 25 \
  --published-after 2026-10-01 --severity high,critical --json
agent-do security find --source cve-now --technology spring --limit 10 --json

# Curated exploitation-focused feeds; critical here is not CVSS critical.
agent-do security find --source cve-now --feed-filter critical --limit 10 --json
agent-do security find --source cve-now --feed-filter kev --limit 10 --json
```

Use current dates for your query. Shared CVE/score/date/package/fix filters and
HTTP timeout/retry/cache/byte-limit options apply; see the [CLI reference](SECURITY_CLI_REFERENCE.md).
`--technology`, `--feed-filter` and `--source-status` require this explicit source.
NVD vendor/product/keyword and curated `--target` selectors are not interchangeable
with cve.now feeds. Direct `--cve` lookup rejects technology/curated-feed selection;
ecosystem/package/date/score filters can still refilter the returned detail locally.

Supported ecosystems: npm, PyPI, Go, Maven, crates.io, Packagist, RubyGems, Hex and
NuGet. Existing aliases normalize, e.g. `java` → Maven and `python` → PyPI.
Documented technology slugs: `nextjs`, `react`, `node`, `express`, `django`, `flask`,
`rails`, `spring`, `log4j`, `kubernetes`, `docker`, `nginx`, `apache-httpd`, `openssl`,
`postgresql`, `mysql`, `redis`, `php`, `wordpress`, `jenkins`, `gitlab`, `fortinet`,
`citrix`, `ivanti`, `cisco-ios`, `palo-alto-panos`, `vmware`, `microsoft-exchange`,
`chrome`, `linux-kernel`. A technology feed can include related products; it does
not prove that the named framework or your deployment is vulnerable.

## Coverage and provenance

The entries API is cursor-paginated. Its records are hydrated with individual
advisory details, so the request count grows with `--limit` (default 100 records
examined before presentation filters). The server currently ignores a `limit`
parameter; the plugin enforces its cap locally and reports truncation.

The entries API also currently ignores technology/ecosystem selectors. Those
queries use the documented JSON feed instead, which returns **up to 200 recent
entries with no documented historical pagination**. Feed assessments are always
limited/incomplete, even when they return zero findings. They cannot answer “all
Java CVEs in 90 days” exhaustively. Date filters apply locally; no arbitrary
lookback completeness is implied. Use NVD/GitHub for supported historical queries.
Exit 0 means the selected lookup/catalog traversal completed; exit 1 includes
limited/truncated feeds, outages or unhealthy requested status. Neither means
absence of vulnerabilities. Partial findings remain saved after a later failure.

Reports retain the original description for display, full source records in
evidence, original advisory links and source-provided dates. Model-generated
summaries remain labeled metadata with model identity and CC-BY 4.0 attribution.
Aggregator-provided KEV evidence is identified as such; explicit `--kev` or
`--known-exploited` still requests direct CISA enrichment. `epssReached` is a dated
threshold event, **not a numeric EPSS probability**. Exploit-DB, related/bundle and
early-warning data are retained in source evidence; none establishes exploitability.
Published ecosystem/package fixes remain unverified recommendations, not upgrades
performed by this command. Conflicting upstream values remain available in evidence.

`--source-status` attaches self-reported polling/history information. A successful
status response is not independent proof that every upstream advisory is fresh.
HTTP reads reject redirects and upload/stack/MCP paths and never forward GitHub or
NVD credentials. Cached/stale data and failures use the existing explicit coverage
rules. If cve.now disappears, default discovery and existing repository/runtime
scans continue to work; this optional source reports its own failure.

## Additional API opportunities

The [public API reference](https://cve.now/llms.txt) and
[service documentation](https://github.com/sazabi/cve.now#api) also describe GHSA/OSV
lookup, RSS/Atom/JSON feeds and MCP access. Source health, curated feeds and
exploitation context are included here. Public GHSA/OSV lookup, external feed
subscriptions and restricted interactive MCP could be added separately; general
advisory scheduling is not implemented by portfolio monitoring. Stack upload and
`check_stack` are deliberately excluded. Numeric EPSS filtering requires an actual
probability field/provider rather than interpreting a threshold event as a score.
