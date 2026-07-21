# LES wind-farm wake interaction case

Case OpenFOAM.com **v2412** for the interaction of four wind-turbine wakes.
The NREL Phase VI turbines are represented with the actuator-line model from
[`turbinesFoam`](https://github.com/turbinesFoam/turbinesFoam), while the
production inlet is a Mann turbulence box generated with
[`Hipersim`](https://hipersim.pages.windenergy.dtu.dk/hipersim/).

The repository stores source configuration and scripts. Meshes, Mann planes,
time directories and solver output are generated locally and intentionally
excluded from Git.

## Reference configuration

- Four NREL Phase VI rotors: `D = 10.058 m`, `H = 12.192 m`, two S809 blades.
- Fixed rotor speed `71.63 rpm`, pitch `3 deg`, hub-height wind `7 m/s`.
- Neutral logarithmic ABL, `z0 = 0.03 m`, target hub-height TI `10%`.
- LES-WALE with `pimpleFoam`, 120 s total and statistics over 60–120 s.
- Verified production mesh: 4,929,992 cells, `D/32` in the rotor/wake core.

Geometry and measured airfoil data are sourced from the NREL report
*Unsteady Aerodynamics Experiment Phase VI: Wind Tunnel Test Configurations
and Available Data Campaigns*, NREL/TP-500-29955. See
[`docs/model.md`](docs/model.md) for conventions and limitations.

## Quick start

Open a shell with OpenFOAM.com v2412 sourced, then:

```bash
python3 -m pip install -r requirements.txt
python3 tools/generate_case.py
./scripts/check_environment.sh
./scripts/build_turbinesfoam.sh
./scripts/mesh.sh
python3 tools/generate_mann_inflow.py
./scripts/run_production.sh
```

For a cheap workflow check that does not require Hipersim:

```bash
python3 tools/generate_case.py --profile smoke
./scripts/run_smoke.sh
```

The smoke profile uses a coarser mesh, uniform inlet and a 0.25 s end time. It
is a numerical integration test, not a physical result.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 tools/generate_case.py --check
python3 tools/generate_mann_inflow.py --dry-run
```

After meshing, `./scripts/check_mesh.sh` enforces mesh quality and the cell
count target. Large production runs are decomposed over 12 MPI ranks.

