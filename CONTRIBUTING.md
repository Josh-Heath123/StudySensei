# Contributing

How changes reach `main`. The day-to-day workflow (branches, commits, PRs, the local check) is in `CLAUDE.md`.

## The merge gate

Every change reaches `main` through a pull request, and the pull request needs the **CI passed** check
(`.github/workflows/ci.yml`). That one job waits for every other job and fails if any failed or was cancelled, so
jobs can be added, split or skipped without changing the branch rules. A PR that changes only Markdown and `docs/`
skips the api, web and e2e jobs; the hygiene job (secret scan and licences) always runs.

Before pushing, run `npm run check` (about a minute; everything CI runs except e2e).

## Branch rules as code

The rules for `main` live in `.github/rulesets/` as GitHub ruleset JSON:

| File | What it does |
| --- | --- |
| `main.json` | Blocks deleting and force-pushing `main`. Requires a pull request (0 approvals, all conversations resolved) and the **CI passed** check with the branch up to date. No bypass actors. |
| `main-signed.json` | Requires signed commits on `main`. Apply it only once commit signing is set up on every machine that commits. |

### Applying them

They aren't applied automatically. With `gh` logged in as the repository owner:

```
gh api -X POST repos/Josh-Heath123/StudySensei/rulesets --input .github/rulesets/main.json
gh api -X POST repos/Josh-Heath123/StudySensei/rulesets --input .github/rulesets/main-signed.json   # after signing is set up
```

Check them with `gh api repos/Josh-Heath123/StudySensei/rulesets` (it lists each ruleset's `id`), or in the repository's
Settings → Rules → Rulesets.

### Changing them later

Edit the JSON file in a pull request first, so the file stays the source of truth. After it merges, update the live
ruleset by its id:

```
gh api repos/Josh-Heath123/StudySensei/rulesets                       # find the id
gh api -X PUT repos/Josh-Heath123/StudySensei/rulesets/<id> --input .github/rulesets/main.json
```

To remove one: `gh api -X DELETE repos/Josh-Heath123/StudySensei/rulesets/<id>`. Changing the required check's name
means changing the `name:` of the `ci-passed` job and `main.json` together, or every PR will wait for a check that
never reports.

## Licences and secrets

- `scripts/check-licenses.mjs` fails on AGPL, GPL, SSPL or an unknown licence in the Python environment (`uv.lock`) or
  the npm production dependencies. A package whose licence is fine but unreadable goes in
  `scripts/license-allowlist.json` with the reason it was reviewed. A real copyleft dependency is replaced, not
  allow-listed (PyMuPDF was rejected for AGPL).
- `THIRD_PARTY_NOTICES.md` is generated from the same data by `npm run licenses`; CI fails if it's stale. The embedding
  model and the fonts are listed there with licences checked by hand in `scripts/third-party-notices.mjs`.
- StudySensei itself is proprietary (`LICENSE`); how it's made is recorded in `docs/AUTHORSHIP.md`.
- gitleaks scans the commits of every PR and push. Never commit `.env`; fake keys in tests should look fake
  (`fake-groq-key-for-ping-tests`).
