# NREL Phase VI — single-turbine ALM/IDDES case

Reproducible OpenFOAM case for an NREL Phase VI wind turbine in a neutral
atmospheric boundary layer. The rotor is represented with the actuator-line
method (ALM), while the wake is resolved using the `kOmegaSSTIDDES` turbulence
model.

This repository contains the case configuration, blade and airfoil data,
generation tools, run scripts and tests. Generated meshes, Mann turbulence
planes, time directories and solver output are intentionally excluded from
Git.

## Simulation software

The case targets **OpenFOAM.com v2412** and runs with `pimpleFoam`.

The actuator-line forcing is provided by
[`turbinesFoam`](https://github.com/turbinesFoam/turbinesFoam), an external
OpenFOAM library for wind- and hydrokinetic-turbine simulations. The generated
case loads it at runtime as:

```text
$FOAM_USER_LIBBIN/libturbinesFoam.so
```

The source code of `turbinesFoam` is not vendored in this repository. It must
be compiled separately against the same OpenFOAM installation used to run the
case. For reproducible results, record the exact `turbinesFoam` commit used for
a production campaign.

The turbulent inlet is generated separately with
[`hipersim`](https://pypi.org/project/hipersim/) **0.1.21**, using the Mann
spectral turbulence model. `hipersim` is a preprocessing dependency and is not
the actuator-line implementation.

## Reference configuration

| Item | Value |
| --- | --- |
| Rotor | NREL Phase VI, 2 S809 blades |
| Diameter / hub height | 10.058 m / 12.192 m |
| Rotor speed / pitch | 71.63 rpm / 3° |
| Hub-height mean wind | 7 m/s |
| Atmospheric boundary layer | Neutral logarithmic profile, `z0 = 0.03 m` |
| Resolved inlet turbulence | Mann model, 10% longitudinal TI, `D/16` transverse sampling |
| CFD solver | `pimpleFoam` |
| Turbulence model | `kOmegaSSTIDDES` |
| Current mesh (`mesh.cells_per_D: 48`) | 22,525,776 hexahedral cells |
| Rotor/wake core resolution | `D/48`, configurable in YAML |
| Simulated time | 57.5 s |
| Statistics window | 28.75–57.5 s |
| Parallel decomposition | 12 ranks |

The complete physical and numerical assumptions are documented in
[`docs/model.md`](docs/model.md).

## Repository layout

```text
case/                 OpenFOAM fields and static dictionaries
config/case.yaml      single source of truth for case parameters
data/                 NREL Phase VI blade geometry and S809 polar
scripts/              environment, mesh, run and cleanup scripts
tools/                dictionary generation, Mann inflow and post-processing
tests/                configuration and rendering tests
docs/                 model description and acceptance workflow
postprocessing/       generated videos, images and LES/wake artifacts
```

Generated OpenFOAM dictionaries are derived from `config/case.yaml`; edit the
YAML configuration and regenerate them instead of maintaining generated files
by hand.

To choose a different mesh, edit just `mesh.cells_per_D` in
`config/case.yaml`, then run `make generate && make mesh` **before starting a
new simulation**. For example, 32 gives 6,674,304 cells, 40 gives
13,022,100, and the current 48 gives 22,525,776. The validator rejects
resolutions above `mesh.max_cells: 25000000`. Never change this setting in the
middle of a run: the existing mesh and checkpoints belong to the old value.

## Requirements

- Linux with OpenFOAM.com v2412 sourced in the current shell;
- a C++ build of `libturbinesFoam.so` compatible with that OpenFOAM build;
- Python 3 with the packages listed in `requirements.txt`;
- FFmpeg (`ffmpeg` and `ffprobe`) for post-processing videos;
- MPI with at least 4 ranks for the smoke test and 12 for production.

To build the upstream actuator-line library in the standard OpenFOAM user
directory:

```bash
cd "$WM_PROJECT_USER_DIR"
git clone https://github.com/turbinesFoam/turbinesFoam.git
cd turbinesFoam
./Allwmake
test -f "$FOAM_USER_LIBBIN/libturbinesFoam.so"
```

The upstream version must support OpenFOAM.com v2412. Save the selected commit
with `git rev-parse HEAD` alongside the results of any production run.

## Setup and validation

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

python3 tools/generate_case.py
python3 -m unittest discover -s tests -v
./scripts/check_environment.sh
```

`check_environment.sh` verifies the OpenFOAM version, required executables,
the presence of `libturbinesFoam.so` and consistency of the generated files.

## Smoke test

The smoke profile uses a coarse mesh, uniform inflow and four MPI ranks. It is
intended to catch setup or runtime errors, not to produce physical results.

`make test` and `make smoke` serve different purposes. The unit tests finish in
well under a second and validate configuration arithmetic and generated text:
cell count and 25-million limit, turbine placement and twist convention,
IDDES/numerical settings, retained checkpoints, post-processing views and
output paths. They do not launch OpenFOAM or create CFD data. The smoke test
actually launches a short coarse OpenFOAM calculation and therefore checks the
solver, MPI and `turbinesFoam` integration. Keeping both prevents configuration
errors from reaching an expensive production run.

```bash
make smoke
```

The smoke run is created under `/tmp/single-actuator-line-smoke.*` and never
rewrites production dictionaries or checkpoints. Its temporary path is printed
for inspecting logs.

## Production run

Generate and validate the production mesh:

```bash
python3 tools/generate_case.py --profile production
./scripts/mesh.sh
```

Generate the Mann inlet and start the 12-rank calculation:

```bash
python3 tools/generate_mann_inflow.py
make run
```

If an existing production calculation is interrupted, resume it from the
latest complete decomposed time without regenerating or decomposing the case:

```bash
make resume
```

The production script checks the mesh, prepares `case/0` from `case/0.mann`,
runs `topoSet`, decomposes the domain and launches `pimpleFoam` in parallel.
See [`docs/workflow.md`](docs/workflow.md) for the complete acceptance checks.

During production, function objects write vorticity, pressure coefficient, Q,
the native IDDES `LESRegion` diagnostic and wake-plane samples. In-solver VTK
rendering is disabled because it can abort an otherwise healthy MPI run. The
production configuration now sets `purgeWrite 0`, retaining every saved
checkpoint for later analysis; plan for hundreds of GB of disk usage.

After the run, with OpenFOAM v2412 sourced and the Python environment active,
use one headless command for all checkpoint videos and turbulence diagnostics:

```bash
make postprocess
```

This samples only the local decomposed case and collects user-facing results in
`postprocessing/`:

```text
postprocessing/
├── videos/       MP4s by field, plus main/ combined views
├── images/       4K PNGs by field and view; checkpoint_times.csv maps frames to time
└── artifacts/    resolved-TKE/IDDES maps, time series and wake summaries
```

The intermediate OpenFOAM cutting planes remain under `case/postProcessing/`;
they are not a second case or a second output workflow. The script uses every
complete checkpoint that still exists on all ranks and reports the exact time
range. The separate actions
`status`, `sample`, `videos`, `images`, `diagnostics`, and `verify` support inspection or
resuming an interrupted post-processing job. The workflow verifies that every
video contains one frame per retained checkpoint. It never reads images from
another case.
The display raster interpolates between sampled plane points; this affects only
the video image, not the CFD fields or quantitative LES diagnostics. Final
display upscaling uses nearest-neighbour pixels rather than bicubic smoothing;
cross-wake vorticity views use a wider 0–8 s⁻¹ scale to retain compact vortices.
The already-completed run has 64 retained checkpoints from 26 to
57.5 s; earlier fields were purged and cannot be reconstructed.

## Useful commands

```bash
make generate    # render the production dictionaries
make test        # run unit and consistency checks
make check-env   # validate OpenFOAM and turbinesFoam
make mesh        # build and validate the production mesh
make smoke       # execute the coarse uniform-inflow smoke test
make mann        # generate Mann boundaryData
make run         # start a new run; refuses to overwrite existing checkpoints
make resume      # resume an existing 12-rank decomposed run
make postprocess # videos and turbulence diagnostics from retained checkpoints
```

Deleting generated CFD data is deliberately not a Makefile target. If a run
must be removed, `./scripts/clean.sh --confirm-delete-generated-data` requires
an explicit opt-in and preserves the reusable `case/0.uniform` and
`case/0.mann` templates.

## Data and reproducibility

The blade definition is stored in `data/turbines/phaseVI_blade.csv`; the
extended Reynolds-number-one-million S809 polar is stored in
`data/airfoils/S809_Re1M_extended`. The Mann seed and all principal numerical
parameters live in `config/case.yaml`.

This repository does not redistribute OpenFOAM or `turbinesFoam`. Their
respective licences and citation requirements apply independently. When
publishing results, cite OpenFOAM, `turbinesFoam`, the aerodynamic data source
and the Mann turbulence methodology as appropriate.

## License

The original code and case configuration in this repository are distributed
under the **GNU General Public License v3.0 or later**
(`GPL-3.0-or-later`). See [`LICENSE`](LICENSE) for the complete terms.

OpenFOAM, `turbinesFoam`, `hipersim` and third-party aerodynamic data remain
the property of their respective copyright holders and are governed by their
own licences and attribution requirements.
