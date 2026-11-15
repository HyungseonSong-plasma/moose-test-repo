# Exact tiny-diffusion numerical parity control (P2/P3 tiny only).
# The existing baseline.i owns all variables, kernels and BCs here.
# Adding an empty root PlasmasAction must create NO new solver objects;
# do NOT confuse this with full Physics/JSON generated-source validation.
# The latter lives in standalone valid_all_physics_json_p2.i.
[Physics]
  [Plasmas]
  []
[]
