from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
VALID_AUTHORITIES = {"state_agency", "state_program", "official_administrator"}
VALID_CATEGORIES = {
    "state_esa", "general_esa", "stem", "neurodivergent", "phd_brand", "general",
}


class ConfigError(ValueError):
    pass


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: str | Path, value: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def host_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == domain.lower() or host.endswith(f".{domain.lower()}") for domain in allowed_domains)


def validate_configuration(domains_data: Any, programs_data: Any) -> tuple[list[dict], dict[str, dict]]:
    domains = domains_data.get("domains", []) if isinstance(domains_data, dict) else []
    programs_list = programs_data.get("programs", []) if isinstance(programs_data, dict) else []
    if len(domains) != 51:
        raise ConfigError(
            f"The supplied matrix contains 51 spoke domains; configuration has {len(domains)}"
        )

    programs: dict[str, dict] = {}
    for program in programs_list:
        program_id = str(program.get("id", "")).strip()
        if not program_id or program_id in programs:
            raise ConfigError(f"Program ids must be non-empty and unique: {program_id!r}")
        sources = program.get("sources", [])
        for source in sources:
            url = str(source.get("url", ""))
            parts = urlsplit(url)
            allowed = source.get("allowed_domains", [])
            if parts.scheme != "https" or not parts.hostname:
                raise ConfigError(f"{program_id}: sources must use HTTPS: {url}")
            if not allowed or not host_allowed(url, allowed):
                raise ConfigError(f"{program_id}: source host is not in its allowlist: {url}")
            if source.get("authority") not in VALID_AUTHORITIES:
                raise ConfigError(f"{program_id}: invalid source authority for {url}")
            for pattern in source.get("follow_patterns", []):
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise ConfigError(f"{program_id}: invalid follow pattern {pattern!r}: {exc}") from exc
        programs[program_id] = program

    seen: set[str] = set()
    for site in domains:
        domain = str(site.get("domain", "")).lower().strip()
        if not DOMAIN_RE.fullmatch(domain) or domain in seen:
            raise ConfigError(f"Spoke domains must be valid and unique: {domain!r}")
        seen.add(domain)
        if domain == "allinclusivetutoring.com":
            raise ConfigError("The hub domain cannot be configured as a spoke")
        if site.get("program_id") not in programs:
            raise ConfigError(f"{domain}: unknown program_id {site.get('program_id')!r}")
        if site.get("category") not in VALID_CATEGORIES:
            raise ConfigError(f"{domain}: invalid category {site.get('category')!r}")
        for required in ("headline", "angle", "audience"):
            if not str(site.get(required, "")).strip():
                raise ConfigError(f"{domain}: missing {required}")
    return domains, programs


def load_and_validate(root: str | Path) -> tuple[list[dict], dict[str, dict]]:
    root_path = Path(root)
    return validate_configuration(
        load_json(root_path / "config" / "domains.json"),
        load_json(root_path / "config" / "programs.json"),
    )

