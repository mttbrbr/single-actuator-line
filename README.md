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
| Resolved inlet turbulence | Mann model, 10% longitudinal TI |
| CFD solver | `pimpleFoam` |
| Turbulence model | `kOmegaSSTIDDES` |
| Production mesh | 6,674,304 hexahedral cells |
| Rotor/wake core resolution | `D/32` |
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
```

Generated OpenFOAM dictionaries are derived from `config/case.yaml`; edit the
YAML configuration and regenerate them instead of maintaining generated files
by hand.

## Requirements

- Linux with OpenFOAM.com v2412 sourced in the current shell;
- a C++ build of `libturbinesFoam.so` compatible with that OpenFOAM build;
- Python 3 with the packages listed in `requirements.txt`;
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

```bash
./scripts/run_smoke.sh
```

Regenerate the production profile before inspecting or running the production
case, because the smoke command rewrites generated dictionaries.

## Production run

Generate and validate the production mesh:

```bash
python3 tools/generate_case.py --profile production
./scripts/mesh.sh
```

Generate the Mann inlet and start the 12-rank calculation:

```bash
python3 tools/generate_mann_inflow.py
./scripts/run_production.sh
```

The production script checks the mesh, prepares `case/0` from `case/0.mann`,
runs `topoSet`, decomposes the domain and launches `pimpleFoam` in parallel.
See [`docs/workflow.md`](docs/workflow.md) for the complete acceptance checks.

## Useful commands

```bash
make generate    # render the production dictionaries
make test        # run unit and consistency checks
make check-env   # validate OpenFOAM and turbinesFoam
make mesh        # build and validate the production mesh
make smoke       # execute the coarse uniform-inflow smoke test
make mann        # generate Mann boundaryData
make clean       # remove generated simulation data
```

`make clean` removes generated mesh and time directories, processor data,
logs, post-processing results and recognised Mann boundary data. The reusable
templates `case/0.uniform` and `case/0.mann` are preserved.

## Data and reproducibility

The blade definition is stored in `data/turbines/phaseVI_blade.csv`; the
extended Reynolds-number-one-million S809 polar is stored in
`data/airfoils/S809_Re1M_extended`. The Mann seed and all principal numerical
parameters live in `config/case.yaml`.

This repository does not redistribute OpenFOAM or `turbinesFoam`. Their
respective licences and citation requirements apply independently. When
publishing results, cite OpenFOAM, `turbinesFoam`, the aerodynamic data source
and the Mann turbulence methodology as appropriate.
