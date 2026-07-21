# Single-turbine Phase VI validation gate

Run from the repository root after compiling turbinesFoam:

```bash
./scripts/run_single_turbine_validation.sh
```

This overlay retains the production `D/32` resolution, uses only T1 at the
domain centre, applies a uniform 7 m/s inlet and runs for 30 s. Average the
turbinesFoam performance output over 10–30 s and compare `Cp` and `Ct` with the
matching NREL Phase VI 7 m/s, 71.63 rpm, 3 degree-pitch campaign. Both
coefficients must be within 15% before farm production is accepted.

The validation command intentionally replaces generated dictionaries in the
main case. Restore them afterwards with `python3 tools/generate_case.py`.

