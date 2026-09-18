# Governed work manifests

New scientific experiments and refactor automation are data, not GitHub workflow files.

Create a fail-closed skeleton with:

\`\`\`bash
python3 skills/workflow/new_work.py --issue 253 --kind experiments --title "Gummel dt release"
python3 skills/workflow/new_work.py --issue 254 --kind refactor --title "Profile-step parser repair"
\`\`\`

The generated identity is monotonic within an issue and kind, for example
\`Issue_253_experiments01\` or \`Issue_254_refactor01\`. Configure repository-relative,
argument-vector commands in the manifest. Commands are executed without a shell by
\`skills/workflow/run_work.py\`; nonzero exits, timeouts, malformed manifests, identity
mismatches, and incomplete execution all fail closed and produce \`evidence.json\`.
