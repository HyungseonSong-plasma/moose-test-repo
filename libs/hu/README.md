# Legacy HU compatibility namespace

The canonical code metric engine is now **Code Understandability Metrics**
under `libs/code_understandability/`. New integrations must import
`libs.code_understandability`; the `libs.hu` namespace exists solely to
preserve historical clients and stored measurement identifiers.

Legacy `HUInput`, `HUAssessment`, `HUObservation`, `HUIndicator`,
`ObservedHU` and `HUComparison` are aliases of canonical model classes.
Legacy `evaluate_hu()` still records the absence of human evaluator answers;
the general `evaluate_understandability()` does not require human evaluations.
`compare_hu()` retains legacy unknown identifiers, while the canonical API
uses general code-understandability terms.

No separate metric calculation algorithm is maintained in this directory.
