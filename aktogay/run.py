"""Entry point that works with isolated mode (python -I does not add the cwd to sys.path).

  python -I aktogay/run.py test [pattern]    unit tests (default pattern test_*.py)
  python -I aktogay/run.py calib [--quick]   calibration table and calib.json
  python -I aktogay/run.py params [--md PARAMETERS.md] [--check]
  python -I aktogay/run.py service [...]     simulator service akt-sim (sim/service.py)
  python -I aktogay/run.py trial [--n 100]   on/off trial of the issue queue (sim/trial.py)
  python -I aktogay/run.py backtest [--quick] quarterly back-test on the KAZ Minerals reports (sim/backtest.py)
  python -I aktogay/run.py oxide [--calibrate [--strict]] [--write PATH]  oxide chain: back-test of the heap on the cathode of the reports, calibration (sim/oxide.py)
  python -I aktogay/run.py replay --write PATH  replay file «с двойником / без» from the stored trial rows (sim/replay.py)
  python -I aktogay/run.py fidelity [--only ...]  availability, relines, forward test 2026, recovery refit, ore spread (sim/fidelity.py)
  python -I aktogay/run.py influence [--screen-n 8]  which parameters can change the conclusions (sim/influence.py)
  python -I aktogay/run.py haul [--calibrate]  truck cycle from the map distance (sim/haul.py)
  python -I aktogay/run.py plausibility [--write PATH]  invariants of the live check on the page «Калибровка» (sim/plausibility.py)
  python -I aktogay/run.py exp23 --write PATH  compact file of the experiment of 24.10.2026 for the pages (sim/exp23_view.py)
  python -I aktogay/run.py exp24 --write PATH  symmetric people / twin base: summary of sim/data/exp24/*.json (sim/exp24.py, VALIDATION 8.17)
  python -I aktogay/run.py detect_eval --seeds 25 --jobs 4 --write PATH  detection share, latency, node and role matrix of «Где теряется медь» (sim/detect_eval.py)
  python -I aktogay/run.py cusum_eval --write PATH  false alarms of the CUSUM against the stated 0.95 a week, threshold curve (sim/cusum_eval.py)
  python -I aktogay/run.py stock_sens --write PATH  two readings of the PEK ore stockpile volume: scenarios under live 40 kt and 163 kt (sim/stock_sens.py)
  python -I aktogay/run.py verify --write PATH  expected shift result of every catalog scenario, computed beforehand (sim/verify.py)
  python -I aktogay/run.py audit --write PATH   independent audit of ore, copper, energy and water balances of every scenario (sim/audit.py)
  python -I aktogay/run.py paramstat [--write PATH]  labels of the parameter tables: fact / vendor / analog / project / calc / assumption
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "test"
    rest = argv[1:]
    if cmd == "test":
        import unittest
        pattern = rest[0] if rest else "test_*.py"
        suite = unittest.defaultTestLoader.discover(os.path.join(HERE, "tests"), pattern=pattern,
                                                    top_level_dir=HERE)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        return 0 if result.wasSuccessful() else 1
    if cmd == "calib":
        from sim import calib
        return calib.main(rest)
    if cmd == "params":
        from sim import params
        return params.main(rest)
    if cmd == "service":
        from sim import service
        return service.main(rest)
    if cmd == "trial":
        from sim import trial
        return trial.main(rest)
    if cmd == "backtest":
        from sim import backtest
        return backtest.main(rest)
    if cmd == "oxide":
        from sim import oxide
        return oxide.main(rest)
    if cmd == "paramstat":
        from sim import paramstat
        return paramstat.main(rest)
    if cmd == "replay":
        from sim import replay
        return replay.main(rest)
    if cmd == "fidelity":
        from sim import fidelity
        return fidelity.main(rest)
    if cmd == "influence":
        from sim import influence
        return influence.main(rest)
    if cmd == "haul":
        from sim import haul
        return haul.main(rest)
    if cmd == "plausibility":
        from sim import plausibility
        return plausibility.main(rest)
    if cmd == "exp23":
        from sim import exp23_view
        return exp23_view.main(rest)
    if cmd == "exp24":
        from sim import exp24
        return exp24.main(rest)
    if cmd == "detect_eval":
        from sim import detect_eval
        return detect_eval.main(rest)
    if cmd == "cusum_eval":
        from sim import cusum_eval
        return cusum_eval.main(rest)
    if cmd == "stock_sens":
        from sim import stock_sens
        return stock_sens.main(rest)
    if cmd == "verify":
        from sim import verify
        return verify.main(rest)
    if cmd == "audit":
        from sim import audit
        return audit.main(rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
