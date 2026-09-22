# Post-processing outputs

Run `make postprocess` from the repository root to create `videos/`, `images/`
and `artifacts/` here. These generated directories are excluded from Git.

OpenFOAM's raw sampled fields remain in `case/postProcessing/`, where its
sampling tools write them. This directory contains the presentation and
diagnostic outputs produced from those fields.
