# #816 — Retire legacy FLOW D-base and ARCH S6 Hybrid positive P2

Status: Draft PR #816 only; no changes to main or physics equations.

Current FLOW workflow retains the uniquely evidenced EI/H source-bound Native P1,
ideal-gas/direct-Material Native P2 and four EI10/EI16 reaction-reduction Native
P2 fixtures. It retires only the obsolete S6 D-base 417/941 success-expectation
step and its orphaned evidence upload paths. Existing historical input runner
and source data remain unchanged.

Current Physics Native workflow retires the entire former
issue541_arch_s6_hybrid_native_p2 job (one redundant C++ build and both
obsolete positive Hybrid check-input cases), while preserving ARCH DD JSON,
CORE, P6 W1 build, New-only 417/941 P05 with N1-N8 negative mutants, and
original100 Public D 417/941 P2. The registered Native job set changes 9 to 8.

Evidence retained:
- FLOW previous workflow Git blob 3f2360f7ae71ed9081dfa55aeba5119f5c44a9b0.
- ARCH previous Native workflow blob dff6e06b4033eb4a5052763c5ac0bb3f3b94e52d.
- FLOW run https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45229306156,
  artifact #14846751966. Upstream EI/H and reduction P2 succeeded; old D-base
  S6-417 input failed with P2_S6_417_CHECK_INPUT_FAILED.
- ARCH run https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45229306344,
  artifact #14846272139. Old 417/941 Hybrid overlays both fail
  DDContinuityEq::checkIntegrity due to duplicate ni_time
  [PhysicsFVLogMolarElectronTimeDerivative] on log_O2p.
- Historical ARCH baseline successful P2 belongs only to source
  5d15c4054a00aa9fa8a778a87bb21690a3a5469b, run #43883076025,
  artifact #14234186951. It does not prove current #816 legacy compatibility.
- Archived A2/B FLOW ledgers, ARCH receipt, runner and archival guard remain
  byte-identical and pinned in ci/guards/issue816_flow_arch_retirement_p0.py.

Approval is limited to obsolete *positive* legacy Hybrid check-input contracts.
It does not suppress arbitrary input failures, restore old compatibility, grant
P3/P4 scientific equivalence, or remove independent ARCH P3/HOLD obligations.
Current exact-head CI must pass before main merge; keep all historical Actions
and artifacts.