from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from spoke_engine.config import ConfigError, load_and_validate
from spoke_engine.crawler import run_crawl
from spoke_engine.generator import generate_sites, validate_approved_facts
from spoke_engine.config import load_json


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="spoke-engine",
        description="Crawl official program pages, review facts, and generate tutoring resource sites.",
    )
    root.add_argument("--root", default=str(PROJECT_ROOT), help="Project root")
    commands = root.add_subparsers(dest="command", required=True)

    crawl = commands.add_parser("crawl", help="Collect candidate facts from approved official sources")
    crawl.add_argument("--strict", action="store_true", help="Fail when any configured source cannot be fetched")
    crawl.add_argument("--delay", type=float, default=2.0, help="Minimum delay per host in seconds")

    generate = commands.add_parser("generate", help="Generate all 51 static sites")
    mode = generate.add_mutually_exclusive_group()
    mode.add_argument("--production", action="store_true", help="Allow indexing and write dist/")
    mode.add_argument("--preview", action="store_true", help="Disallow indexing and write preview-dist/")
    generate.add_argument("--output", help="Override output directory")

    commands.add_parser("validate", help="Validate domain, source, and approved-fact configuration")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project_root = Path(args.root).resolve()
    try:
        if args.command == "crawl":
            result = run_crawl(project_root, strict=args.strict, delay=args.delay)
            print(
                f"Collected {len(result['candidates'])} candidate facts; "
                f"{len(result['errors'])} source errors. Human review is required."
            )
            return 0
        if args.command == "generate":
            production = bool(args.production)
            output = args.output or project_root / ("dist" if production else "preview-dist")
            manifest = generate_sites(
                project_root,
                output_dir=output,
                production=production,
            )
            print(
                f"Generated {manifest['site_count']} {'production' if production else 'preview'} "
                f"sites in {Path(output).resolve()}"
            )
            return 0
        if args.command == "validate":
            _, programs = load_and_validate(project_root)
            facts = validate_approved_facts(
                load_json(project_root / "data" / "approved_facts.json"), programs
            )
            print(f"Configuration is valid; {len(facts)} approved facts are publishable.")
            return 0
    except (ConfigError, RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1

