"""Aktogay sulphide concentrator model core (standard library only).

Modules:
  params       parameter table, ParamSet, PARAMETERS.md export
  state        plant state dataclasses, topology, deterministic randomness
  comminution  crusher, SAG (Morrell, Austin), pebble limit, ball mills (Bond), cyclones
  flotation    rougher/cleaner kinetics, grade, tails, thickener, filter, concentrate stock
  ore          pit blocks, block-model error, fleet, haul, belt, stockpile, batches
  utilities    power (grid limit, load shedding), water (pond, recycle), money
  events       scenarios, hidden causes, random stops, crews
  pit          trucks (state machine), faces, haul roads, stripping (on the aggregated haul)
  people       people of the shift: state, location, free time (crews and decisions)
  sensors      noise, analyser, laboratory, control alarm, instruments, measured features
  site_aktogay site passport (library vs site: people, fleet, faces, roads, instruments)
  plant        Plant (one copy) and CopySet (fact / base / loud / no_twin)
  calib        annual fit and checks against reports
"""

__version__ = "0.1.0"
