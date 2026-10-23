"""Entry point that works with isolated mode (python -I does not add the cwd to sys.path).

  python -I aktogay/run.py test [pattern]    unit tests (default pattern test_*.py)
  python -I aktogay/run.py calib [--quick]   calibration table and calib.json
  python -I aktogay/run.py params [--md PARAMETERS.md] [--check]
  python -I aktogay/run.py service [...]     simulator service akt-sim (sim/service.py)
  python -I aktogay/run.py trial [--n 100]   on/off trial of the issue queue (sim/trial.py)
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
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
