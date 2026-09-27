# Qualified plasma-closure case

This directory is populated in the validated distribution artifact from the
qualified 20 ns PlasmaClosures migration case.

Expected files:

- `input.i`: heavy-particle parent application
- `fast_sub.i`: electron application with `[GummelIteration]` and electron `[PlasmaClosures]`
- `poisson_sub.i`: Poisson application with charge `[PlasmaClosures]` and banded electron response
- `electron_moments.txt`
- `o2_elastic.txt`
- `transport_data.txt`
- `case.json`

From this directory, after building `physics-opt`:

```bash
../../physics-opt -t --check-input -i input.i
../../physics-opt -t -i input.i
```

The case metadata corresponds to 88 heavy cycles / 352 electron steps and
an end time of approximately 19.941 ns.
