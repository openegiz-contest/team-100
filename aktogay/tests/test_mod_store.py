"""Module store and runner on a run change: an old run must not hold the new one back."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import mod_support as ms  # noqa: E402
from modules import losses  # noqa: E402
from modules import main as mod_main  # noqa: E402
from modules.store import NO_VALUE  # noqa: E402

OLD, NEW = "s42-free-0001", "s42-scen-0002"


def mixed(t_old, t_new, new_names):
    """Search result: new_names already republished at t_new in run NEW, the rest still at t_old in run OLD."""
    items = []
    for it in ms.snapshot(t_old, run=OLD):
        name = it["thingId"].split(":", 1)[1]
        items.append(ms.item(name, {}, t_new, run=NEW) if name in new_names else it)
    return items


class StoreRunChangeTest(unittest.TestCase):
    def runner(self):
        r = mod_main.Runner(dry_run=True)
        r.store.update_from_search(ms.snapshot(615.0, run=OLD))
        r.on_new_run(OLD)
        return r

    def test_old_run_sim_time_does_not_leak(self):
        r = self.runner()
        self.assertEqual(r.store.sim_time("sag-1"), 615.0)
        # the site starts the new run (warm-up announcement), the others are still in the old run
        r.store.update_from_search(mixed(615.0, 0.0, {"site"}))
        self.assertEqual(r.store.run_id, NEW)
        r.on_new_run(NEW)
        for _ in range(2):                       # a second poll used to restore 615 from the old run
            r.store.update_from_search(mixed(615.0, 0.0, {"site"}))
            self.assertEqual(r.store.sim_time("sag-1"), NO_VALUE)
            self.assertEqual(r.due(r.losses, losses.READS, losses.READS_TYPES), NO_VALUE)
        # the new run republishes everything at 08:00: the point is 480, not 615
        r.store.update_from_search(ms.snapshot(480.0, run=NEW))
        self.assertEqual(r.store.max_sim_time(losses.READS), 480.0)
        self.assertEqual(r.due(r.losses, losses.READS, losses.READS_TYPES), 480.0)

    def test_lost_batch_delete_does_not_stall_the_modules(self):
        """22.10: three DONE batches kept sim_time 940 after their deletes were lost; every tact waited
        for them (modules stood at 15:35 while the site ran on). An orphan no longer holds a point."""
        r = self.runner()
        r.on_new_run(NEW)
        orphan = ms.batch_item(940.0, "batch-0003", 2, "DONE", run=NEW)
        r.store.update_from_search(ms.snapshot(940.0, run=NEW, batches=[{"name": "batch-0009", "line": 1, "state": "IN_STOCK"}])
                                   + [orphan])
        items = ms.snapshot(1620.0, run=NEW, batches=[{"name": "batch-0009", "line": 1, "state": "IN_STOCK"}]) + [orphan]
        r.store.update_from_search(items)
        ok, tmax = r._reads_complete(losses.READS, losses.READS_TYPES, 1620.0)
        self.assertTrue(ok)
        self.assertEqual(r.due(r.losses, losses.READS, losses.READS_TYPES), 1620.0)

    def test_batch_alone_does_not_complete_a_point(self):
        r = self.runner()
        items = mixed(615.0, 390.0, {"site"})
        items.append(ms.batch_item(390.0, "batch-0001", 1, "PLANNED", run=NEW))
        r.store.update_from_search(items)
        r.on_new_run(NEW)
        r.store.update_from_search(items)
        ok, _ = r._reads_complete(losses.READS, losses.READS_TYPES, 0.0)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
