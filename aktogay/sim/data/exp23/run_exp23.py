"""Runs of the experiment of 24.10.2026 (VALIDATION 8.6), one after another, 4 worker processes, below normal priority.

python -I -B -X utf8 aktogay/sim/data/exp23/run_exp23.py   (from the folder that holds aktogay/); finished files are skipped.
Then: python -I aktogay/run.py trial --aggregate aktogay/sim/data/exp23 --out aktogay/sim/data/experiment_23.json
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
FULL = ["--library", "tier_s"]
SEEDS = list(range(1001, 1101))
JOBS_LIST = [
    ("legacy_check", ["--no-twin"]),                                       # code of 22.10 settings: must equal trial_n100.json
    ("main_full", FULL + ["--copies", "base,by_value,by_loud,no_twin,novice,value_nd"]),
    ("crews1", FULL + ["--crews", "1", "--copies", "by_value,by_loud,no_twin,value_nd"]),
    ("crews2", FULL + ["--crews", "2", "--copies", "by_value,by_loud,no_twin,value_nd"]),
    ("crews3", FULL + ["--crews", "3", "--copies", "by_value,by_loud,no_twin,value_nd"]),
    ("main_base", ["--copies", "base,by_value,by_loud,no_twin,novice,value_nd"]),
]
for h, dl in ((2, 0), (6, 4), (12, 10), (24, 22), (4, 2)):
    JOBS_LIST.append((f"lab_{h}", FULL + ["--copies", "by_value,no_twin", "--set", f"sens_lab_delay_h={dl}"]))
for d in (0, 15, 30, 60, 120):
    JOBS_LIST.append((f"delay_{d}", FULL + ["--copies", "base,by_value", "--call-delay", str(d)]))
cfg_full = dict(trial.DEFAULTS, library="tier_s")
for kd in ("crusher", "trip", "dose", "cyclone", "hard", "grid", "reline"):
    seeds = [s for s in SEEDS if any(t.kind == kd for t in trial.draw_shift(s, cfg_full).troubles)]
    JOBS_LIST.append((f"delaykind_{kd}", FULL + ["--copies", "base,by_value", "--call-delay", "60", "--delay-kinds", kd,
                                                  "--seeds", ",".join(map(str, seeds))]))
for tag, extra in (("tor_comp50", ["--compliance", "0.5"]), ("tor_comp75", ["--compliance", "0.75"]),
                   ("tor_err2", ["--est-sigma", "0.4"]), ("tor_det150", ["--detect-min", "150"])):
    JOBS_LIST.append((tag, FULL + ["--copies", "by_value,no_twin"] + extra))
JOBS_LIST.append(("rep_full", FULL + ["--seed0", "2001", "--copies", "base,by_value,by_loud,no_twin,novice,value_nd"]))

# Novice from data (VALIDATION 8.9, pre-registered before the first run of 24.10.2026 03:09): nov_det, nov_err, nov_r, nov_twin
NOV_LO = ["--set", "nov_detect_mult=1.0", "--set", "nov_detect_sigma_ln=0", "--set", "nov_p_diag=0.009", "--set", "nov_p_step=0.00099",
          "--set", "nov_steps=5", "--set", "nov_stress_mult=1.0"]
NOV_HI = ["--set", "nov_detect_mult=2.6", "--set", "nov_detect_sigma_ln=0.25", "--set", "nov_p_diag=0.236", "--set", "nov_p_step=0.0079",
          "--set", "nov_steps=20", "--set", "nov_stress_mult=4.0"]
JOBS_LIST.append(("nov_main", FULL + ["--copies", "base,by_value,no_twin,novice,nov_det,nov_err,nov_r,nov_twin"]))
JOBS_LIST.append(("nov_lo", FULL + ["--copies", "by_value,no_twin,nov_r,nov_twin"] + NOV_LO))
JOBS_LIST.append(("nov_hi", FULL + ["--copies", "by_value,no_twin,nov_r,nov_twin"] + NOV_HI))
JOBS_LIST.append(("nov_rep", FULL + ["--seed0", "2001", "--copies", "base,by_value,no_twin,nov_r,nov_twin"]))

# Added 24.10.2026 after the first runs (VALIDATION 8.7 item 3 left the tier S kinds out of B1 by kind): the same method for roping, pH drift,
# HPGR and mantle change, so every trouble card has the price of an hour of delay; and the alarm-like events of the shift (modules/flood.py).
JOBS_LIST.append(("flood", FULL + ["--copies", "no_twin,by_value", "--alarms", "no_twin,by_value"]))
# Descriptive, not pre-registered: the slope of recovery on P80 of the Bozshakol analog (laboratory 1.2, plant regression 1.95 pp per 10 um)
# instead of the stand's 0.3 (assumption); the same copies and 5-minute cycle as the tornado base lab_4.
for tag, slope in (("sens_p80_12", "1.2"), ("sens_p80_195", "1.95")):
    JOBS_LIST.append((tag, FULL + ["--copies", "by_value,no_twin", "--set", "flot_p80_pp_10um=" + slope]))
for kd in ("roping", "phdrift", "hpgr", "mantle"):
    seeds = [s for s in SEEDS if any(t.kind == kd for t in trial.draw_shift(s, cfg_full).troubles)]
    JOBS_LIST.append((f"delaykind_{kd}", FULL + ["--copies", "base,by_value", "--call-delay", "60", "--delay-kinds", kd,
                                                  "--seeds", ",".join(map(str, seeds))]))

def main():
    only = set(sys.argv[1:])
    for name, args in JOBS_LIST:
        out = os.path.join(HERE, name + ".json")
        if os.path.exists(out) or (only and name not in only):
            continue
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] start {name}", flush=True)
        argv = ["--n", "100", "--seed0", "1001", "--jobs", JOBS] + args + ["--out", out + ".part"]
        trial.main(argv)
        os.replace(out + ".part", out)
        print(f"[{time.strftime('%H:%M:%S')}] done {name} in {time.time() - t0:.0f} s", flush=True)
    print("all done", flush=True)


if __name__ == "__main__":
    main()
