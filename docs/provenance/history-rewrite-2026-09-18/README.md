# Reachable-history rewrite provenance

Date: 2026-09-18

The repository's reachable branch history was rewritten to remove a retired
QPX-era heavy-transport class symbol and replace it with the canonical Physics
class name. The one-shot rewrite validated that the retired symbol had zero
reachable occurrences before force-pushing rewritten branch heads.

Files:
- commit-map.tsv: old commit SHA -> rewritten commit SHA
- refs-before.tsv: branch/tag refs before rewrite
- refs-after.tsv: branch refs after rewrite
- rewrite-summary.txt: head/tag counts and rewrite validation summary

This provenance does not claim deletion from external clones, forks, caches,
or GitHub's internal unreachable-object retention.
