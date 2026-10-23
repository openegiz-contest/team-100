"""Analysis modules of the Aktogay stand (akt-modules): losses, ore forecast, issue queue.

They read Ditto over HTTP and InfluxDB over Flux/HTTP only, never the
simulator, and write their own things (mod-losses, mod-ore, mod-priority,
issue-*) through Ditto merge commands. Standard library only.

  params    parameter table of the expectation model (own numbers, with sources)
  expect    formulas: SAG energy, Bond grind, flotation chain, two-product, money
  cusum     one-sided CUSUM with a fast threshold
  policy    rank(troubles, now, prm): pure queue policy (safety, time bands, money)
  clients   Ditto and InfluxDB HTTP clients
  store     latest snapshot and model-time windows of the things read
  writer    feature writer with type coercion from setup/things.json
  losses    "where copper is lost": expectation vs measurement per node
  ore       "which ore is coming": stockpile window model, 12 h forecast, hindsight check
  priority  "queue of issues": troubles -> policy -> issue-* and mod-priority
  main      runner: polling, model-time tacts, barrier, resend
"""

__version__ = "0.1.0"
