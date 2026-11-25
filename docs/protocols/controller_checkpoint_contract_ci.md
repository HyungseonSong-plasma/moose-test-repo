# Controller checkpoint contract qualification (candidate)

Controller invokes the read-only dispatch on trusted main with exact main SHA,
contract SHA256 and Samuel pin. It must observe the exact run and attempt, successful
job and artifact, and independently verify the receipt and artifact digest, source
identity, test set and hashes against the approved immutable contract. Never infer
success from dispatch acceptance. Missing/expired evidence or changed relevant source,
central pin, provider implementation or authority means requalification/HOLD. The
controller may reuse an independently verified receipt for unchanged qualification
inputs; per-operation live HEAD, policy and blocker gates remain mandatory.

The CI qualifies local Git CAS semantics only. It cannot call the ChatGPT GitHub
Connector and cannot certify its remote atomicity, grant write authority, or change
Samuel registration. Require a separately authorized live Connector qualification
on an isolated PR and a registered conditional publication contract before any
production checkpoint write. Do not use the existing narrow branch-fast-forward
capability for this distinct operation. No new Writer workflow, force update or
shared global lock. Controller scheduling stays paused pending runtime admission,
work identity, exclusive lease and restore qualification.

## Samuel integration and consumer receipt verification

Reuse the exact pinned `chatgpt_operation.github.actions_runtime` API:
`dispatch_contract` calls `dispatch_workflow`, and `observe_contract` calls
`observe_dispatch_once` with the exact source SHA. Persist the original dispatch
receipt and use the same correlation ID on subsequent observations; no duplicate
launch while pending. `checkpoint-contract:<correlation_id>` is observable in the
run name, including the fallback when a dispatch response lacks a direct run ID.
The trusted runtime must supply the installed pinned Samuel implementation and
an authenticated Actions transport; no token discovery or new dispatch provider.
After Samuel returns exactly one MATCHED_TERMINAL run, retrieve fresh exact-attempt
run/job/artifact metadata with complete enumeration and download that artifact.
`verify_receipt` checks repository, workflow, source, event, correlation, run and
attempt, successful job, archive digest/size/membership, exact contract and source
hash inventory, central pin, and JUnit test outcomes. Its output still grants no
write authority or live Connector qualification. Expected hashes must be read
from trusted immutable source; no self-attestation from the artifact. Live
metadata availability and runtime binding must be qualified before activation.
