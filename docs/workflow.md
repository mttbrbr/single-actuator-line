# Workflow and acceptance checks

1. Source OpenFOAM.com v2412 and run `python3 tools/generate_case.py`.
2. Run `scripts/check_environment.sh` and compile turbinesFoam v0.3.0 for
   v2412 with `scripts/build_turbinesfoam.sh` if required.
3. Run `scripts/mesh.sh`. Production mesh acceptance requires `Mesh OK` and
   4.5–5.5 million cells.
4. Install the pinned Python dependencies and run
   `python3 tools/generate_mann_inflow.py`. Inspect
   `case/constant/boundaryData/manifest.json`; realised longitudinal TI must be
   10% after the documented uniform realisation scaling. The manifest also
   preserves the raw TI and scale factor.
5. Use `scripts/run_smoke.sh` after code changes. It deliberately leaves smoke
   dictionaries in place; `run_production.sh` regenerates production ones.
6. Run production with `scripts/run_production.sh`. The script refuses to run
   without both an accepted mesh and Mann manifest.
7. Run `python3 tools/postprocess_wakes.py` after completion. Cutting-plane VTK
   data remain under `case/postProcessing/wakePlanes` for detailed wake-width
   and meandering analysis.

The production estimate is 24,000 time steps over roughly five million cells.
The included 12-rank decomposition matches the local physical-core count, but
the same case can be moved to a cluster by changing `run.n_processors` and
regenerating the dictionaries.

Generated Mann data can exceed hundreds of megabytes. `scripts/clean.sh`
retains it while removing mesh, solver times and logs.

