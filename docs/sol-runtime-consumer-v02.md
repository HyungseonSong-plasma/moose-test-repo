# Pinned SOL Adapter Runtime 0.2 consumer

Issue #279 adopts the supported `simulation-ontology` external runtime v0.2 consumer as an opaque executable boundary.

## Immutable pins

- simulation-ontology: `020e9a979a0b97f2af3cf54758cedf38fecb187a`
- consumer package: `sol-external-runtime-v02-consumer`
- sol-adapter-moose: `f35563f0e63e2739cb94a36c450d5d66024aff2a`
- Adapter Protocol: `0.2`
- Public Contract: `0.2`

No floating `main` dependency is permitted for #279 evidence.

## Ownership

Physics mechanically maps `SolRequest.backend_target` to runtime `target` and `required_capabilities`, and maps `mapping_plan`/`realization_spec` into the Adapter Protocol 0.2 plan request. Physics does not own adapter registration, process/session lifecycle, live `describe_adapter` bootstrap, compatibility projection, candidate selection, JSON-RPC transport, reconnect, or replay policy. Those remain upstream runtime responsibilities.

For the MOOSE vertical slice the reviewed Physics-to-SOL capability mapping yields target `moose` and capability `thermal.steady_conduction`; the generic runtime consumer itself contains no MOOSE selection rule.

## Interpretation boundary

The Physics boundary records runtime evidence and distinguishes validation rejection, execution non-completion, protocol failure, runtime/transport failure, and missing/ambiguous no-replay evidence. Adapter-native files and backend artifacts are evidence only and never become canonical Physics identity.

Runtime/protocol interoperability is not MOOSE physical or numerical V&V. Scientific acceptance remains a separate Physics responsibility.

The semantic separations remain explicit: execution plan is not mapping plan, execution case is not mapping action, raw parameter is not SOL quantity, and Physics capability ID is not SOL backend capability unless a reviewed mapping states otherwise.
