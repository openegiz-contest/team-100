"""akt-web helpers (web/server.py) that need no Ditto or InfluxDB."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
if WEB not in sys.path:
    sys.path.insert(0, WEB)

import server  # noqa: E402


class WebTest(unittest.TestCase):
    def test_control_patch_drops_stale_keys(self):
        # "Два сразу" left preset/kip/auto in control.scenario; the next scenario must not inherit them
        cur = {"seq": 5, "id": "fork", "preset": "fork", "kip": 1.0, "auto": 1.0, "run": "r", "sim_time": 495.0,
               "t_wall": 1.0}
        obj = {"seq": 6, "id": "crusher:1", "run": "r", "sim_time": 500.0, "t_wall": 2.0}
        patch = server.control_patch(cur, obj)
        self.assertEqual({k: v for k, v in patch.items() if v is not None}, obj)
        self.assertEqual({k for k, v in patch.items() if v is None}, {"preset", "kip", "auto"})
        self.assertEqual(server.control_patch(None, obj), obj)
        self.assertEqual(server.control_patch({}, obj), obj)

    def test_seq_never_restarts_when_ditto_does_not_answer(self):
        """A timed-out read of control.<f> must fail the command, not write seq 1 (the simulator would drop it)."""
        calls = []

        def fake(method, path, body=None, headers=None):
            calls.append((method, path))
            if method == "GET" and path.endswith("/features/scenario/properties/value"):
                raise server.UpstreamError(502, "Ditto unreachable: timed out")
            if method == "GET" and path.endswith("/features/speed/properties/value"):
                raise server.UpstreamError(404, "Ditto 404")
            if method == "GET":
                return "run-1" if "idSimulationRun" in path else 500.0
            return None

        old = server.ditto
        server.ditto = fake
        try:
            with self.assertRaises(server.UpstreamError):
                server.write_control("scenario", {"id": "hard:1"})
            self.assertFalse([c for c in calls if c[0] == "PATCH"])
            obj = server.write_control("speed", {"value": 300.0})      # no value yet (404): seq 1
            self.assertEqual(obj["seq"], 1)
        finally:
            server.ditto = old

    def test_annotated_csv(self):
        text = ("#datatype,string,long,double\r\n,result,table,_value\r\n,,0,1.5\r\n\r\n"
                ",result,table,_value\r\n,,1,2.5\r\n")
        self.assertEqual([r["_value"] for r in server.parse_annotated_csv(text)], ["1.5", "2.5"])

    def test_remind_writes_the_journal(self):
        """«Напомнить» / «Позвать следующего»: journal.last with action remind / next (the simulator acts on it)."""
        written = []
        old_seq, old_ditto = server.next_seq, server.ditto
        server.next_seq = lambda thing, feat: 7
        server.ditto = lambda method, path, body=None, headers=None: (
            written.append((method, path, body)) if method != "GET" else ("run-1" if "idSimulationRun" in path else 600.0))
        try:
            obj = server.write_journal("next", "issue-3", "Дежурный КИПиА", "не прибыл")
        finally:
            server.next_seq, server.ditto = old_seq, old_ditto
        self.assertEqual((obj["action"], obj["issue"], obj["seq"]), ("next", "issue-3", 7))
        self.assertIn('"remind"', open(os.path.join(WEB, "server.py"), encoding="utf-8").read())


class StaticTextTest(unittest.TestCase):
    """The new panels exist and say where their numbers come from."""

    def read(self, rel):
        with open(os.path.join(WEB, "static", rel), encoding="utf-8") as f:
            return f.read()

    def test_handover_view_and_question(self):
        v, h, a = self.read("views.js"), self.read("help.js"), self.read("app.js")
        self.assertIn("AKT.views.handover", v)
        self.assertIn("Plocher", v)                                   # literature, labelled as such
        self.assertIn("Что передать смене?", h)
        self.assertIn("['handover', 'Сдача смены']", a)
        self.assertIn("data-a=\"remind\"", v)
        self.assertIn("Позвать следующего", v)

    def test_diorama_freshness_of_pit_machines(self):
        c = self.read("diorama/core.js")
        self.assertIn("updateFresh", c)
        self.assertIn("обновлено", c)
        self.assertIn("modifiedAge", c)


if __name__ == "__main__":
    unittest.main()
