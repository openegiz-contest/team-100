"""The novice runs of VALIDATION 8.9-8.10 on the symmetric people / twin base (8.17): the same four runs as `exp23/run_exp23.py`
(nov_main, nov_rep, nov_lo, nov_hi), now with --twin-human same, so that «двойник − опытный» and «новичок с двойником − опытный» are
counted on the base where the twin is added to the people. «Опытный − новичок» does not involve the twin and is not expected to move.

python -I -B -X utf8 aktogay/sim/data/exp24/run_nov24.py [NAME ...]   (from the folder that holds aktogay/); finished files are skipped.
Then: python -I aktogay/run.py exp24 --write aktogay/sim/data/experiment_24.json   (the block `novice` reads exp24/nov24/*.json).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(SIM))
from sim import trial  # noqa: E402

try:
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL
except Exception:
    pass

OUT_DIR = os.path.join(HERE, "nov24")
JOBS = "3"
FULL = ["--library", "tier_s"]
NOV_LO = ["--set", "nov_detect_mult=1.0", "--set", "nov_detect_sigma_ln=0", "--set", "nov_p_diag=0.009", "--set", "nov_p_step=0.00099",
          "--set", "nov_steps=5", "--set", "nov_stress_mult=1.0"]
NOV_HI = ["--set", "nov_detect_mult=2.6", "--set", "nov_detect_sigma_ln=0.25", "--set", "nov_p_diag=0.236", "--set", "nov_p_step=0.0079",
          "--set", "nov_steps=20", "--set", "nov_stress_mult=4.0"]
JOBS_LIST = [
    ("nov_main", FULL + ["--copies", "base,by_value,no_twin,novice,nov_det,nov_err,nov_r,nov_twin", "--seed0", "1001"]),
    ("nov_rep", FULL + ["--copies", "base,by_value,no_twin,nov_r,nov_twin", "--seed0", "2001"]),
    ("nov_lo", FULL + ["--copies", "by_value,no_twin,nov_r,nov_twin", "--seed0", "1001"] + NOV_LO),
    ("nov_hi", FULL + ["--copies", "by_value,no_twin,nov_r,nov_twin", "--seed0", "1001"] + NOV_HI),
]


def main():
    only = set(sys.argv[1:])
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, args in JOBS_LIST:
        out = os.path.join(OUT_DIR, name + ".json")
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
