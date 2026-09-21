# Workflow and acceptance checks

1. Source the intended OpenFOAM.com v2412 environment.
2. Ensure $FOAM_USER_LIBBIN/libturbinesFoam.so already exists. No ALM source
   checkout or build step belongs to this repository.
3. Run python3 tools/generate_case.py and
   python3 -m unittest discover -s tests -v.
4. Run scripts/mesh.sh. Acceptance requires:
   - Mesh OK;
   - exactly the number of cells derived from `mesh.cells_per_D` in YAML
     (22,525,776 at the current value 48; maximum 25 million);
   - all cells hexahedral;
   - maximum non-orthogonality at numerical zero.
5. Generate the Mann box with python3 tools/generate_mann_inflow.py.
   Confirm that its duration covers the complete run and that the realised
   longitudinal TI is 10% in
   boundaryData/manifest.json.
6. Run scripts/check_environment.sh, prepare the Mann initial directory and
   execute pimpleFoam -dry-run before a production launch.
7. Run `make run` for a new 57.5 s, 12-rank calculation, or `make resume`
   for an existing decomposed run. `make run` refuses to overwrite checkpoints.
8. Post-process the T1 performance CSV and wake samples over 28.75–57.5 s.

The case no longer contains the in-solver VTK/X11 renderer, which could
terminate MPI when no authorised display was available. Keep CFD and image
production separate. Run `python3 scripts/postprocess.py all` after
the calculation for headless videos and resolved-TKE/IDDES diagnostics. This
uses all complete retained checkpoints, and `purgeWrite 0` prevents future
production runs from silently discarding early frames. Monitor disk usage.
The video renderer uses the former full-frame colour-map style at 3840-pixel
width, without screen/display access.

`scripts/clean.sh --confirm-delete-generated-data` removes generated mesh,
times, logs, post-processing and recognised Mann boundary data only after
explicit opt-in. Mann data with an unknown marker are refused rather than
deleted.
