"""Тести без мережі: відповіді джерел підставляються з fixtures/."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from renovator_monitor import config as config_mod
from renovator_monitor import notify, pipeline, report
from renovator_monitor.fetch import FetchError, Response
from renovator_monitor.models import RawMention
from renovator_monitor.registry import Registry, effective_status
from renovator_monitor.relevance import query_is_strong, score_text
from renovator_monitor.sources import bing_news, telegram
from renovator_monitor.sources.rss import parse_feed
from renovator_monitor.textutil import canonical_url, parse_date, title_key

FX = Path(__file__).with_name("fixtures")


def fx(name: str) -> bytes:
    return (FX / name).read_bytes()


class FakeClient:
    """Повертає fixture за підрядком URL; невідомі URL дають FetchError."""

    def __init__(self, routes: dict[str, bytes]):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url, headers=None):
        self.calls.append(url)
        for key, body in self.routes.items():
            if key in url:
                return Response(url, 200, body, "text/xml; charset=utf-8")
        raise FetchError(f"немає маршруту для {url}")


def test_config(tmp: str) -> dict:
    cfg = config_mod.load()
    cfg["storage"] = {"registry": f"{tmp}/registry.jsonl", "export_dir": tmp}
    cfg["sources"]["google_news"]["editions"] = [
        {"hl": "uk", "gl": "UA", "ceid": "UA:uk", "queries": ["Реноватор"]},
        {"hl": "en-GB", "gl": "GB", "ceid": "GB:en", "queries": ["Renovator NATO Ukraine"]},
    ]
    cfg["sources"]["bing_news"]["markets"] = [{"setlang": "en", "cc": "GB", "queries": ["Renovator NATO"]}]
    cfg["sources"]["gdelt"]["queries"] = ["\"project renovator\""]
    cfg["sources"]["govuk"]["queries"] = ["Renovator Ukraine"]
    cfg["sources"]["wordpress"]["sites"] = [
        {"url": "https://armyinform.com.ua", "name": "АрміяInform", "lang": "uk", "queries": ["реноватор"]}]
    cfg["sources"]["telegram"]["channels"] = ["testchannel"]
    cfg["sources"]["telegram"]["queries"] = ["реноватор"]
    return cfg


ROUTES = {
    "ceid=UA:uk": fx("google_uk.xml"),
    "ceid=GB:en": fx("google_en.xml"),
    "bing.com/news": fx("bing.xml"),
    "api.gdeltproject.org": fx("gdelt.json"),
    "gov.uk/api/search": fx("govuk.json"),
    "armyinform.com.ua/?s=": fx("wordpress.xml"),
    "t.me/s/testchannel": fx("telegram.html"),
    "defenceonline.co.uk/2026": fx("defenceonline.html"),
}


class RelevanceTests(unittest.TestCase):
    def test_cyrillic_term_with_context_is_relevant(self):
        s = score_text("НАТО відновить п'ять реабілітаційних центрів у межах проєкту «Реноватор»")
        self.assertEqual(s.term, "strong")
        self.assertEqual(s.status, "relevant")

    def test_inflected_cyrillic_forms(self):
        for word in ("Реноватора", "Реноватору", "Реноватором", "реноваторі"):
            self.assertEqual(score_text(f"у межах {word}").term, "strong", word)

    def test_tool_review_is_irrelevant(self):
        s = score_text("Best oscillating multi-tool 2026: Renovator review", query_strong=True)
        self.assertEqual(s.status, "irrelevant")
        self.assertIn("tools", s.negative)

    def test_home_renovation_is_irrelevant(self):
        s = score_text("Kitchen and bathroom renovator schemes for homeowners")
        self.assertEqual(s.status, "irrelevant")

    def test_title_without_term_from_strong_query(self):
        s = score_text("Латвія візьме на себе відновлення одного з військових госпіталів України",
                       query_strong=True)
        self.assertEqual(s.term, "none")
        self.assertEqual(s.status, "relevant")

    def test_context_alone_never_relevant(self):
        s = score_text("NATO allies fund military rehabilitation hospital in Ukraine, Latvia leads")
        self.assertNotEqual(s.status, "relevant")

    def test_page_term_upgrades_score(self):
        weak = score_text("Підсумки тижня", query_strong=True)
        strong = score_text("Підсумки тижня", query_strong=True, page_term="strong")
        self.assertGreater(strong.score, weak.score)

    def test_strong_latin_phrases(self):
        for t in ("Project Renovator", "Operation Renovator", "projekts Renovator", "the “Renovator” project"):
            self.assertEqual(score_text(t).term, "strong", t)
        self.assertEqual(score_text("a renovator in Ohio").term, "weak")

    def test_query_is_strong(self):
        self.assertTrue(query_is_strong("Реноватор"))
        self.assertTrue(query_is_strong("Renovator NATO"))
        self.assertTrue(query_is_strong("Renovator Ukraina"))
        self.assertFalse(query_is_strong("renovator"))
        self.assertFalse(query_is_strong("NATO hospital"))


# Заголовки для перевірки якості правил: (текст, запит_із_сильним_терміном, очікуваний статус).
# Частина випадків гіпотетична, але кожен відтворює реальний тип знахідки.
EVAL_CASES = [
    ("Литва очолить відновлення військового госпіталю в межах «Реноватора»", False, "relevant"),
    ("Norway to lead rehabilitation centre under NATO's Renovator project", False, "relevant"),
    ("Sweden joins NATO Renovator initiative for Ukraine", False, "relevant"),
    ("Latvija vadīs Ukrainas militārās slimnīcas atjaunošanu NATO projektā Renovator", False, "relevant"),
    ("Lietuva vadovaus NATO projektui „Renovator“ Ukrainoje", False, "relevant"),
    ("Sverige leder ett rehabiliteringscenter i Ukraina inom Nato-projektet Renovator", False, "relevant"),
    ("Norge skal lede et rehabiliteringssenter i Ukraina gjennom Renovator-prosjektet", False, "relevant"),
    ("UK hands over rehabilitation wards to Ukraine's Armed Forces", True, "relevant"),
    ("Командування Медичних сил ЗСУ: робоча група проєкту «Реноватор» провела засідання", False, "relevant"),
    ("This Old House renovator shares kitchen tips", False, "irrelevant"),
    ("Best cordless multi-tool: Renovator review", True, "irrelevant"),
    # Кириличний термін мовчки не відкидаємо: пропуск справжньої згадки дорожчий за зайву перевірку.
    ("ЖК «Реноватор» у Києві: забудовник оголосив старт продажів квартир", False, "uncertain_or_irrelevant"),
    ("Renovator: new season of the TV show premieres on Netflix", False, "irrelevant"),
    ("NATO allies discuss military hospitals in Ukraine", False, "uncertain_or_irrelevant"),
]


class EvalTests(unittest.TestCase):
    def test_eval_cases(self):
        for text, strong, expected in EVAL_CASES:
            got = score_text(text, query_strong=strong).status
            if expected == "uncertain_or_irrelevant":
                self.assertIn(got, ("uncertain", "irrelevant"), text)
            else:
                self.assertEqual(got, expected, text)


class TextUtilTests(unittest.TestCase):
    def test_canonical_url(self):
        self.assertEqual(canonical_url("http://www.Example.com/a/?utm_source=x&b=2&a=1#frag"),
                         "https://example.com/a?a=1&b=2")

    def test_title_key_strips_source_suffix(self):
        self.assertEqual(title_key("Five NATO nations lead effort - UK Defence Journal", "UK Defence Journal"),
                         title_key("Five NATO nations lead effort"))

    def test_parse_date_formats(self):
        self.assertEqual(parse_date("Tue, 07 Oct 2025 09:15:00 GMT"), "2025-10-07T09:15:00Z")
        self.assertEqual(parse_date("20251007T151500Z"), "2025-10-07T15:15:00Z")
        self.assertEqual(parse_date("2026-02-20T09:30:00.000+00:00"), "2026-02-20T09:30:00Z")
        self.assertEqual(parse_date("2026-03-01T10:00:00+02:00"), "2026-03-01T08:00:00Z")
        self.assertIsNone(parse_date("вчора"))


class ParserTests(unittest.TestCase):
    def test_rss_rejects_entities(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
        with self.assertRaises(ValueError):
            parse_feed(bomb)

    def test_bing_unwrap_and_source(self):
        items = parse_feed(fx("bing.xml"))
        self.assertEqual(items[0].source_name, "Censor.NET")
        self.assertEqual(bing_news.unwrap(items[0].link), "https://censor.net/en/news/3578351/nato-renovator")

    def test_telegram_parser(self):
        msgs = telegram.parse_channel(fx("telegram.html").decode())
        self.assertEqual([m["post"] for m in msgs], ["testchannel/101", "testchannel/102"])
        self.assertTrue(msgs[0]["text"].startswith("Проєкт «Реноватор»: передано обладнання до госпіталю"))
        self.assertIn("вкладений", msgs[0]["text"])
        self.assertEqual(msgs[0]["date"], "2026-03-01T10:00:00+00:00")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = test_config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_once(self, **kw):
        return pipeline.run(self.cfg, client=FakeClient(ROUTES), **kw)

    def test_end_to_end(self):
        res = self.run_once(notify_enabled=False)
        self.assertEqual(res.errors, [])
        reg = Registry(self.cfg["storage"]["registry"])
        by_title = {r["title"]: r for r in reg.all()}

        # Дублікат між GDELT (прямий URL) і Google News (агрегатор) злито в один запис.
        five = [r for r in reg.all() if "Five NATO nations" in r["title"]]
        self.assertEqual(len(five), 1)
        self.assertEqual(five[0]["url"].split("?")[0],
                         "https://ukdefencejournal.org.uk/five-nato-nations-lead-rehabilitation-effort-in-ukraine/")
        self.assertEqual(len(five[0]["found_via"]), 2)

        # АрміяInform з WordPress і з Google News теж злито (той самий домен і заголовок).
        army = [r for r in reg.all() if r["domain"] == "armyinform.com.ua"]
        self.assertEqual(len(army), 1)
        self.assertFalse(army[0]["url"].startswith("https://news.google.com"))

        self.assertEqual(effective_status(by_title["UK delivers modernised rehabilitation wards to Ukraine"]), "relevant")
        self.assertEqual(effective_status(by_title["Home renovation grants"]), "irrelevant")
        tool = [r for r in reg.all() if "multi-tool" in r["title"]][0]
        self.assertEqual(effective_status(tool), "irrelevant")

        # Telegram: повідомлення без терміна відсіяне, з терміном релевантне.
        tg = {r["url"]: r for r in reg.all() if r["domain"] == "t.me"}
        self.assertEqual(effective_status(tg["https://t.me/testchannel/101"]), "relevant")

        # Заголовок без терміна, але сторінка містить «Project Renovator»: перевірка підняла статус.
        wards = by_title["UK hands over final modernised medical rehabilitation wards"]
        self.assertEqual(wards["page_term"], "strong")
        self.assertIn("Project Renovator", wards["page_excerpt"])
        self.assertEqual(effective_status(wards), "relevant")
        self.assertNotIn("home_renovation", wards["negative"])  # <aside> вирізано

        # Експорт створено.
        self.assertTrue((Path(self.tmp.name) / "registry.csv").exists())
        self.assertTrue((Path(self.tmp.name) / "index.html").exists())

    def test_second_run_adds_nothing_and_keeps_manual(self):
        self.run_once(notify_enabled=False)
        reg = Registry(self.cfg["storage"]["registry"])
        rid = next(r["id"] for r in reg.all() if r["title"] == "Home renovation grants")
        reg.set_manual(rid, "relevant", "перевірено вручну")
        reg.save()
        res = self.run_once(notify_enabled=False)
        self.assertEqual(res.new, 0)
        reg = Registry(self.cfg["storage"]["registry"])
        self.assertEqual(effective_status(reg.records[rid]), "relevant")
        self.assertEqual(reg.records[rid]["notes"], "перевірено вручну")

    def test_source_failure_is_isolated(self):
        routes = dict(ROUTES)
        del routes["api.gdeltproject.org"]
        res = pipeline.run(self.cfg, client=FakeClient(routes), notify_enabled=False)
        self.assertTrue(any(e.startswith("gdelt") for e in res.errors))
        self.assertGreater(res.fetched, 0)

    def test_gdelt_plain_text_error(self):
        routes = dict(ROUTES)
        routes["api.gdeltproject.org"] = b"Your search contained a phrase that was too short."
        res = pipeline.run(self.cfg, client=FakeClient(routes), only=["gdelt"], notify_enabled=False)
        self.assertTrue(any("не JSON" in e for e in res.errors))

    def test_registry_file_is_valid_jsonl_and_sorted(self):
        self.run_once(notify_enabled=False)
        lines = Path(self.cfg["storage"]["registry"]).read_text(encoding="utf-8").splitlines()
        recs = [json.loads(l) for l in lines]
        keys = [(r["first_seen_at"], r["id"]) for r in recs]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len({r["id"] for r in recs}), len(recs))


class IdempotenceTests(unittest.TestCase):
    def test_repeat_run_same_day_leaves_files_identical(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = test_config(d)
            pipeline.run(cfg, client=FakeClient(ROUTES), notify_enabled=False)
            snap = {n: (Path(d) / n).read_bytes() for n in ("registry.jsonl", "registry.csv", "index.html")}
            pipeline.run(cfg, client=FakeClient(ROUTES), notify_enabled=False)
            for n, before in snap.items():
                self.assertEqual((Path(d) / n).read_bytes(), before, n)


class BreakerTests(unittest.TestCase):
    def test_host_skipped_after_repeated_network_failures(self):
        from renovator_monitor.fetch import HttpClient
        import urllib.error
        c = HttpClient(retries=0, default_interval=0)
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")) as op:
            for _ in range(5):
                with self.assertRaises(FetchError):
                    c.get("https://down.example/x")
        self.assertEqual(op.call_count, 3)


class ExportTests(unittest.TestCase):
    def rec(self, **kw):
        base = {"id": "abc", "url": "https://e.com/x", "title": "t", "first_seen_at": "2026-01-01T00:00:00Z",
                "found_via": [], "auto_status": "relevant", "score": 70}
        base.update(kw)
        return base

    def test_csv_formula_injection_guard(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.csv"
            report.write_csv([self.rec(title="=HYPERLINK(\"http://evil\")")], p)
            with p.open(encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
            self.assertTrue(rows[1][9].startswith("'="))

    def test_html_escapes_and_blocks_js_urls(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "i.html"
            report.write_html([self.rec(title="<script>alert(1)</script>", url="javascript:alert(1)")], p, "now")
            page = p.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert", page)
            self.assertNotIn("javascript:", page)


class NotifyTests(unittest.TestCase):
    def test_marks_only_after_success_and_splits(self):
        recs = [{"id": f"id{i}", "url": f"https://e.com/{i}", "title": "Реноватор " + "x" * 300,
                 "first_seen_at": "2026-01-01T00:00:00Z", "auto_status": "relevant", "score": 80,
                 "notified": False} for i in range(30)]
        sent_texts = []
        env = {"RENOVATOR_TG_TOKEN": "t", "RENOVATOR_TG_CHAT_ID": "c"}
        with mock.patch.dict("os.environ", env), \
             mock.patch.object(notify, "send_telegram", side_effect=lambda text, *a: sent_texts.append(text)):
            n = notify.notify_new(recs, False, [])
        self.assertEqual(n, 30)
        self.assertGreater(len(sent_texts), 1)
        self.assertTrue(all(len(t) <= 4096 for t in sent_texts))
        self.assertTrue(all(r["notified"] for r in recs))

    def test_failure_leaves_unsent(self):
        recs = [{"id": "a", "url": "https://e.com", "title": "x", "first_seen_at": "2026-01-01T00:00:00Z",
                 "auto_status": "relevant", "notified": False}]
        errors = []
        with mock.patch.dict("os.environ", {"RENOVATOR_TG_TOKEN": "t", "RENOVATOR_TG_CHAT_ID": "c"}), \
             mock.patch.object(notify, "send_telegram", side_effect=RuntimeError("мережа")):
            self.assertEqual(notify.notify_new(recs, False, errors), 0)
        self.assertFalse(recs[0]["notified"])
        self.assertTrue(errors)


class RegistryTests(unittest.TestCase):
    def test_prefix_resolution_and_bad_status(self):
        with tempfile.TemporaryDirectory() as d:
            reg = Registry(Path(d) / "r.jsonl")
            rec, _ = reg.upsert(RawMention(url="https://a.com/1", title="Реноватор", source="t", query="q"))
            self.assertEqual(reg.set_manual(rec["id"][:6], "irrelevant")["manual_status"], "irrelevant")
            with self.assertRaises(ValueError):
                reg.set_manual(rec["id"], "maybe")

    def test_corrupt_line_reports_position(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            p.write_text('{"id": "x"\n', encoding="utf-8")
            with self.assertRaises(ValueError) as cm:
                Registry(p)
            self.assertIn(":1:", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
