# InfoTrust — Working State

## 1. Project Identity
- **Project Name:** InfoTrust
- **Full Project Purpose:** A hybrid credibility engine and AI Analysis Service designed to evaluate the factual integrity of text claims, utilizing a fine-tuned misinformation classification model.
- **Current Architecture:** Contract-first REST API separating the frontend, backend, and an isolated AI inference service.
- **Backend Technology:** Django 5.2 LTS, Django Ninja
- **Frontend Technology:** React, Vite, TailwindCSS
- **Database:** PostgreSQL
- **Authentication Technology:** JWT using `django-ninja-jwt`
- **ML/Model Technology:** DeBERTa-v3-base model (fine-tuned)
- **Important Architectural Constraints:** Strictly no Django REST Framework, business logic confined completely to the Service Layer, and a unified PostgreSQL database structure.

## 2. Canonical Documentation
The project relies on exactly 8 canonical project MD files:
1. `PROJECT_RULES.md`
2. `PRD.md`
3. `ARCHITECTURE.md`
4. `API_SPEC.md`
5. `DECISIONS.md`
6. `TASK.md`
7. `PROMPTS.md`
8. `README.md`

**These are the project's source-of-truth documents.**
- Do NOT create `DATABASE.md`, `UI_UX.md`, or other project-level specification documents unless explicitly required later.
- `PROJECT_RULES.md` has the absolute highest priority when resolving conflicts.

## 3. Current Git / Repository State
- **Current Branch:** `main`
- **Latest Relevant Commit:** `9379a83 feat: implement login api`
- **Working Tree:** Clean
- **Remote State:** Up to date with `origin/main`

## 4. Environment
- **OS/Environment:** Windows
- **Python Version:** 3.12.6 (VERIFIED)
- **Node Version:** v22.19.0 (VERIFIED)
- **npm Version:** 10.9.3 (VERIFIED)
- **Django Version:** 5.2.17 (VERIFIED)
- **Django Ninja Version:** 1.7.0 (VERIFIED)
- **React Version:** 19.2.8 (VERIFIED)
- **Vite Version:** 8.2.2 (VERIFIED)
- **Tailwind Version:** 4.3.3 (VERIFIED)
- **PostgreSQL Status:** UNAVAILABLE LOCALLY
- **Docker Status:** UNVERIFIED
- **Backend Virtual Environment:** Exists and active (VERIFIED)

## 5. Completed Implementation Tasks
| Task ID  | Task Name | Status | Important Implementation Details | Commit Status |
|----------|-----------|--------|----------------------------------|---------------|
| INIT-001 | Project Initialization | Complete | Basic scaffolding | Verified |
| INIT-002 | Backend Setup | Complete | Django base structure | Verified |
| INIT-003 | Database Setup | Complete | PostgreSQL bindings in base.py | Verified |
| INIT-004 | Frontend Setup | Complete | React/Vite/Tailwind scaffolding | Verified |
| INIT-005 | API Design & Routing | Complete | Django Ninja root router | Verified |
| INIT-006 | Frontend Routing | Complete | React Router | Verified |
| INIT-007 | Shared Components | Complete | Baseline UI elements | Verified |
| INIT-008 | Deployment Configuration | Complete | Dockerfile | Verified |
| INIT-009 | CI/CD Setup | Complete | GitHub Actions | Verified |
| INIT-010 | Core Services | Complete | Service layer boundaries defined | Verified |
| INIT-011 | ML Integration Setup | Complete | AI Service scaffolding | Verified |
| INIT-012 | Finalize Architecture | Complete | Canonical documentation lockdown | Verified |
| AUTH-001 | Authentication App Setup | Complete | Django App creation | Verified |
| AUTH-002 | Custom User Model | Complete | UUID PK, email USERNAME_FIELD | Verified |
| AUTH-003 | User Manager | Complete | Hashing and role mapping | Verified |
| AUTH-004 | JWT Configuration | Complete | `django-ninja-jwt` implementation | Verified |
| AUTH-005 | Registration Serializer | Complete | `RegistrationIn` Pydantic Schema | Verified |
| AUTH-006 | Registration Service | Complete | `register_user` logic and DB Integrity | Verified |
| AUTH-007 | Registration API | Complete | `POST /register` Endpoint mapping | Verified |
| AUTH-008 | Registration API Tests | Complete | HTTP Integration Tests | Verified |
| AUTH-009 | Login Serializer | Complete | `LoginIn` Schema implementation | Verified |
| AUTH-010 | Login Service | Complete | `authenticate_user` implementation | Verified |
| AUTH-011 | Implement Login API | Complete | `POST /login` mapping and exception handlers | Verified |

## 6. Authentication State
- **User Model:** Custom User model utilizing a UUID primary key, identifying users via `email` (`USERNAME_FIELD`). Tracks `full_name`, `role` (USER/ADMIN), and `is_active`.
- **UserManager:** Creates users and superusers, safely hashing passwords.
- **Registration:** Pydantic `RegistrationIn` handles syntax and regex validation. Service layer isolates database integrity and transactions. API layer translates zero-knowledge exceptions to standard `409` or `422` HTTP structures.
- **Login:** `LoginIn` schema explicitly requires email/password without complexity limits to support legacy systems. `authenticate_user()` service applies safe manual hash mitigation to prevent missing-email enumeration.
- **JWT Technology:** `django-ninja-jwt` is configured globally (`ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`). Tokens are generated via `RefreshToken.for_user(user)`.
- **Security Assertions:** 
  - Django REST Framework (DRF) is explicitly NOT used.
  - `djangorestframework-simplejwt` is explicitly NOT used.
  - Plaintext passwords are never logged, serialized, or returned.

