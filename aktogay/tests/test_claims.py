"""Registry of headline numbers (web/static/claims.json) and the checker scripts/check_numbers.py."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import check_numbers as cn  # noqa: E402

STATIC = os.path.join(ROOT, "web", "static")


class RegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(cn.CLAIMS, encoding="utf-8") as f:
            cls.reg = json.load(f)

    def test_every_claim_has_an_experiment_and_a_kind(self):
        for c in self.reg["claims"]:
            self.assertIn(c["experiment"], self.reg["experiments"], c["id"])
            self.assertIn(c["check"], self.reg["check_kinds"] if c["check"] != "literature" else ("literature", "auto", "history", "manual"), c["id"])
            if c["check"] in ("manual", "history") and not c.get("source"):
                self.assertTrue(c.get("note"), c["id"] + ": a claim without a computation says why")

    def test_ids_are_unique(self):
        ids = [c["id"] for c in self.reg["claims"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_automatic_claims_hold(self):
        bad, _warn = cn.check_claims(self.reg)
        self.assertEqual(bad, [])

    def test_no_unmarked_number_in_the_documents(self):
        unmarked, listing, _concept = cn.scan(self.reg)
        self.assertGreater(len(listing), 100)
        self.assertEqual(unmarked, [], "numbers not in claims.json: %s" % unmarked[:5])

    def test_concept_numbers_are_in_the_registry(self):
        """The Concept section is the participant's text: it is read, never edited; a number there that the registry does not hold
        (or holds with another value) is reported by the checker to the owner."""
        _unmarked, _listing, concept = cn.scan(self.reg)
        self.assertGreaterEqual(len(concept), 4)
        missing = [t for t, ids, _c in concept if not ids]
        self.assertEqual(missing, [])

    def test_a_number_not_in_the_registry_is_caught(self):
        tokens = cn.tokens_in("двойник даёт +9,99 т за смену и ещё +8,88 т", html=False)
        self.assertEqual([t for t, _c in tokens], ["+9,99", "+8,88"])
        reg = {"claims": [{"id": "x", "text": "+9,99", "check": "manual", "experiment": "e"}]}
        held = {t for c in reg["claims"] for t in cn.tokens_of(c)}
        self.assertEqual([t for t, _c in tokens if t not in held], ["+8,88"])

    def test_interval_numbers_are_scanned(self):
        t = [x for x, _c in cn.tokens_in("эффект [95 % ДИ +0,89; +1,31] и ещё [−0,02; +0,03]")]
        self.assertEqual(t, ["+0,89", "+1,31", "−0,02", "+0,03"])

    def test_formatting(self):
        self.assertEqual(cn.fmt(1.074, 2), "+1,07")
        self.assertEqual(cn.fmt(-0.001, 2), "−0,00")
        self.assertEqual(cn.fmt(-41.63, 0), "−42")

    def test_scenario_and_fork_claims_follow_verify_json(self):
        v = {(r["id"], r["kip"]): r for r in json.load(open(os.path.join(STATIC, "verify.json"), encoding="utf-8"))["runs"]}
        c = {c["id"]: c for c in self.reg["claims"]}
        self.assertEqual(c["fork_all_k1"]["text"], cn.fmt(v[("fork", 1)]["fork_cu_t"]["total_cu_t"], 2))
        self.assertEqual(c["sc_c3"]["text"], cn.fmt(v[("hard:1", 1)]["diff"]["fact"]["cu_t"], 2))

    def test_experiments_are_told_apart(self):
        """The same quantity («вклад порядка») comes from different experiments, and each of them is named."""
        kinds = {c["experiment"] for c in self.reg["claims"] if c["id"] in ("e4_ord_k1", "fork_order_k1", "h2210_order")}
        self.assertEqual(kinds, {"e4_crews", "scen_seed42", "legacy_22_10"})
        self.assertIn("иллюстрация", self.reg["experiments"]["scen_seed42"]["kind"])

    def test_stop_list_catches_what_the_evidence_does_not_carry(self):
        bad = {
            "twin_gives_1_07": "Двойник даёт +1,07 т Cu за смену на фабрике.",
            "kio_hours": "КИО 0,78 означает, что дробилка работает 78 % часов.",
            "crusher_bottleneck": "Дробилка — узкое место фабрики.",
            "line_hour_price_checked": "Цена часа линии в двойнике сверена с отчётами KAZ.",
            "reline_reproduced": "Перефутеровка воспроизведена на модели.",
            "reline_hours_claims": "Перефутеровка стоила 109 ч по отчётам.",
            "formula_beats_constant": "Формула извлечения прогнозирует лучше константы на полугодиях и годах, 4 из 4.",
            "zigzag_is_noise": "Зигзаг извлечения — шум отчётности.",
            "first_in_world": "Двойник такого рода впервые в мире.",
            "only_18_assumptions": "Только 18 допущений влияют на вывод.",
            "sensors_realistic": "Датчики реалистичны и несут погрешность по паспортам вендора.",
            "sag_energy_pinned": "Удельная энергия SAG зажата фактами 6,6–7,27 кВт·ч/т.",
            "maintenance_downtime_as_proof": "KAZ Minerals называет «reduced maintenance downtime», что подтверждает эффект двойника.",
        }
        for fid, text in bad.items():
            self.assertIn(fid, [h[0] for h in cn.forbidden_hits(text)], fid)

    def test_stop_list_lets_negations_and_history_through(self):
        ok = ("Писать «цена часа линии сверена с отчётами» нельзя.",
              "Мы не пишем, что КИО 0,78 означает 78 % часов.",
              "Прежняя база (--twin-human none): двойник − опытный +1,07 [+0,89; +1,31] [оценка на модели].",
              "Опыт 22.10.2026 дал +1,26, это историческая запись.",
              "Твёрдую руду «как сейчас» видят при начале выемки, ≈ 2 ч, до SAG — ≈ 245 мин.",
              "Вывод «дробилка — узкое место» неверно писать без паспорта.")
        for text in ok:
            self.assertEqual(cn.forbidden_hits(text), [], text)

    def test_emphasis_marks_do_not_hide_a_negation(self):
        self.assertEqual(cn.forbidden_hits("Мы **не** пишем «зигзаг — шум отчётности»."), [])

    def test_documents_have_no_forbidden_statement(self):
        hits, _concept = cn.scan_forbidden()
        self.assertEqual(hits, [], hits[:3])

    def test_page_shows_experiment_and_status(self):
        pages = open(os.path.join(STATIC, "pages.js"), encoding="utf-8").read()
        self.assertIn("claims.json", pages)
        self.assertIn("ht-claims", pages)


if __name__ == "__main__":
    unittest.main()
