# Physical and numerical model

## Geometry and actuator line

The mean wind is aligned with +x, y is cross-wind and z is vertical. The
single turbine T1 is centred at (0, 0, 12.192 m) and its rotation axis is
(-1 0 0).

The NREL Phase VI rotor has diameter 10.058 m, two tapered and twisted S809
blades, fixed speed 71.63 rpm and 3 degree pitch. The blade table remains in
the NREL feather-positive convention; the generator writes -(twist + pitch)
for turbinesFoam. The cylindrical root uses a drag-only profile and the
measured S809 Reynolds-one-million polar is extended to [-180, 180] degrees
for startup robustness.

The actuator-line implementation is not part of this repository.
libturbinesFoam.so must already be compiled for OpenFOAM.com v2412. The case
loads it at runtime and retains only the required fvOptions, blade geometry
and polar input.

## Structured mesh

The domain is [-5D, 15D] x [-4D, 4D] x [0, 5D]. blockMesh creates a conformal
3-by-3-by-2 arrangement of 18 Cartesian blocks. The central rotor and wake
region extends from -0.5D to 8D, -1.5D to 1.5D, and from the ground to 2D; its
spacing is uniform at D/32 = 0.3143 m. Geometric grading in the outer blocks
stays below approximately 4.2% per cell.

The production mesh has 6,674,304 cells. Every cell must be a hexahedron and
maximum non-orthogonality must be numerical zero. topoSet only creates the T1
source selection and does not modify the mesh.

## IDDES and numerics

The turbulence closure is kOmegaSSTIDDES, selected under simulationType LES,
with IDDESDelta. It uses the k-omega SST branch in shielded near-wall regions
and resolves LES content where the mesh permits it.

Velocity convection is centred. The transported k and omega equations use
bounded convection. Gradients are linear and Laplacian/snGrad schemes are
orthogonal. Since the mesh is Cartesian, nNonOrthogonalCorrectors is zero. The
timestep is limited to 0.005 s and the Courant number to 0.7.

## Neutral ABL and boundary conditions

The inlet mean is:

    U(z) = u*/kappa log((z + z0)/z0)

with z0 = 0.03 m, kappa = 0.41 and u* = 0.4775537 m/s, giving U(H) = 7 m/s.
Hipersim generates resolved Mann fluctuations with Gamma = 3.9, L = 0.7D,
fixed seed and 10% longitudinal TI.

At the production inlet, U uses timeVaryingMappedFixedValue; k and omega use
the OpenFOAM atmospheric equilibrium profiles atmBoundaryLayerInletK and
atmBoundaryLayerInletOmega. Thus 10% denotes the resolved longitudinal Mann
component and is not an upper bound on total resolved-plus-modelled
turbulence.

The ground uses noSlip, kqRWallFunction, omegaWallFunction and
atmNutkWallFunction. The top applies the equilibrium kinematic shear
u*^2 = 0.2280575 m2/s2; lateral faces are symmetry. Pressure is fixed to zero
at the outlet and has zero normal gradient elsewhere. Outlet velocity uses a
zero-valued backflow condition.

## Sampling

The run lasts 30 s and statistics start at 10 s. Centreline probes and cutting
planes are written at 1D, 2D, 4D, 6D and 8D downstream. This duration is suited
to preliminary single-turbine assessment; longer runs are required for
statistically converged atmospheric-wake conclusions.
