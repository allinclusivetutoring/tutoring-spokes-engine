from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from spoke_engine.config import load_and_validate, load_json
from spoke_engine.crawler import candidate_facts, extract_page
from spoke_engine.generator import generate_sites, validate_approved_facts


ROOT = Path(__file__).resolve().parents[1]
TEST_OUTPUT = ROOT / ".test-output"


class ConfigurationTests(unittest.TestCase):
    def test_matrix_has_51_unique_spokes_and_excludes_hub(self):
        domains, _ = load_and_validate(ROOT)
        names = [site["domain"] for site in domains]
        self.assertEqual(len(names), 51)
        self.assertEqual(len(set(names)), 51)
        self.assertNotIn("allinclusivetutoring.com", names)

    def test_approved_facts_have_allowed_provenance(self):
        _, programs = load_and_validate(ROOT)
        facts = validate_approved_facts(
            load_json(ROOT / "data" / "approved_facts.json"), programs
        )
        self.assertGreaterEqual(len(facts), 10)
        self.assertTrue(all(fact["review_status"] == "approved" for fact in facts))


class ExtractionTests(unittest.TestCase):
    def test_extracts_short_review_candidates_not_whole_page(self):
        html = """
        <html><head><title>Official Program</title></head><body><main>
          <h1>Scholarship updates</h1>
          <p>Applications for the 2026-27 school year are open from March 2, 2026 through June 15, 2026.</p>
          <p>Eligible students may receive $5,435.62 for approved education expenses.</p>
          <p>This unrelated sentence should not become a candidate fact.</p>
        </main></body></html>
        """
        title, blocks, _ = extract_page(html, "https://agency.example.gov/program")
        source = {"authority": "state_program"}
        facts = candidate_facts("example", source, "https://agency.example.gov/program", title, blocks)
        self.assertEqual(len(facts), 2)
        self.assertTrue(any("June 15, 2026" in fact["dates_found"] for fact in facts))
        self.assertTrue(any("$5,435.62" in fact["amounts_found"] for fact in facts))
        self.assertTrue(all(len(fact["excerpt"]) <= 320 for fact in facts))


class GenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if TEST_OUTPUT.exists():
            shutil.rmtree(TEST_OUTPUT)
        cls.manifest = generate_sites(ROOT, output_dir=TEST_OUTPUT, production=False)

    @classmethod
    def tearDownClass(cls):
        if TEST_OUTPUT.exists():
            shutil.rmtree(TEST_OUTPUT)

    def test_generates_every_site_as_noindex_preview(self):
        self.assertEqual(self.manifest["site_count"], 51)
        page = (TEST_OUTPUT / "sites" / "iowaesatutoring.com" / "index.html").read_text(encoding="utf-8")
        self.assertIn('content="noindex,nofollow"', page)
        self.assertIn('rel="canonical" href="https://iowaesatutoring.com/"', page)
        self.assertIn("$8,148", page)

    def test_discloses_independence_even_for_approved_domain_name(self):
        page = (TEST_OUTPUT / "sites" / "approvedesatutoring.com" / "index.html").read_text(encoding="utf-8")
        self.assertIn("not a government website", page)
        self.assertIn("does not establish official approval", page)

    def test_netlify_routes_each_domain(self):
        redirects = (TEST_OUTPUT / "_redirects").read_text(encoding="utf-8")
        self.assertIn(
            "https://lagatortutoring.com/*  /sites/lagatortutoring.com/:splat  200!",
            redirects,
        )
        self.assertEqual(redirects.count("  200!"), 102)


if __name__ == "__main__":
    unittest.main()

