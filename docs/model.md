# Physical and numerical model

## Coordinate system and layout

The mean wind is aligned with `+x`, `y` is the cross-wind direction and `z` is
vertical. The actuator-line rotation axis is therefore `(-1 0 0)`. Turbine
coordinates in `config/case.yaml` are expressed in rotor diameters and are
converted to metres by `tools/generate_case.py`.

The layout is deterministic rather than re-randomised for every run. Seed
`20260715` records its provenance; the resolved coordinates are committed in
the YAML file so results can always be reproduced.

## NREL Phase VI rotor

The rotor model follows NREL/TP-500-29955:

- standard-tip diameter 10.058 m and hub height 12.192 m;
- two tapered and twisted S809 blades;
- fixed 71.63 rpm operation and 3 degree operator pitch;
- upwind rotor, zero cone, zero tilt.

`data/turbines/phaseVI_blade.csv` transcribes Table A-1. NREL defines positive
twist and pitch towards feather, while the axial-flow element convention in
`turbinesFoam` has the opposite sign. The generator therefore writes
`-(twist + 3 degrees)` to `elementData`; the source CSV remains in the report
convention. The cylindrical/transition root uses a cylinder drag profile;
S809 is assigned from approximately `r=1.26 m` to the tip.

`data/airfoils/S809_Re1M_extended` uses the measured 1-million-Reynolds-number
coefficients in Tables A-7 and A-8 in the operating range. Values at large
positive and negative incidence are an explicit conservative extension. They
prevent unsafe linear extrapolation if a start-up transient produces an
unusual angle of attack, but must not be treated as measured data.

## LES and actuator-line resolution

The production mesh uses `D/32 = 0.3143 m` in the rotor/wake core and `D/16`
in its transition. With `GaussianCoeffs.meshFactor=1`, the mesh contribution
to the turbinesFoam Gaussian width is approximately `2 delta`, or `0.63 m` in
the core. Two buffer cells are requested between refinement levels. The
verified mesh contains 4,929,992 cells; standard `checkMesh` reports `Mesh OK`
with maximum non-orthogonality 25.24 degrees and maximum skewness 0.333.

The WALE sub-grid model uses `cubeRootVol` as its LES filter width. Spatial
convection is centred (`Gauss linear`) and gradients are limited only where
needed for robustness. The time step is limited to 0.005 s and Courant number
0.7, giving about 167 time steps per rotor revolution.

## Neutral ABL and Mann inlet

The mean profile is

```text
U(z) = u*/kappa log((z + z0)/z0)
```

with `z0=0.03 m`, `kappa=0.41` and `u*=0.47755 m/s`, selected so that
`U(H)=7 m/s`. The ground uses `atmNutkWallFunction`; the upper patch applies
the matching kinematic shear stress `u*^2=0.22806 m2/s2`.

Hipersim generates the actual Mann spectral field with `Gamma=3.9`,
`L=0.7D`, target longitudinal TI 10%, fixed seed and no high-frequency
compensation. The longitudinal spacing is `U(H)*0.1 s=0.7 m`. The generated
FFT box is 2048x64x40; 1203 planes are exported without longitudinal wrapping.
The converter adds the log profile to each plane and writes OpenFOAM
`timeVaryingMappedFixedValue` data.

The spectral box is generated with `n_cpu=1`. This avoids Hipersim's
version-dependent structured-array path in its multiprocessing random-number
generator; solver parallelism remains independent at 12 MPI ranks.
The finite realisation is then scaled uniformly in all three components so
its longitudinal standard deviation is exactly the requested 10% of hub
velocity. Raw TI, scale factor and effective `alphaepsilon` are recorded in
`boundaryData/manifest.json`.

This is a homogeneous Mann fluctuation field superimposed on an inhomogeneous
mean ABL. It is not a precursor LES and does not prescribe height-dependent
Reynolds stresses. The first 60 s are therefore discarded as inflow and wake
adjustment.

## Validation gate

Before accepting farm statistics, use the same mesh resolution and ALM setup
with only T1 active. At 7 m/s compare mean thrust and power coefficients with
the corresponding Phase VI data. The initial acceptance band is +/-15%.
Failure of this gate must be addressed through polar/pitch/sign and grid-width
checks; do not tune the four-turbine result directly.

