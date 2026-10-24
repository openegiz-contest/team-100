"""Modules keep up with the simulator under load (24.10): a module takes the newest point that every thing of its reads
has reached, skips the older ones, and a point that is still being published does not hold it back."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from modules import losses, main as mod_main, ore, priority  # noqa: E402
from modules.store import NO_VALUE  # noqa: E402

RUN = ms.RUN


def half_published(t_old, t_new, new_names):
    """A search in the middle of a point: new_names already at t_new, the others still at t_old."""
    out = []
    for it in ms.snapshot(t_old, run=RUN):
        name = it["thingId"].split(":", 1)[1]
        out.append(ms.item(name, {}, t_new, run=RUN) if name in new_names else it)
    return out


class NewestCompletePointTest(unittest.TestCase):
    def runner(self):
        r = mod_main.Runner(dry_run=True)
        r.store.update_from_search(ms.snapshot(480.0, run=RUN))
        r.on_new_run(RUN)
        return r

    def test_point_in_the_middle_of_publishing_does_not_stall(self):
        """The simulator already shows 590 on a few things, the rest is at 585: the module takes 585, not nothing."""
        r = self.runner()
        r.store.update_from_search(ms.snapshot(585.0, run=RUN))
        r.store.update_from_search(half_published(585.0, 590.0, {"site", "sag-1", "line-1"}))
        self.assertEqual(r.due(r.losses, losses.READS, losses.READS_TYPES), 585.0)
        self.assertTrue(r.incomplete, "the newer point is on its way: read again soon")

    def test_jumps_over_stale_points(self):
        """The module stood at 480; the twin is at 700 now: one tact at 700, not 44 tacts of catching up."""
        r = self.runner()
        r.losses.processed = 480.0
        r.store.update_from_search(ms.snapshot(700.0, run=RUN))
        self.assertEqual(r.due(r.losses, losses.READS, losses.READS_TYPES), 700.0)
        self.assertEqual(r.due(r.ore, ore.READS, ore.READS_TYPES), 690.0)          # ore tact is 15 min

    def test_never_goes_back_and_never_repeats(self):
        r = self.runner()
        r.losses.processed = 585.0
        r.store.update_from_search(half_published(585.0, 590.0, {"site"}))
        self.assertEqual(r.due(r.losses, losses.READS, losses.READS_TYPES), NO_VALUE)

    def test_priority_point_follows_the_two_modules_not_an_old_point(self):
        r = self.runner()
        r.losses.processed, r.ore.processed = 700.0, 690.0
        self.assertEqual(r.priority_point(705.0), 700.0)                            # not past losses
        r.losses.processed, r.ore.processed = 700.0, 600.0
        self.assertEqual(r.priority_point(700.0), 610.0)                            # ore is 15-min tact: at most 10 min ahead of it
        r.losses.processed = NO_VALUE
        self.assertEqual(r.priority_point(700.0), NO_VALUE)
        r.losses.processed, r.ore.processed, r.priority.processed = 700.0, 690.0, 700.0
        self.assertEqual(r.priority_point(700.0), NO_VALUE)

    def test_a_thing_that_stopped_publishing_holds_the_point_at_its_own_time(self):
        """water stays at 480 while the rest is at 585: the point is 480 (the newest every thing has reached)."""
        r = self.runner()
        items = [it for it in ms.snapshot(585.0, run=RUN) if not it["thingId"].endswith(":water")]
        r.store.update_from_search(items)
        self.assertEqual(r.due(r.losses, losses.READS, losses.READS_TYPES), 480.0)


class LagIndicatorTest(unittest.TestCase):
    def test_interface_reads_lag_from_processed_sim_time(self):
        root = os.path.join(ROOT, "web", "static")
        with open(os.path.join(root, "app.js"), encoding="utf-8") as f:
            app = f.read()
        for w in ("AKT.moduleLag", "AKT.maxLag", "processed_sim_time", "модули отстают на", "AKT.LAG_WARN"):
            self.assertIn(w, app, w)
        with open(os.path.join(root, "index.html"), encoding="utf-8") as f:
            idx = f.read()
        self.assertIn('id="now-eff"', idx)


if __name__ == "__main__":
    unittest.main()
