# R4 — Wall-energy BC retirement candidate

Base: `0e46702d49f6424f2f381b492cb43375b72e97b6`; bounded Native evidence [45424801571](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45424801571), artifact 14934808542. Pinned MOOSE `FVFunctorNeumannBC` evaluates the signed flux on the same sided FV face. Factor -1 preserves outward residual; ADParsedFunctorMaterial retains the existing thermal and SEE model. The external raw FV smoke intentionally retains its existing equations; the isolated dielectric SEE control uses conservative log-molar energy and reconstructs physical inventory for the unchanged numerical oracle. The coupled D4 and lower-D generators already fail P2 with the unregistered PhysicsElectronWallFluxMaterial; archive them without claiming coupled physics parity. Their CSV analyzers remain available for historic evidence. D6's accepted historical input does not instantiate this energy BC: preserve the original metadata below and remove only the stale current production mechanism entry. No other D6 metadata is corrected here.

Original source bytes are preserved with the .txt suffix:

| Original path | Git blob |
|---|---|
| `physics_app/src/fvbcs/PhysicsFVElectronEnergyWallFluxBC.C` | `d8c4298353ab14186a9f3a270a22f9f5742621f9` |
| `physics_app/include/fvbcs/PhysicsFVElectronEnergyWallFluxBC.h` | `196090e997a4648a7df2b98ca113ff8fa037648a` |
| `experiments/Issue3_dielectric_surface_charge/prepare_d4.py` | `ffc8f9468edae4a085e2d9dfa17c07680bbff87d` |
| `experiments/Issue3_dielectric_surface_charge/prepare_d4_lowerd.py` | `13f049226468a919e44ec2771d2872f3ef5042b1` |
| `physics_app/ci/electron_energy_wall_smoke.i` | `ef23344beeabe85e6740638e220c5e79c7be844f` |
| `experiments/Issue3_dielectric_surface_charge/prepare_d4_see_energy.py` | `fcfdcb94d0902e2d8d3e7a7145b103b0308d1a29` |
| `experiments/Issue3_dielectric_surface_charge/analyze_d4_see_energy.py` | `021b75f884d09912739e017154b00da7bf93319e` |
| `experiments/Issue3_dielectric_surface_charge/test.json` | `5d379e9d1c17b33128d53f2047672b17eb880da2` |

The post-cut native build and run, and external/dynamic consumer closure, remain separate gates. Historical replay requires the matching historical checkout and executable. Do not infer generalized solver parity or global safe deletion from bounded fixture evidence.