## 7. Current API Endpoints
1. `POST /api/v1/auth/register`
   - **Purpose:** Create a new user account.
   - **Request Schema:** `RegistrationIn`
   - **Response Behavior:** `201` -> `RegistrationSuccessOut` (containing nested filtered `UserOut`). `422` for bad syntax, `409` for duplicate emails.
   - **Authentication:** Guest

2. `POST /api/v1/auth/login`
   - **Purpose:** Authenticate an existing user and distribute JWTs.
   - **Request Schema:** `LoginIn`
   - **Response Behavior:** `200` -> `LoginSuccessOut` (containing tokens and `UserOut`). `401` for bad credentials, `403` for disabled accounts, `422` for syntax failures.
   - **Authentication:** Guest

## 8. Current Test State
- **Authentication Test Count:** 21 Tests.
- **Latest Test Result:** `Ran 21 tests in 6.787s - OK`.
- **Checks:** `python manage.py check` reports 0 issues.
- **Migrations:** `python manage.py makemigrations --check` detects no unstaged changes.
- **Known Limitations:** Because PostgreSQL is unavailable locally, tests currently execute by dynamically patching `base.py` to `sqlite3`, running the suite, and explicitly reverting `base.py` immediately. 
- **Known Warnings:** Executing the tests locally using the dummy environment variable `SECRET_KEY="test"` natively triggers PyJWT's `InsecureKeyLengthWarning`. This is an accepted, test-only behavior.

## 9. Database / Infrastructure State
- **PostgreSQL Configuration:** Fully defined in `docker-compose.yml` and bound within `backend/config/settings/base.py`.
- **PostgreSQL Status:** UNAVAILABLE LOCALLY. Database-backed migration and runtime verification against the true Postgres container remains pending.

## 10. ML State
- **Model:** DeBERTa-v3-base (fine-tuned)
- **Output:** Binary ML classification backing a three-class final credibility verdict.
- **Status:** ML experimentation is assumed complete/frozen according to canonical docs. Backend integration of the inference service remains entirely pending.

## 11. Important Architectural Decisions
These decisions must NOT be casually altered:
- Django 5.2 LTS + Django Ninja.
- PostgreSQL as the single source of truth database.
- Custom User Model enforcing email as the primary login field.
- `django-ninja-jwt` strictly replaces DRF/Simple JWT.
- Replaceable, independent AI model architecture with no generalized LLM components.
- Google Fact Check API augmentation.

## 12. Known Issues / Technical Debt
- PostgreSQL is currently unavailable locally, requiring an artificial SQLite execution bridge for unit testing.
- Database-backed migration/runtime verification against a live Postgres system is pending.
- API error-envelope inconsistency (`error_code` vs `errors`) remains noted across documentation and will require harmonization in future sweeps.

## 13. EXACT NEXT STEP
**CURRENT LAST COMPLETED TASK:**
AUTH-011 — Implement Login API

**NEXT TASK:**
AUTH-012

*AUTH-012 has NOT been implemented.*

The next developer/AI MUST:
1. Read `PROJECT_RULES.md`.
2. Read `TASK.md` and identify the exact AUTH-012 requirements.
3. Inspect relevant existing implementation.
4. Produce a **PLAN ONLY**.
5. Have the plan reviewed before implementation.
6. Implement ONLY AUTH-012 after approval.
7. Run appropriate tests/checks.
8. Stop and wait for review.
9. Do not automatically proceed to AUTH-013.

## 14. Development Workflow
**PLAN → REVIEW → IMPLEMENT ONE TASK → TEST → REVIEW/REFACTOR → COMMIT → NEXT TASK**
- Never allow the AI to automatically continue to the next task.
- Review plans before implementation.
- Review implementation reports before committing.
- Commit each completed task separately.
- Do not mix unrelated tasks in one commit.
- Follow canonical documentation hierarchy.
- Do not blindly accept AI claims; verify against repository state.
- Do not install dependencies unless justified by the canonical task/architecture.
- Do not create unnecessary documentation files.

## 15. Handoff Instructions for the Next ChatGPT Account
"Start by reading `WORKING.md` and the 8 canonical project documents. Do not assume `WORKING.md` overrides the canonical documentation. If `WORKING.md` conflicts with the canonical docs, the canonical docs win."

- The current task boundary is AUTH-011 (Complete).
- The next task is AUTH-012.
- **Ask the user to provide or review the AUTH-012 planning step.**
- **Do NOT implement immediately.**
- Continue using the strict **PLAN → REVIEW → IMPLEMENT → TEST → COMMIT** workflow.

## 16. Verification Metadata
- **Date:** 2026-09-12T17:03:00+05:30
- **Branch:** `main`
- **Latest Verified Commit:** `9379a83`
- **Working Tree Status:** Clean

*This file is a handoff snapshot designed to preserve context across ChatGPT sessions and is NOT a replacement for canonical project documentation.*
