"""Runs of the symmetric people / twin base of 24.10.2026 (VALIDATION 8.17), one after another, 4 worker processes, below normal priority.

python -I -B -X utf8 aktogay/sim/data/exp24/run_exp24.py [NAME ...]   (from the folder that holds aktogay/); finished files are skipped.
Then: python -I aktogay/run.py exp24 --write aktogay/sim/data/experiment_24.json

R1 / R2   the symmetric base (--twin-human same), hard ore seen by "как сейчас" at the start of digging, seeds 1001 and 2001 (headline)
R3 / R4   the same with hard ore seen by "как сейчас" only when the block feeds the SAG (--asis-hard sag), the other edge
R5 / R5b  control: --twin-human none, the asymmetric base of 8.8 on the merged code (must reproduce +1.07 on seeds 1001)
R6 / R6b  R1 / R2 under the other reading of the PEK stockpile sentence (live 163 kt, VALIDATION 8.16)
R7 / R7b  R3 / R4 under the same reading
Reading B of the stockpile is the command of `sim/stock_sens.py` (TRIAL_CMD): live 163 kt, the start level of each pile at the same share.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(SIM))
sys.path.insert(0, os.path.dirname(os.path.dirname(SIM)))
from sim import trial  # noqa: E402

try:
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL
except Exception:
    pass

JOBS = "4"
BASE = ["--library", "tier_s", "--copies", "base,by_value,by_loud,no_twin,novice,value_nd"]
STOCK_B = ["--set", "stock_live_t=163000", "--set", "stock1_t0=47270", "--set", "stock2_t0=122250"]
SAG = ["--asis-hard", "sag"]
JOBS_LIST = [
    ("R1_same_dig_s1001", BASE + ["--seed0", "1001"]),
    ("R2_same_dig_s2001", BASE + ["--seed0", "2001"]),
    ("R3_same_sag_s1001", BASE + SAG + ["--seed0", "1001"]),
    ("R4_same_sag_s2001", BASE + SAG + ["--seed0", "2001"]),
    ("R5_none_dig_s1001", BASE + ["--twin-human", "none", "--seed0", "1001"]),
    ("R6_same_dig_stockB_s1001", BASE + STOCK_B + ["--seed0", "1001"]),
    ("R5b_none_dig_s2001", BASE + ["--twin-human", "none", "--seed0", "2001"]),
    ("R6b_same_dig_stockB_s2001", BASE + STOCK_B + ["--seed0", "2001"]),
    ("R7_same_sag_stockB_s1001", BASE + SAG + STOCK_B + ["--seed0", "1001"]),
    ("R7b_same_sag_stockB_s2001", BASE + SAG + STOCK_B + ["--seed0", "2001"]),
]


def main():
    only = set(sys.argv[1:])
    for name, args in JOBS_LIST:
        out = os.path.join(HERE, name + ".json")
        if os.path.exists(out) or (only and name not in only):
            continue
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] start {name}", flush=True)
        argv = ["--n", "100", "--jobs", JOBS] + args + ["--out", out + ".part"]
        trial.main(argv)
        os.replace(out + ".part", out)
        print(f"[{time.strftime('%H:%M:%S')}] done {name} in {time.time() - t0:.0f} s", flush=True)
    print("all done", flush=True)


if __name__ == "__main__":
    main()
