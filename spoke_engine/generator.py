from __future__ import annotations

import html
import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from spoke_engine.config import load_and_validate, load_json, save_json


CATEGORY_CONTENT = {
    "state_esa": {
        "eyebrow": "Independent scholarship-program tutoring resource",
        "services": [
            "One-to-one academic tutoring shaped around the student's current coursework",
            "Executive-function support for planning, organization, and assignment follow-through",
            "Documentation suitable for a family's own records, subject to program rules",
        ],
    },
    "general_esa": {
        "eyebrow": "Education savings account tutoring guidance",
        "services": [
            "Remote tutoring plans for math, science, study skills, and academic confidence",
            "Clear session descriptions and recordkeeping for families managing education funds",
            "Program-specific questions directed back to the responsible state agency or administrator",
        ],
    },
    "stem": {
        "eyebrow": "Online STEM and study-skills tutoring",
        "services": [
            "Conceptual math and science instruction instead of answer-only homework help",
            "Engineering habits such as modeling, testing, iteration, and technical communication",
            "Study systems that break complex work into visible, manageable steps",
        ],
    },
    "neurodivergent": {
        "eyebrow": "Strengths-aware individualized tutoring",
        "services": [
            "Predictable session structure with flexible pacing and multiple ways to demonstrate learning",
            "Executive-function strategies externalized through checklists, calendars, and visual plans",
            "Collaboration with families around student preferences without making clinical claims",
        ],
    },
    "phd_brand": {
        "eyebrow": "Advanced individualized academic instruction",
        "services": [
            "High-level explanation that connects foundational skills to advanced applications",
            "Research, writing, quantitative reasoning, and independent-learning support",
            "A personalized plan based on goals, current evidence, and student feedback",
        ],
    },
    "general": {
        "eyebrow": "Flexible online tutoring for individual learners",
        "services": [
            "Individual instruction for homeschool, traditional-school, and alternative-learning students",
            "Academic planning that adapts to the learner's pace, goals, and schedule",
            "Regular family-facing progress summaries focused on work completed and next steps",
        ],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_approved_facts(data: Any, programs: dict[str, dict]) -> list[dict]:
    facts = data.get("facts", []) if isinstance(data, dict) else []
    ids: set[str] = set()
    validated: list[dict] = []
    for fact in facts:
        fact_id = str(fact.get("id", ""))
        if not fact_id or fact_id in ids:
            raise ValueError(f"Approved fact ids must be non-empty and unique: {fact_id!r}")
        ids.add(fact_id)
        if fact.get("review_status") != "approved":
            raise ValueError(f"{fact_id}: only approved facts belong in approved_facts.json")
        program_id = fact.get("program_id")
        if program_id not in programs:
            raise ValueError(f"{fact_id}: unknown program {program_id!r}")
        source_url = str(fact.get("source_url", ""))
        approved_urls = {
            source["url"] for source in programs[program_id].get("sources", [])
        }
        approved_hosts = {
            domain
            for source in programs[program_id].get("sources", [])
            for domain in source.get("allowed_domains", [])
        }
        host = (urlsplit(source_url).hostname or "").lower()
        if source_url not in approved_urls and not any(
            host == domain or host.endswith(f".{domain}") for domain in approved_hosts
        ):
            raise ValueError(f"{fact_id}: fact source is outside the program allowlist")
        for required in ("label", "value", "source_title", "reviewed_at"):
            if not str(fact.get(required, "")).strip():
                raise ValueError(f"{fact_id}: missing {required}")
        if fact.get("expires_at"):
            try:
                date.fromisoformat(fact["expires_at"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{fact_id}: expires_at must be YYYY-MM-DD") from exc
        validated.append(fact)
    return validated


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _utm_url(domain: str, category: str) -> str:
    params = urlencode(
        {
            "utm_source": domain,
            "utm_medium": "referral",
            "utm_campaign": f"spoke-{category}",
        }
    )
    return f"https://allinclusivetutoring.com/?{params}"


def _render_redirects(domains: list[dict]) -> str:
    lines = ["# Generated host-based rewrites. Every domain must first be assigned to this Netlify project."]
    for site in domains:
        domain = site["domain"]
        target = f"/sites/{domain}/:splat"
        lines.append(f"https://{domain}/*  {target}  200!")
        lines.append(f"https://www.{domain}/*  {target}  200!")
        lines.append(f"http://{domain}/*  https://{domain}/:splat  301!")
        lines.append(f"http://www.{domain}/*  https://{domain}/:splat  301!")
    lines.append("/  https://allinclusivetutoring.com/  302")
    return "\n".join(lines) + "\n"


def generate_sites(
    root: str | Path,
    *,
    output_dir: str | Path | None = None,
    production: bool = False,
) -> dict:
    root_path = Path(root)
    domains, programs = load_and_validate(root_path)
    approved_data = load_json(root_path / "data" / "approved_facts.json")
    all_facts = validate_approved_facts(approved_data, programs)
    today = date.today()
    facts = [
        fact
        for fact in all_facts
        if not fact.get("expires_at") or date.fromisoformat(fact["expires_at"]) >= today
    ]
    facts_by_program: dict[str, list[dict]] = {}
    for fact in facts:
        facts_by_program.setdefault(fact["program_id"], []).append(fact)

    output = Path(output_dir) if output_dir else root_path / ("dist" if production else "preview-dist")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    environment = Environment(
        loader=FileSystemLoader(root_path / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("site.html.j2")
    stylesheet = (root_path / "templates" / "styles.css").read_text(encoding="utf-8")
    generated_at = utc_now()
    manifest_sites: list[dict] = []

    for site in domains:
        domain = site["domain"]
        program = programs[site["program_id"]]
        program_facts = sorted(
            facts_by_program.get(site["program_id"], []),
            key=lambda item: (item.get("sort_order", 100), item["label"]),
        )
        last_reviewed = max(
            (fact["reviewed_at"] for fact in program_facts),
            default="No dynamic program facts approved yet",
        )
        page = template.render(
            site=site,
            program=program,
            facts=program_facts,
            category=CATEGORY_CONTENT[site["category"]],
            booking_url=_utm_url(domain, site["category"]),
            canonical_url=f"https://{domain}/",
            production=production,
            last_reviewed=last_reviewed,
            generated_at=generated_at,
        )
        site_root = output / "sites" / domain
        _write_text(site_root / "index.html", page)
        _write_text(site_root / "assets" / "styles.css", stylesheet)
        robots = (
            f"User-agent: *\nAllow: /\nSitemap: https://{domain}/sitemap.xml\n"
            if production
            else "User-agent: *\nDisallow: /\n"
        )
        _write_text(site_root / "robots.txt", robots)
        sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"  <url><loc>https://{html.escape(domain)}/</loc></url>\n"
            "</urlset>\n"
        )
        _write_text(site_root / "sitemap.xml", sitemap)
        _write_text(
            site_root / "404.html",
            f"<!doctype html><meta charset='utf-8'><meta name='robots' content='noindex'>"
            f"<title>Page not found</title><p>Return to <a href='https://{html.escape(domain)}/'>"
            f"{html.escape(domain)}</a>.</p>",
        )
        manifest_sites.append(
            {
                "domain": domain,
                "program_id": site["program_id"],
                "approved_fact_count": len(program_facts),
                "canonical_url": f"https://{domain}/",
            }
        )

    _write_text(output / "_redirects", _render_redirects(domains))
    _write_text(
        output / "index.html",
        "<!doctype html><html><head><meta charset='utf-8'><meta name='robots' content='noindex'>"
        "<meta http-equiv='refresh' content='0;url=https://allinclusivetutoring.com/'></head>"
        "<body><a href='https://allinclusivetutoring.com/'>All Inclusive Tutoring</a></body></html>",
    )
    manifest = {
        "generated_at": generated_at,
        "production": production,
        "site_count": len(manifest_sites),
        "sites": manifest_sites,
    }
    save_json(output / "manifest.json", manifest)
    return manifest
