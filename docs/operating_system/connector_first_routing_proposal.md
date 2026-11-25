# Connector-only create and comment adoption

**Status:** candidate consumer adoption of merged Samuel PR #319; active only after this PR passes CI and is merged.

The original connector-first proposal is superseded by the owner's narrower decision: retain the authoritative registry, require Connector-only providers for `GITHUB_BRANCH_CREATE`, `GITHUB_FILE_CREATE`, `GITHUB_PR_CREATE`, `GITHUB_COMMENT_CREATE`. All other chains remain governed by the central pin.

Central revision: `20827ec81ab0eac4dd7560a22ee4212e274113a5`. Registry/blob/trigger identities are in `central_skills.json`. The mandatory response contract and local branch-policy mirror are included in this pin migration. No permissions expanded. No controller schedules modified. Historical Issue457 one-shot workflows intentionally retain their original execution pins so the migration does not retrigger experiments.
