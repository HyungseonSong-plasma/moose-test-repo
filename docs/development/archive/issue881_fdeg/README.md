# Historical FDEG provenance (#881)

**Status: historical evidence only.** No active FDEG engine, compatibility adapter or scientific acceptance is supplied by these registries. Canonical reusable source analysis is `physics_harness/code/`. The #774 retired Factory guard retains exact registry blob identity as provenance, independent of live analysis.

The original executable subsystem, tests and document versions remain reproducible from [pre-cut main 7a119106](https://github.com/HyungseonSong-plasma/moose-test-repo/tree/7a119106a22f2de2ca5c761a4119f00509e0efdd). The three JSON registries here are original Git blobs, not reserialized data. Existing FDEG development documents elsewhere are historical design records; their CLI examples require the original source checkout.

Evidence references:
- Code CI [45476946329](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45476946329), artifact 14959988094, ZIP SHA-256 `f9d89f8313ba0a885f1a2cf10ab5d02d0e46f134414cab5266e41e362f37edf6`, exact source cee3dd7447e5ca776d85cd600944bbac287d6610. Live-electron snapshot PRE_RETIREMENT / HOLD, not semantic or runtime acceptance.
- [Code6 source comparison 45484020418](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45484020418), artifact 14962467467, ZIP SHA-256 `37238045a198628ac8d65a27e96cfda9cec245f45e1ede1d46924e9ca3bc301e`. 15/15 literal source locations, ten generators; no missing or additional candidate locations. PARTIAL (159 diagnostic entries); no runtime or external closure. Detailed block/bindings retain their source-specific owner in #704.
- Dynamic references: #882, separate from this subsystem retirement.

## Original evidence custody

Both original ZIPs are stored here byte-for-byte, not reconstructed reports. The staging run [45485652803](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45485652803) verified producer run, source identity, original SHA-256 and ZIP CRC before staging the Git blobs; independent local download/hash matched the same blob identities. The tracked paths and digests are listed in [custody manifest](custody.json). Original source lineage remains distinct from the historical observation. No scientific acceptance or runtime closure is asserted.

- [artifact-14959988094.zip](artifact-14959988094.zip): 49855 bytes, Git blob `a02d6adba2b65531c7452f85ff3f734615b0dd1a`.
- [artifact-14962467467.zip](artifact-14962467467.zip): 82889 bytes, Git blob `85ff04621fc5b17248e80e5298a93bc7f76fcd04`.
