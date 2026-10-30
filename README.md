# INSTITRACE

**Integrated Dashboard for Monitoring and Tracking Institution-Related Complaint Cases Across AICTE Bureaus/Cells**

- Smart India Hackathon 2026 — Problem Statement **SIH26264** (Software · Smart Automation)
- Organization: AICTE — Department: Regulation Bureau
- Team: **SONARA** (Team ID 197721)
- **All data in this repository is SYNTHETIC DEMO DATA. No real AICTE records, persons, or credentials are used.**

---

## What INSTITRACE does

AICTE bureaus/cells (e.g. the Regulation Bureau and the Public Grievance Redressal Cell) can
process complaints about the same institution in isolation. INSTITRACE provides:

1. **One institution view** — a consolidated profile and complete case history per institution.
2. **A case registry** with receipt dates, categories, statuses, bureau/cell and officer
   assignment, last/next actions, expected and actual disposal dates.
3. **Cross-bureau coordination alerts** — institution-level signals when several bureaus hold
   active cases for the same institution, with acknowledge/resolve workflow.
4. **Explainable same-incident assessments** — a deterministic rule engine produces
   evidence-backed relationship suggestions with supporting, conflicting and missing evidence,
   requiring human review (confirm / reject / defer with rationale).
5. **Traceability** — append-only case action history plus a separate audit trail.
6. **Reports & analytics** — institution/region/bureau/status reports, ageing, disposal rates,
   overlap reporting and CSV export (with spreadsheet-injection protection).

### The core domain distinction (read this first)

| Concept | Meaning | Represented by |
| --- | --- | --- |
| Same institution | Two cases concern the same institution | `cases.institution_id` |
| Cross-bureau coordination alert | Active cases on one institution sit in different bureaus | `CoordinationAlert` (type `CROSS_BUREAU_COORDINATION`) |
| Potential same-incident | Evidence suggests the cases concern the same incident | `RelationshipAssessment` (rule-engine recommendation) |
| Human decision | Reviewer confirms / rejects / defers | `RelationshipAssessment.status` + rationale |

Sharing an institution never proves a shared incident; the engine abstains (`INSUFFICIENT_EVIDENCE`)
when records are thin and states explicitly when evidence does not establish a relationship.

## Architecture at a glance

- **Frontend**: React 18 + Vite 5 + TypeScript, React Router 6, Recharts. Vite dev server proxies
  `/api` to the backend so the browser always calls the same origin.
- **Backend**: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic migrations, Pytest.
- **Database**: PostgreSQL is the primary target; SQLite is the documented and fully tested local
  default (set by `INSTITRACE_DATABASE_URL`). Business logic uses portable SQLAlchemy only.

See [docs/architecture.md](docs/architecture.md) for the diagram and [docs/database-schema.md](docs/database-schema.md) for the ER diagram.

---

## Quick start (Windows 10/11, PowerShell)

Verified toolchain: **Python 3.11** (3.10+ works) and **Node.js 18+** (developed on Node 22 LTS,
npm 10). PostgreSQL is **optional** — the default SQLite mode runs everywhere without a server.

### 1. Check prerequisites

```powershell
python --version        # need 3.10 or newer  (tested: 3.11.2)
node --version          # need 18 or newer    (tested: v22.x)
npm --version           # bundled with node   (tested: 10.x)
```

If `python` is missing, install Python 3.11 from python.org and tick "Add python.exe to PATH".
If `node` is missing, install the Node.js LTS installer from nodejs.org.

### 2. Get the code and configure

```powershell
git clone <your-fork-or-repo-url> INSTITRACE
cd INSTITRACE
Copy-Item .env.example .env    # defaults work locally; edit secrets before sharing
```

### 3. Backend (PowerShell terminal #1)

```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.seed            # runs migrations, then loads synthetic demo data
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- If PowerShell blocks script activation: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
  (accept the prompt), then retry `..\.venv\Scripts\Activate.ps1`.
- Swagger UI: <http://localhost:8000/docs>

### 4. Frontend (PowerShell terminal #2)

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> and sign in with a demo account below.

### Demo users (synthetic, local-only)

| Username | Password | Role | Can |
| --- | --- | --- | --- |
| `admin` | `InstiTrace#Demo1` | ADMIN | everything, incl. demo reset |
| `officer.rb` | `Officer#Demo1` | BUREAU_OFFICER | case intake & workflow |
| `reviewer` | `Reviewer#Demo1` | REVIEWER | relationship review decisions |
| `manager` | `Manager#Demo1` | READ_ONLY_MANAGER | read-only oversight |

