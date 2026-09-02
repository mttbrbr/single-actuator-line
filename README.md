# Single-turbine ALM IDDES case

OpenFOAM.com **v2412** case for one NREL Phase VI wind turbine in a neutral
atmospheric boundary layer. The rotor is represented by the actuator-line
model from an externally compiled libturbinesFoam.so; this repository
contains only case configuration, turbine input data and workflow tools.

## Reference configuration

- One NREL Phase VI rotor at (x/D, y/D) = (0, 0): D = 10.058 m,
  H = 12.192 m, two S809 blades.
- Fixed rotor speed 71.63 rpm, pitch 3 deg, hub-height wind 7 m/s.
- Neutral logarithmic ABL, z0 = 0.03 m, with a Mann inlet at 10% resolved
  longitudinal turbulence intensity.
- k-omega SST IDDES with pimpleFoam, 30 s total and statistics over 10–30 s.
- Orthogonal, fully hexahedral 18-block mesh with 6,674,304 cells and D/32
  rotor/wake core resolution.

Meshes, Mann planes, time directories and solver output are generated locally
and excluded from Git.

## Quick start

Source OpenFOAM.com v2412 and ensure the already compiled library is available
as $FOAM_USER_LIBBIN/libturbinesFoam.so, then run:

    python3 -m pip install -r requirements.txt
    python3 tools/generate_case.py
    ./scripts/check_environment.sh
    ./scripts/mesh.sh
    python3 tools/generate_mann_inflow.py
    ./scripts/run_production.sh

For a cheap numerical workflow check without Hipersim:

    python3 tools/generate_case.py --profile smoke
    ./scripts/run_smoke.sh

## Tests

    python3 -m unittest discover -s tests -v
    python3 tools/generate_case.py --check
    python3 tools/generate_mann_inflow.py --dry-run

See docs/model.md for model conventions and docs/workflow.md for acceptance
checks.
