# StudySensei

A study planner and tutor that knows your modules and your habits. It tells you what to study next and why, helps
while you study, and gets more accurate about you every week.

> Being rebuilt as a web app. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for status.
> The original PyQt prototype is archived at the git tag `v0-pyqt-prototype`.

## Prerequisites (Windows, macOS or Linux)

- Git
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you)
- Node.js 22 LTS
- Docker Desktop, **running**

## First-time setup

```bash
git clone https://github.com/Josh-Heath123/StudySensei.git
cd StudySensei
npm install                      # web and root JS dependencies
uv sync --directory apps/api     # Python 3.12 + API dependencies
```

Optional: copy `apps/api/.env.example` to `apps/api/.env` (and the same for `apps/web`) to override the defaults.
The defaults work for local development.

## Run

```bash
npm run dev
```

This starts Postgres in Docker (port 5433), applies migrations, creates the local user, and runs:

- the web app at http://localhost:5173
- the API at http://localhost:8000 (docs at http://localhost:8000/docs); the web app reaches it through Vite at `/api`

The Today page shows a **System status** card. Both rows should read **Connected**.

## Check

```bash
npm run check
```

This runs ruff, prettier, eslint, mypy, tsc, pytest (against real Postgres) and vitest, the same checks as CI.

## Docs

- [Product](docs/PRODUCT.md): what we're building and why
- [Architecture](docs/ARCHITECTURE.md): how it's built
- [Roadmap](docs/ROADMAP.md): phases and tasks
- [Progress](docs/PROGRESS.md): session log
- [Decisions](docs/decisions/)
- [Legacy notes](docs/legacy-notes.md): ideas kept from the prototype
- [Changelog](CHANGELOG.md): what each phase delivered
- [Contributing](CONTRIBUTING.md): the merge gate and branch rules

## Ownership and licence

StudySensei is a personal project owned by Joshua Heath. All rights reserved: see [LICENSE](LICENSE).

- [docs/AUTHORSHIP.md](docs/AUTHORSHIP.md): who makes it and how, as a dated record.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): the third-party components it uses and their licences (generated
  by `npm run licenses`).