Defaults ship for local convenience only; override via `INSTITRACE_DEMO_*` env vars in `.env`.

### 5. Run tests and checks

```powershell
# Backend tests (50 tests) - default SQLite
cd backend; ..\.venv\Scripts\Activate.ps1; pytest tests/ -q

# Backend tests against PostgreSQL (after section 6; reuse an empty test database)
$env:INSTITRACE_TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/institrace_test"
pytest tests/ -q
Remove-Item Env:INSTITRACE_TEST_DATABASE_URL

# Frontend tests + type check
cd frontend; npm test; npm run typecheck

# Production-style frontend build
cd frontend; npm run build
```

### 6. PostgreSQL mode (optional)

PostgreSQL is the intended production database. The same code runs on it via one setting:

```powershell
# 1) Install PostgreSQL 16 (EDB installer) and create a database:
#    psql -U postgres -c "CREATE DATABASE institrace;"
# 2) Point configuration at it (adds the psycopg2 driver):
pip install psycopg2-binary
# edit .env:
# INSTITRACE_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/institrace
python -m app.seed
```

> **Verification status:** BOTH database paths pass the full 50-test suite. In the build sandbox
> PostgreSQL 16.2 (bundled via `pgserver`) ran: `alembic upgrade head`, the seed, the live API
> smoke test, and the entire pytest suite (`INSTITRACE_TEST_DATABASE_URL=<pg dsn> pytest tests/`).
> A Windows TCP-install walkthrough is documented but was not executable inside the sandbox.
> See [docs/known-limitations.md](docs/known-limitations.md).

### 7. Safe demo reset

```powershell
cd backend; ..\.venv\Scripts\Activate.ps1
python -m app.seed --reset     # wipes all rows and reseeds the synthetic dataset
```

or use **Settings & Status → Reset demo data** in the UI (ADMIN role). This is destructive by
design and asks for confirmation; it is the only destructive operation in the app.

### 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`; reopen the terminal. |
| `pip install` fails on SSL/proxy | Re-run with `pip install -r requirements.txt --index-url https://pypi.org/simple`. |
| Port 8000 already in use | `netstat -ano | findstr :8000`, stop the process, or start uvicorn with `--port 8001` and update `frontend/vite.config.ts` proxy target. |
| Port 5173 already in use | Vite auto-picks 5174; open the printed URL instead. |
| Blank page / API errors (CORS) | Always open the app through the Vite URL (5173). Never call :8000 directly from the browser; the proxy keeps everything same-origin. |
| `database is locked` (SQLite) | Close extra `sqlite3`/DB browser sessions on `backend/institrace.db`. |
| `relation does not exist` (PostgreSQL) | You skipped migrations: run `alembic upgrade head` from `backend/`. |
| Login 401 | Credentials table above; passwords are also overridable in `.env`. |

Repository layout:

```
INSTITRACE/
├── backend/            FastAPI app, matching engine, services, alembic, pytest suite
│   ├── app/            main.py, models.py, schemas.py, seed.py, matching/, services/, routers/
│   ├── alembic/        migration environment + initial schema migration
│   └── tests/          49 backend tests (matching, workflow, deadlines, reports, reliability)
├── frontend/           React + Vite + TypeScript SPA (pages/, components/, api/)
├── docs/               architecture, schema, matching rules, API reference, traceability,
│                       test report, demo script, known limitations
├── .env.example        configuration template (copy to .env)
└── .gitignore
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — architecture diagram and module map
- [docs/database-schema.md](docs/database-schema.md) — ER diagram, tables, constraints
- [docs/matching-engine.md](docs/matching-engine.md) — rule definitions and safeguards
- [docs/api-reference.md](docs/api-reference.md) — endpoint reference
- [docs/requirements-traceability.md](docs/requirements-traceability.md) — requirement ↔ implementation ↔ tests
- [docs/test-report.md](docs/test-report.md) — actual commands and results
- [docs/demo-script.md](docs/demo-script.md) — the 3–5 minute judge demo
- [docs/known-limitations.md](docs/known-limitations.md) — honest gap list
