# Post-processing outputs

Run `make postprocess` from the repository root to create `videos/`, `images/`
and `artifacts/` here. These generated directories are excluded from Git.

OpenFOAM's raw sampled fields remain in `case/postProcessing/`, where its
sampling tools write them. This directory contains the presentation and
diagnostic outputs produced from those fields.

The three horizontal views cover the complete horizontal domain, including the
inlet, using their original names. Vorticity uses a black–red–yellow colour map.
