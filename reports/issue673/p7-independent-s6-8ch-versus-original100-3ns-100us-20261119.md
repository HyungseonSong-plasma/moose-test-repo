# P7: independently executed S6 historical 8-channel benchmark versus latest Physics at 3ns and 100us

**2026-11-19 · Evidence-only quantitative comparison. Science status: HOLD.**

## Exact identity and benchmark classification

- Latest modern Physics: Draft [PR #665](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/665) exact source `9457191f4c0693ae886586edd961965867ccd5c0`, W1 ELF SHA256 `b327aea7f496809779dd233336d8c62d15ab021accdb13e552efe1a750c72e18`.
- Independently *executed historical MOOSE model* 8-channel S6-417/941, original 400W 100us Native [#42589883028](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42589883028), workflow `d60bb8422f0a68f2e2699e5cf8d28b58b53369d0`, archive artifacts [417 #13677089020](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42589883028/artifacts/13677089020), [941 #13677375813](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42589883028/artifacts/13677375813). Rehashed original ZIPs (417 SHA256 `441eb637c0eefa947ecbc4e14853ab435e553616b8b6a1e1d11928309409bdcb`, 941 `d8643bf2d029a3236876b8912209be61fb85cecadc3125519897e441835d0177`), CRC checks PASS, actual 461-row plasma.csv each. Historical table is prepared **42 rows**, SHA256 `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`.
- Modern **New-only same-42row** bounded D8 3ns [#44409942970](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44409942970), artifact #14475669657; modern **Public D original-100row** 3ns [#44423713218](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44423713218), artifact #14483546363, and actual full 100us [#44426913036](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44426913036), artifacts [417 #14500940527](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44426913036/artifacts/14500940527) / [941 #14499369656](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44426913036/artifacts/14499369656). All latest runs check out `9457191...` source and reuse same W1 ELF with no rebuild. Public D original 100-row table SHA256 `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387`.
- The historical archive is independent **as a prior execution/source provenance**, but it is **not independent solver mathematics or calibrated laboratory evidence**. Same eight chemistry IDs per case; Public D comparisons are **different electron Lookup inputs (42 vs 100 rows)** and cannot isolate Owner changes.

## Recomputed numerical differences (26 observables per case per comparison, exactly same clock)

| Modern arm vs historical 8ch reference | 417 max absolute relative difference | 941 max absolute relative difference | Interpretation |
|---|---:|---:|---|
| **New-only 42row at 3ns** vs archived 42row 3ns | 3.558×10⁻¹¹ % | 4.269×10⁻¹¹ % | Excellent short-window *same-input model reproducibility*, not external science |
| **Public D 100row at 3ns** vs archived 42row 3ns | 7.636 % | 7.636 % | Cross-input descriptive, dominated by focus O2p particle flux |
| **Public D 100row at 100us** vs archived 42row 100us | 14.854 % | 15.017 % | Cross-input descriptive, dominated by wafer net-surface-current magnitude |

### Actual 100us: signed (modern − archived)/archived

| Observable | 417 archived → modern | 417 delta | 941 archived → modern | 941 delta |
|---|---|---:|---|---:|
| RF absorbed power (W) | 404.4499 → 405.0575 | +0.150% | 404.4401 → 405.0451 | +0.150% |
| Electron density maximum (m⁻³) | 9.54334e16 → 1.06286e17 | **+11.372%** | 9.51877e16 → 1.06028e17 | **+11.388%** |
| Electron density minimum (m⁻³) | 1.15519e14 → 1.10534e14 | −4.315% | 1.15313e14 → 1.10329e14 | −4.321% |
| Mean energy maximum (eV) | 5.81085 → 5.73504 | −1.305% | 5.82121 → 5.74475 | −1.314% |
| Integrated Poisson charge (C) | 4.77094e-7 → 5.05670e-7 | **+5.990%** | 4.77739e-7 → 5.06415e-7 | **+6.003%** |
| Wafer current (A) | −5.81329e-4 → −6.67681e-4 | **+14.854% magnitude** | −5.83300e-4 → −6.70892e-4 | **+15.017% magnitude** |
| Focus ring current (A) | 1.98073e-2 → 1.92708e-2 | −2.708% | 1.99686e-2 → 1.94414e-2 | −2.640% |

**52/52 observables** at 100us can be numerically compared by timestamp and name using archived original raw CSV + modern sanitized 100us receipts. Absolute and signed relative metrics are stored separately in local full review audit. However modern raw CSV/Exodus not exported, so output bytes cannot independently be reconstructed/rehashed from the sanitized Artifact; no spatial map similarity test can be performed with this evidence alone.

## External independent HPEM reference: cannot claim spatial quantitative validation yet

- Versioned **public HPEM-derived** profile CSVs (Issue493): 45 axial r=0cm points, 51 radial z=23cm points, reference peak `8.885e16 m^-3`. Current Public D 100us volume peak is 19.62% (417) / 19.33% (941) higher, **peak locations and timestamp not paired**.
- Original HPEM physical timestamp is **unknown** and radial/axial coordinate convention is **not independently calibrated**. A numerical max-to-max ratio is not a profile RMSE nor an external scientific acceptance test.
- Candidate Native 100us original full Exodus was not published (private data safety), so true spatial slice RMSE is not available in these artifacts. Another independently authorized one-shot profile extractor [#44483021551](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44483021551) was *in progress when checked*; do not infer success.
- Separate user-authorized P4 checkpoint/restart comparison [#44482451543](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44482451543) was *in progress when checked*; no restart PASS inferred.

## Gate

- `P7_HISTORICAL_8CH_3NS_SAME_INPUT_REPRODUCIBILITY=PASS_DIAGNOSTIC`.
- `P7_PUBLIC_D_100US_CROSS_INPUT_NUMERIC_DIFFERENCE=QUANTIFIED`, **not** a science PASS/FAIL causality verdict.
- `P3_PUBLIC_D_ORIGINAL100_100US=PASS_EXECUTION_417_941` (already completed with 460 steps / 461 time rows).
- `P4_RESTART_EQUIVALENCE=OBSERVATION_PENDING`; `HPEM_PROFILE_TIME_AND_CALIBRATION=HOLD`; `SCIENCE_HOLD=ACTIVE`.
- Need controlled same-100row old-vs-new owner reference, predeclared tolerances, independently verified HPEM time/geometry, and field/restart evidence before any scientific equivalence approval. **Do not launch another Native workflow or build, modify original input, or merge PR #665**.
