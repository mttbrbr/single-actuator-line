# Workflow and acceptance checks

1. Source OpenFOAM.com v2412.
2. Ensure $FOAM_USER_LIBBIN/libturbinesFoam.so already exists. No ALM source
   checkout or build step belongs to this repository.
3. Run python3 tools/generate_case.py and
   python3 -m unittest discover -s tests -v.
4. Run scripts/mesh.sh. Acceptance requires:
   - Mesh OK;
   - 6.6–6.8 million cells;
   - all cells hexahedral;
   - maximum non-orthogonality at numerical zero.
5. Generate the 30.2 s Mann box with python3 tools/generate_mann_inflow.py.
   Confirm 303 exported planes and 10% realised longitudinal TI in
   boundaryData/manifest.json.
6. Run scripts/check_environment.sh, prepare the Mann initial directory and
   execute pimpleFoam -dry-run before a production launch.
7. Run scripts/run_production.sh for the 30 s, 12-rank calculation.
8. Post-process the T1 performance CSV and wake samples over 10–30 s.

scripts/clean.sh removes generated mesh, times, logs, post-processing and
recognised Mann boundary data. Mann data with an unknown marker are refused
rather than deleted.
