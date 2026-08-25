# Executable location

The test runners support a local optimized executable at:

```text
bin/qpx-opt
```

Resolution order is:

1. `QPX_EXECUTABLE`
2. `bin/qpx-opt`
3. `qpx-opt` from `PATH`

For a small portable executable, `bin/qpx-opt` may be committed directly. For a large binary or a build with external runtime-library dependencies, prefer a GitHub Release asset and place/download the executable into `bin/qpx-opt` before running tests.

The test workspace should record the executable build/commit used for an important regression in its development or incident log.
