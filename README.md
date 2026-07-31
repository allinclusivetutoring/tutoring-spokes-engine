# Tutoring Spokes Engine

A verified-source crawler and static generator for the tutoring-domain matrix. The
provided list contains **51 spoke domains**, although the original heading called it a
50-spoke plan. `allinclusivetutoring.com` remains the hub and is not generated as a
spoke.

This version replaces the original paragraph-copying script. It does not disguise
itself as a browser, republish source articles, or push a newly scraped deadline
straight to production.

## How the system works

```text
approved official URLs
        │
        ▼
robots-aware targeted crawler
        │
        ▼
candidate facts + change report
        │
        ▼
human verifies source, wording, and expiration
        │
        ▼
approved_facts.json
        │
        ▼
Jinja generator ──► 51 host-routed static sites ──► Netlify
```

The crawler stores short review excerpts and provenance, not whole articles. Candidate
facts have no publication path. Only a human-reviewed paraphrase in
`data/approved_facts.json` can appear on a generated site, and expiring facts disappear
automatically after their review window.

## Project layout

- `config/domains.json` — all 51 domains, audiences, page angles, and program mapping.
- `config/programs.json` — official source URLs and exact host allowlists.
- `spoke_engine/crawler.py` — robots-aware crawler, conditional requests, extraction,
  candidate classification, snapshots, and change reports.
- `spoke_engine/generator.py` — validated Jinja rendering, expiration checks, canonical
  URLs, sitemaps, robots files, and Netlify host rewrites.
- `data/candidates.json` — machine-collected review queue; never published.
- `data/approved_facts.json` — human-reviewed, source-linked publishable facts.
- `reports/change_report.md` — weekly additions, removals, and crawl failures.
- `.github/workflows/weekly-refresh.yml` — Sunday crawl, preview, tests, artifact, and
  review pull request.
- `netlify.toml` — production validation and build settings.

## Local setup

```powershell
cd "$env:USERPROFILE\OneDrive\Desktop\tutoring-spokes-engine"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Use a monitored contact address and descriptive user agent:

```powershell
$env:CRAWLER_CONTACT = "crawler-operator@example.org"
$env:CRAWLER_USER_AGENT = "AllInclusiveTutoringFactsBot/1.0 (+mailto:crawler-operator@example.org)"
```

## Run it

Validate all configuration and approved facts:

```powershell
python engine.py validate
```

Crawl only the configured official sources:

```powershell
python engine.py crawl
```

Review these two files:

- `reports/change_report.md`
- `data/candidates.json`

Verify every proposed date, amount, application status, and eligibility statement by
opening its source. Then write a concise paraphrase into `data/approved_facts.json` with:

- a unique `id`;
- the correct `program_id`;
- a short `label` and factual `value`;
- official `source_url` and `source_title`;
- `reviewed_at` in `YYYY-MM-DD` format;
- a conservative `expires_at` date;
- `review_status` set to `approved`.

The generator rejects facts whose source is outside that program's configured host
allowlist. It omits facts after `expires_at`.

Generate a search-engine-blocked preview:

```powershell
python engine.py generate --preview
```

Generate production files only after review:

```powershell
python engine.py generate --production
```

Output is placed under `dist/sites/<domain>/`. The generated `_redirects` file rewrites
each incoming domain to its own directory while preserving the visitor-facing URL.

## Weekly GitHub review

The included workflow runs at Sunday 00:00 UTC, which is Saturday 5:00 PM in Phoenix.
It:

1. validates configuration;
2. crawls approved sources;
3. builds a `noindex` preview;
4. runs the test suite;
5. uploads the preview for 14 days;
6. opens or updates a pull request containing candidate facts and the change report.

It intentionally does **not** approve facts or push them directly to the production
branch. Scholarship deadlines and funding details can affect family decisions, so a
weekly human review is part of the architecture.

In the GitHub repository settings, create Actions variables named:

- `CRAWLER_CONTACT`
- `CRAWLER_USER_AGENT`

The repository must allow GitHub Actions to create pull requests. Scheduled workflows
run from the default branch, so merge the workflow there before expecting the schedule.

## Netlify setup

Connect the GitHub repository to one Netlify project. Netlify reads `netlify.toml`, runs
validation plus the production generator, and publishes `dist`.

For the host-routing design to work, add every owned spoke domain as a custom domain or
domain alias on that Netlify project and configure its DNS. The generated `_redirects`
file contains HTTPS host-level rewrites for all 51 domains. Confirm your Netlify plan,
certificate provisioning, and domain-alias limits before moving production DNS.

Always test at least two unrelated domains in a deploy preview and production before
moving the remaining domains. Keep `allinclusivetutoring.com` on its existing site.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests verify the 51-domain matrix, unique domains, source allowlists, approved-fact
provenance, candidate extraction, preview `noindex`, independence disclosures,
canonical URLs, and Netlify host routes.

## Editorial and SEO guardrails

Each page must offer genuine standalone value for its named audience. Do not claim that
a tutor is approved, eligible for reimbursement, endorsed, or affiliated with a program
unless the current official program directory supports that exact claim. Do not turn
the network into near-duplicate doorway pages or auto-generate unsupported testimonials,
credentials, outcomes, locations, deadlines, or funding amounts.

The initial approved facts were manually checked against the linked primary or official
administrator pages on 2026-07-31. Their expiration dates are intentionally short.
`robots.txt` permission does not grant content-republication rights, and this system is
not a substitute for legal review of scholarship marketing, privacy, advertising, or
program-provider rules.

