"""Test helpers shared by all test files."""
import functools
import os

from sim import params

SLOW = os.environ.get("AKT_SLOW") == "1"


def needs_impl(fn):
    """Skip (not fail) while the code under test still raises NotImplementedError."""
    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        try:
            return fn(self, *a, **k)
        except NotImplementedError as e:
            self.skipTest("not implemented yet" + (f": {e}" if str(e) else ""))
    return wrapper


def prm(**overrides):
    """Fresh ParamSet with optional overrides."""
    return params.default().copy(**overrides)
