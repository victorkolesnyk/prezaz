"""Тести рушія на синтетичних даних. Запуск з теки vpmo:
    python3 -m unittest discover -s tests
"""
import datetime
import json
import os
import unittest

from pmo import compliance, gates, model, prioritize, report, tolerances as tl, trello

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
TODAY = datetime.date(2026, 10, 23)


def portfolio():
    return model.load(os.path.join(ROOT, "data", "pryklad_portfel.json"))


def project(pid):
    return next(p for p in portfolio()["projects"] if p["id"] == pid)


def boards():
    return trello.load_boards([os.path.join(HERE, "fixtures", "site1_pryklad.json")])


class TestModel(unittest.TestCase):
    def test_example_is_valid(self):
        self.assertEqual(model.validate(portfolio()), [])

    def test_validation_catches_errors(self):
        bad = {"portfolio": {"criteria": [{"key": "a", "weight": 0.7}]},
               "projects": [{"id": "X", "products": {"pid": "done"}},
                            {"id": "X", "risks": [{"id": "R", "probability": 7, "impact": 1}]}]}
        errors = model.validate(bad)
        self.assertEqual(len(errors), 4)

    def test_dates(self):
        self.assertEqual(model.parse_date("09.10.2026"), datetime.date(2026, 10, 9))
        self.assertEqual(model.parse_date("2026-10-09T12:00:00Z"), datetime.date(2026, 10, 9))
        self.assertIsNone(model.parse_date("—"))


class TestTrello(unittest.TestCase):
    def setUp(self):
        self.m = trello.metrics(boards()["SITE1 ПРИКЛАД"], TODAY)

    def test_counts(self):
        self.assertEqual(self.m["site"], "1")
        self.assertEqual(self.m["cards"], 7)
        self.assertEqual(self.m["done"], 1)
        self.assertEqual(self.m["max_milestone_slip"], 52)
        self.assertEqual(self.m["ea_zone_open"], 1)

    def test_register_defects(self):
        self.assertEqual([c["wbs"] for c in self.m["closed_parent_open_children"]], ["1"])
        self.assertEqual(self.m["branch_mismatch"][0]["wbs"], "2")
        self.assertEqual(self.m["broken_predecessors"], ["2.3"])

    def test_money_with_decimal_comma(self):
        self.assertEqual(trello.money("4 509 429,50 євро"), 4509429.5)


class TestTolerances(unittest.TestCase):
    def test_project_a(self):
        res = tl.evaluate(project("PR-A"), portfolio(), trello.metrics(boards()["SITE1 ПРИКЛАД"], TODAY))
        self.assertEqual(res["time"][0], tl.EXCEPTION)
        self.assertEqual(res["cost"][0], tl.AT_RISK)        # 45 000 з 50 000 = 90 %
        self.assertEqual(res["scope"][0], tl.AT_RISK)       # вилучено «should»
        self.assertEqual(res["risk"][0], tl.EXCEPTION)      # 4x5 без відповіді
        self.assertEqual(res["benefits"][0], tl.WITHIN)     # недобір 5 %
        self.assertEqual(res["sustainability"][0], tl.NO_DATA)
        self.assertEqual(tl.overall(res), tl.EXCEPTION)

    def test_cost_uses_contingency_when_no_explicit_tolerance(self):
        res = tl.evaluate(project("PR-B"), portfolio())
        self.assertEqual(res["cost"][0], tl.EXCEPTION)      # 14 000 понад резерв 10 000
        self.assertEqual(res["time"][0], tl.NO_DATA)

    def test_manual_slip(self):
        p = dict(project("PR-B"), progress={"time_slip_days": 25, "source": "протокол"})
        self.assertEqual(tl.evaluate(p, portfolio())["time"][0], tl.AT_RISK)


class TestGatesAndPrinciples(unittest.TestCase):
    def test_delivery_gate(self):
        name, gaps = gates.check(project("PR-A"))
        self.assertEqual(name, "Дозвіл на наступний етап")
        self.assertEqual(len(gaps), 1)
        self.assertIn("Звіт про завершення етапу", gaps[0])

    def test_initiation_gate_lists_missing_roles(self):
        name, gaps = gates.check(project("PR-B"))
        self.assertEqual(name, "Дозвіл на проєкт")
        self.assertTrue(any("Старший постачальник" in g for g in gaps))

    def test_principles_project_a(self):
        res = {n: ok for n, ok, _ in compliance.check(project("PR-A"), TODAY)}
        self.assertTrue(all(res.values()), res)


class TestFunding(unittest.TestCase):
    def scenario(self):
        with open(os.path.join(ROOT, "data", "pryklad_stsenarii.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_priority_order_and_dependencies(self):
        res = prioritize.fund(self.scenario())
        funded = {i["id"] for i in res["funded"]}
        self.assertEqual(funded, {"S-A.1", "S-A.2", "S-B.1", "S-B.2"})
        self.assertLessEqual(res["spent"], res["budget"])

    def test_dependency_pulled_in(self):
        sc = self.scenario()
        for i in sc["items"]:
            i["mandatory"] = i["id"] == "S-A.3"
        funded = [i["id"] for i in prioritize.fund(sc)["funded"]]
        self.assertEqual(funded[:3], ["S-A.3", "S-A.2", "S-A.1"])

    def test_rank_without_scores(self):
        r = prioritize.rank([{"id": "X", "scores": {}}], [{"key": "a", "weight": 1}])
        self.assertIsNone(r[0]["score"])


class TestReports(unittest.TestCase):
    def test_dashboard_has_no_colour_words(self):
        text = report.dashboard(portfolio(), boards(), TODAY)
        for word in ("червон", "жовт", "зелен", "RAG"):
            self.assertNotIn(word, text)
        self.assertIn("PR-A", text)

    def test_exception_report(self):
        text = report.exception_report(portfolio(), project("PR-A"), boards(), TODAY)
        self.assertTrue(text.startswith("# Звіт про виняток: PR-A"))
        self.assertIn("[2.3]", text)


if __name__ == "__main__":
    unittest.main()
