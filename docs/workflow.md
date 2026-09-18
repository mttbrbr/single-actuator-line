# Workflow and acceptance checks

1. Source the intended OpenFOAM.com v2412 environment.
2. Ensure $FOAM_USER_LIBBIN/libturbinesFoam.so already exists. No ALM source
   checkout or build step belongs to this repository.
3. Run python3 tools/generate_case.py and
   python3 -m unittest discover -s tests -v.
4. Run scripts/mesh.sh. Acceptance requires:
   - Mesh OK;
   - 6.6–6.8 million cells;
   - all cells hexahedral;
   - maximum non-orthogonality at numerical zero.
5. Generate the Mann box with python3 tools/generate_mann_inflow.py.
   Confirm that its duration covers the complete run and that the realised
   longitudinal TI is 10% in
   boundaryData/manifest.json.
6. Run scripts/check_environment.sh, prepare the Mann initial directory and
   execute pimpleFoam -dry-run before a production launch.
7. Run scripts/run_production.sh for the 57.5 s, 12-rank calculation.
8. Post-process the T1 performance CSV and wake samples over 28.75–57.5 s.

In-solver rendering remains disabled in `config/case.yaml`: VTK/X11 rendering
can terminate the MPI solver when no authorised display is available. Keep CFD
and image production as separate steps. The retained visualization settings
may be enabled deliberately for post-processing in a suitable VTK environment.

scripts/clean.sh removes generated mesh, times, logs, post-processing and
recognised Mann boundary data. Mann data with an unknown marker are refused
rather than deleted.
