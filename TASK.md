# TASK.md

> **Project:** InfoTrust – AI-Powered Misinformation Detection & Claim Analysis Platform
>
> **Purpose:** This document is the master engineering backlog for the project. Every implementation task should originate from this file.
>
> **Development Philosophy:**
> - Complete one task at a time.
> - Do not skip dependencies.
> - Every completed task must be testable.
> - No feature is considered complete until its Definition of Done (DoD) is satisfied.
> - Refactor continuously to maintain clean architecture.
> - Follow the architecture defined in `ARCHITECTURE.md`.

---

# Development Workflow

Every milestone follows the same lifecycle:

```text
Planning
    ↓
Implementation
    ↓
Testing
    ↓
Code Review
    ↓
Refactoring
    ↓
Documentation
    ↓
Completion
```

Never move to the next milestone until the current milestone is fully complete.

---

# Task Priority Levels

| Priority | Meaning |
|----------|---------|
| P0 | Critical – Blocks further development |
| P1 | High – Core feature |
| P2 | Medium – Important but non-blocking |
| P3 | Low – Nice to have |

---

# Complexity Scale

| Level | Description |
|-------|-------------|
| S | Small (<1 hour) |
| M | Medium (1–3 hours) |
| L | Large (3–6 hours) |
| XL | Very Large (>6 hours) |

---

# Task Status

Every task should always be in one of these states:

- ⬜ Not Started
- 🟨 In Progress
- 🟩 Completed
- 🟥 Blocked
- 🔄 Needs Refactoring

---

# Milestone 1 — Project Initialization

## Goal

Create a clean, scalable, production-ready foundation for InfoTrust before implementing business logic.

This milestone establishes:

- Git repository
- Modular project structure
- Django REST backend
- React + TypeScript frontend
- PostgreSQL database
- Docker development environment
- Environment configuration
- Code quality tools
- Initial documentation

No authentication, database models, or AI functionality are implemented during this milestone.

---

## Deliverables

- Git repository initialized
- Django REST backend created
- React + TypeScript frontend created
- Feature-based folder structure established
- Docker configured
- PostgreSQL connected
- Environment variables configured
- Development tooling configured
- Initial documentation completed
- Local development environment verified

---

## Dependencies

None.

This is the starting point of the project.

---

# Task List

---

## INIT-001

### Title

Create Git Repository

**Priority:** P0

**Complexity:** S

### Tasks

- Create GitHub repository
- Clone repository locally
- Initialize Git
- Verify remote connection
- Protect the `main` branch (optional)

### Definition of Done

- Repository created
- Push and pull work correctly

---

## INIT-002

### Title

Create Root Folder Structure

**Priority:** P0

**Complexity:** S

### Expected Structure

```text
InfoTrust/
│
├── backend/
├── frontend/
├── docs/
├── scripts/
├── docker/
├── .github/
└── README.md
```

### Definition of Done

Project structure matches `ARCHITECTURE.md`.

---

## INIT-003

### Title

Initialize Django Backend

**Priority:** P0

**Complexity:** M

### Tasks

- Create Django project
- Install Django Ninja
- Configure settings package
- Create `apps/` directory
- Verify development server starts

### Definition of Done

Backend starts successfully.

---

## INIT-004

### Title

Initialize React Frontend

**Priority:** P0

**Complexity:** M

### Tasks

- Create React project using Vite
- Enable TypeScript
- Configure project structure
- Verify development server starts

### Definition of Done

Frontend starts successfully.

---

## INIT-005

### Title

Configure Git Ignore

**Priority:** P0

**Complexity:** S

### Include

- Python cache
- Node modules
- Build folders
- Environment files
- IDE settings
- Logs
- Coverage reports

### Definition of Done

No unnecessary files are tracked.

---

## INIT-006

### Title

Configure Environment Variables

**Priority:** P0

**Complexity:** S

### Create

Backend

```text
.env.example
```

Frontend

```text
.env.example
```

### Document Variables

- SECRET_KEY
- DEBUG
- DATABASE_URL
- JWT_SECRET
- MODEL_ARTIFACT_PATH
- MODEL_VERSION
- FACT_CHECK_API_KEY
- ALLOWED_HOSTS

No secrets should be committed.

---

## INIT-007

### Title

Install Backend Dependencies

**Priority:** P0

**Complexity:** M

### Install

- Django
- Django Ninja
- Simple JWT
- psycopg
- django-cors-headers
- python-dotenv
- Pillow
- requests
- sentence-transformers
- transformers
- torch
- scikit-learn
- pandas
- numpy

### Verify

Backend starts successfully.

---

## INIT-008

### Title

Install Frontend Dependencies

**Priority:** P0

**Complexity:** M

### Install

- React Router
- Axios
- Tailwind CSS
- React Hook Form
- Zod
- TanStack Query
- Recharts

### Verify

Frontend builds successfully.

---

## INIT-009

### Title

Configure Tailwind CSS

**Priority:** P1

**Complexity:** S

### Tasks

- Install Tailwind CSS
- Configure content paths
- Add global styles
- Verify styling works

---

## INIT-010

### Title

Configure PostgreSQL Connection

**Priority:** P0

**Complexity:** M

### Tasks

- Create PostgreSQL database
- Configure connection
- Run migrations
- Verify database connectivity

### Definition of Done

Backend connects successfully to PostgreSQL.

---

## INIT-011

### Title

Configure CORS

**Priority:** P1

**Complexity:** S

### Tasks

- Configure allowed origins
- Restrict credentials
- Verify frontend-backend communication

### Definition of Done

Cross-origin requests work correctly.

---

## INIT-012

### Title

Create Docker Configuration

**Priority:** P1

**Complexity:** L

### Create

- Backend Dockerfile
- Frontend Dockerfile
- docker-compose.yml

### Verify

Entire application starts using Docker Compose.

---

## INIT-013

### Title

Configure Code Quality Tools

**Priority:** P2

**Complexity:** M

### Backend

- Ruff
- Black
- isort

### Frontend

- ESLint
- Prettier

### Goal

Consistent formatting and linting across the project.

---

## INIT-014

### Title

Configure Development Workspace

**Priority:** P3

**Complexity:** S

### Recommended

- Python extension
- ESLint
- Prettier
- Tailwind IntelliSense
- Docker extension

(Optional but recommended.)

---

## INIT-015

### Title

Create Initial README

**Priority:** P2

**Complexity:** M

### Include

- Project overview
- Technology stack
- Setup instructions
- Folder structure
- Local development
- Docker usage

---

## INIT-016

### Title

Verify Local Development Environment

**Priority:** P0

**Complexity:** S

### Checklist

- ✅ Backend starts
- ✅ Frontend starts
- ✅ PostgreSQL connected
- ✅ Environment variables loaded
- ✅ Docker builds successfully
- ✅ Frontend communicates with backend
- ✅ No startup errors

---

# Milestone 1 Verification Checklist

Before continuing, verify:

- Git repository initialized
- Django REST backend operational
- React frontend operational
- PostgreSQL connected
- Docker functioning
- Tailwind configured
- Required dependencies installed
- Environment variables documented
- Code quality tools configured
- README created
- Project structure matches `ARCHITECTURE.md`

---

# Milestone 1 Definition of Done

Milestone 1 is complete only if:

- All INIT tasks are completed.
- Backend and frontend run successfully.
- PostgreSQL is connected.
- Docker environment works correctly.
- Environment variables are configured.
- No hardcoded secrets exist.
- Frontend communicates with backend.
- Project structure follows the approved architecture.
- Documentation has been updated.

Development may proceed to **Milestone 2 — Authentication** only after Milestone 1 is fully complete.

---

# End of Part 1
# Milestone 2 — Authentication & Authorization

## Goal

Implement a secure, scalable, and production-ready authentication system for InfoTrust.

This milestone establishes the complete authentication and authorization foundation required by the platform.

Users should be able to:

- Register
- Log in using email and password
- Receive JWT access and refresh tokens
- Refresh expired access tokens
- Log out securely
- Access protected resources
- Access role-specific functionality
- Retrieve their authenticated profile

Authentication must follow the architecture defined in `ARCHITECTURE.md`.

---

# Deliverables

- Custom User model
- JWT Authentication
- Registration API
- Login API
- Refresh Token API
- Logout API
- Current User API
- Role-Based Access Control (RBAC)
- Protected Backend APIs
- Protected Frontend Routes
- Authentication Context
- Authentication Unit Tests

---

# Dependencies

Requires:

- Milestone 1 completed
- PostgreSQL configured
- Django Ninja installed
- Simple JWT configured

---

# Task List

---

## AUTH-001

### Title

Create Authentication Django App

**Priority:** P0

**Complexity:** S

### Tasks

- Create `authentication` Django app
- Register application in Django settings
- Configure URL routing
- Verify successful startup

### Definition of Done

- Authentication app loads correctly
- URLs registered successfully

---

## AUTH-002

### Title

Implement Custom User Model

**Priority:** P0

**Complexity:** M

### Fields

- UUID (Primary Key)
- Full Name
- Email (Unique)
- Password Hash
- Role
- Is Active
- Created At
- Updated At

### Role Values

- USER
- ADMIN

### Requirements

- Email replaces username
- UUID used as primary key
- Passwords stored using Django's password hashing

### Definition of Done

- Custom User model replaces Django's default User model
- Authentication works using email

---

## AUTH-003

### Title

Implement Custom User Manager

**Priority:** P1

**Complexity:** M

### Responsibilities

- Create regular users
- Create superusers
- Normalize email addresses
- Validate required fields
- Assign default roles

### Definition of Done

- User creation works correctly
- Superuser creation works correctly

---

## AUTH-004

### Title

Configure JWT Authentication

**Priority:** P0

**Complexity:** M

### Tasks

- Configure Simple JWT
- Configure authentication classes
- Configure access token lifetime
- Configure refresh token lifetime
- Enable refresh token rotation
- Enable blacklist support

### Definition of Done

- JWT authentication functions correctly
- Refresh tokens operate correctly

---

## AUTH-005

### Title

Implement Registration Serializer

**Priority:** P0

**Complexity:** M

### Validation Rules

- Full name required
- Valid email required
- Email must be unique
- Password complexity enforced
- Password confirmation must match

### Definition of Done

- Invalid registrations are rejected
- Validation errors returned consistently

---

## AUTH-006

### Title

Implement Registration Service

**Priority:** P0

**Complexity:** M

### Responsibilities

- Validate business rules
- Create user
- Hash password
- Assign default USER role
- Return serialized user

### Architecture Rule

Business logic must remain inside the Service Layer.

### Definition of Done

- Users are created only through the service layer

---

## AUTH-007

### Title

Create Registration API

**Priority:** P0

**Complexity:** M

### Endpoint

```http
POST /api/v1/auth/register
```

### Response

Successful registration returns:

- Success status
- User information

Validation errors return standardized error responses.

### Definition of Done

- Users can successfully register
- Duplicate emails are rejected

---

## AUTH-008

### Title

Test Registration API

**Priority:** P0

**Complexity:** S

### Verify

- Successful registration
- Duplicate email rejection
- Password validation
- Missing field validation
- Password hashing

### Definition of Done

All registration tests pass.

---

## AUTH-009

### Title

Implement Login Serializer

**Priority:** P0

**Complexity:** S

### Validate

- Email
- Password

### Definition of Done

Invalid payloads are rejected before authentication.

---

## AUTH-010

### Title

Implement Login Service

**Priority:** P0

**Complexity:** M

### Responsibilities

- Authenticate credentials
- Verify active account
- Generate Access Token
- Generate Refresh Token
- Return authenticated user

### Definition of Done

Valid credentials produce JWT tokens.

---

## AUTH-011

### Title

Create Login API

**Priority:** P0

**Complexity:** M

### Endpoint

```http
POST /api/v1/auth/login
```

### Response

- Access Token
- Refresh Token
- User Profile

### Definition of Done

Successful authentication returns valid JWT tokens.

---

## AUTH-012

### Title

Test Login API

**Priority:** P0

**Complexity:** S

### Verify

- Valid login
- Invalid password
- Unknown email
- Disabled account
- Inactive account
- Standardized error responses

### Definition of Done

All login scenarios behave correctly.

---

## AUTH-013

### Title

Implement Refresh Token API

**Priority:** P1

**Complexity:** S

### Endpoint

```http
POST /api/v1/auth/refresh
```

### Responsibilities

- Validate refresh token
- Generate new access token
- Reject expired or invalid refresh tokens

### Definition of Done

Authenticated users can obtain a new access token without logging in again.

---

## AUTH-014

### Title

Implement Logout API

**Priority:** P1

**Complexity:** M

### Endpoint

```http
POST /api/v1/auth/logout
```

### Responsibilities

- Blacklist refresh token
- Invalidate future refresh attempts
- Return success response

### Definition of Done

Logged-out refresh tokens cannot be reused.

---

## AUTH-015

### Title

Create Current User API

**Priority:** P1

**Complexity:** S

### Endpoint

```http
GET /api/v1/auth/me
```

### Returns

- User ID
- Full Name
- Email
- Role
- Account Status
- Created At

### Definition of Done

Authenticated users can retrieve their profile information.

---

## AUTH-016

### Title

Implement Role-Based Access Control (RBAC)

**Priority:** P0

**Complexity:** M

### Roles

- Guest
- User
- Admin

### Responsibilities

- Restrict protected endpoints
- Restrict administrative endpoints
- Verify ownership where required

### Definition of Done

Permissions are enforced consistently across the application.

---

## AUTH-017

### Title

Create Authentication Unit Tests

**Priority:** P1

**Complexity:** M

### Test Cases

- Registration
- Login
- JWT validation
- Refresh token
- Logout
- Current user endpoint
- Permission checks

### Definition of Done

All authentication tests pass.

---

## AUTH-018

### Title

Create Frontend Authentication Pages

**Priority:** P1

**Complexity:** M

### Pages

- Login
- Register

### Shared Components

- Authentication layout
- Logo and branding
- Form container
- Validation messages
- Loading indicator

### Definition of Done

Authentication pages match the application design system.

---

## AUTH-019

### Title

Build Registration Form

**Priority:** P1

**Complexity:** M

### Fields

- Full Name
- Email
- Password
- Confirm Password

### Validation

- React Hook Form
- Zod Schema Validation

### Requirements

- Client-side validation
- Server-side error display
- Loading state
- Success handling

### Definition of Done

Users can successfully register through the frontend.

---

## AUTH-020

### Title

Build Login Form

**Priority:** P1

**Complexity:** M

### Fields

- Email
- Password

### Validation

- Required fields
- Email format
- Password required

### Requirements

- Loading state
- Error handling
- Successful redirection
- Accessible form controls

### Definition of Done

Users can successfully authenticate through the frontend.

---

## AUTH-021

### Title

Create Authentication API Client

**Priority:** P1

**Complexity:** M

### Responsibilities

Provide reusable API methods for:

- Register
- Login
- Logout
- Refresh Token
- Get Current User

### Architecture Rule

All authentication requests should be centralized in a single API service.

### Definition of Done

Frontend uses a single authentication service for all auth requests.

---

## AUTH-022

### Title

Implement Secure Token Storage

**Priority:** P1

**Complexity:** M

### Responsibilities

- Store Access Token securely
- Store Refresh Token securely
- Automatically remove tokens on logout
- Prevent unauthorized access after logout

### Note

For the MVP, JWTs may be stored in browser storage as defined in the project architecture. The implementation should remain flexible enough to migrate to HttpOnly cookies in future versions.

### Definition of Done

Authentication tokens are managed securely throughout the user session.



## AUTH-023

### Title

Implement Protected Routes

Priority:

P0

Complexity:

M

Protect:

- Dashboard
- Submit Claim
- Claim History
- Profile
- Settings
- Admin Dashboard

Behavior:

Unauthenticated users are redirected to Login.

Definition of Done:

Protected pages cannot be accessed without authentication.

---

## AUTH-024

### Title

Implement Role-Based Route Guards

Priority:

P1

Complexity:

M

Rules:

Guest

- Public pages only

User

- User dashboard
- Submit claims
- View own history
- Manage own profile

Admin

- Full administrative access

Definition of Done:

Role-based frontend routing matches backend authorization.

---

## AUTH-025

### Title

Implement Persistent Authentication

Priority:

P2

Complexity:

M

Requirements:

- Automatically refresh expired access tokens
- Restore authenticated session after browser refresh
- Redirect to login when refresh fails

Definition of Done:

Users remain logged in without unnecessary re-authentication.

---

## AUTH-026

### Title

Implement Global Authentication Context

Priority:

P1

Complexity:

M

Context should provide:

- Current user
- Authentication status
- User role
- Login function
- Logout function
- Loading state

Definition of Done:

Authentication state is available throughout the application.

---

## AUTH-027

### Title

Handle Authentication Errors

Priority:

P1

Complexity:

S

Handle:

- Invalid credentials
- Duplicate email
- Expired access token
- Invalid refresh token
- Unauthorized requests
- Network failures
- Server errors

Display:

- User-friendly messages
- No internal server details

Definition of Done:

Authentication failures are handled gracefully.

---

## AUTH-028

### Title

Verify Complete Authentication Flow

Priority:

P0

Complexity:

M

End-to-End Flow:

Register

↓

Login

↓

Receive JWT Tokens

↓

Access Protected Dashboard

↓

Access Protected APIs

↓

Refresh Access Token

↓

Logout

↓

Protected Routes Blocked

↓

Protected APIs Return 401

Definition of Done:

Complete authentication lifecycle works exactly as designed.

---

# Milestone 2 Verification Checklist

Verify:

✓ Custom User Model implemented

✓ JWT authentication working

✓ Registration API operational

✓ Login API operational

✓ Refresh Token API operational

✓ Logout API operational

✓ Current User endpoint operational

✓ Password hashing enabled

✓ Role-based permissions enforced

✓ Protected APIs secured

✓ Protected frontend routes secured

✓ Authentication Context implemented

✓ Persistent login working

✓ Automated authentication tests passing

✓ Documentation updated

---

# Milestone 2 Definition of Done

Milestone 2 is complete only if:

- Custom User Model replaces Django's default user model.
- JWT authentication functions correctly.
- Users can register, log in, refresh tokens, and log out.
- Protected APIs reject unauthorized requests.
- Role-based authorization is enforced on both backend and frontend.
- Authentication state persists correctly.
- Frontend authentication flow is fully integrated.
- Automated authentication tests pass.
- Documentation is updated.

Only after Milestone 2 is complete should development proceed to **Milestone 3 — Database & Core Domain Models**.

---

# End of Part 2
# Milestone 3 — Database & Core Domain Models

## Goal

Implement the complete database schema and core domain models for InfoTrust.

This milestone establishes:

- Core database tables
- Model relationships
- Constraints
- Indexes
- Validation rules
- Django Admin registration
- Initial seed data

No AI inference or claim analysis is implemented yet.

---

# Deliverables

- Database schema implemented
- Django models created
- Relationships verified
- Migrations completed
- Constraints enforced
- Django Admin configured
- Seed data available

---

# Dependencies

Requires:

- Milestone 1 completed
- Milestone 2 completed

---

# Task List

---

## DB-001

### Title

Create Claims Django App

Priority:

P0

Complexity:

S

Tasks:

- Create claims app
- Register app
- Verify startup

Definition of Done:

Claims app loads successfully.

---

## DB-002

### Title

Create Analysis Django App

Priority:

P0

Complexity:

S

Tasks:

- Create analysis app
- Register app
- Verify startup

Definition of Done:

Analysis app loads successfully.

---

## DB-003

### Title

Create Audit Django App

Priority:

P1

Complexity:

S

Purpose:

Store audit logs and administrative actions.

---

## DB-004

### Title

Implement Claim Model

Priority:

P0

Complexity:

M

Fields include:

- UUID
- User
- Claim Text
- Status
- Submitted At
- Updated At

Relationships:

User → Claims (One-to-Many)

Definition of Done:

Claim model migrated successfully.

---

## DB-005

### Title

Implement Analysis Model

Priority:

P0

Complexity:

L

Fields include:

- Claim
- Credibility Score
- Verdict
- Explainability JSON
- Model Prediction
- Model Confidence
- Analysis Timestamp

Relationship:

Claim → Analysis (One-to-One)

Definition of Done:

Analysis model migrated successfully.

---

## DB-006

### Title

Extend Analysis Model for Hybrid Credibility Engine

Priority:

P1

Complexity:

L

Store structured outputs from the Hybrid Credibility Engine:

- Model Prediction
- Model Confidence
- Fact-check Summary
- Fact-check Match Count
- Narrative Match Count
- Highest Similarity Score
- Rule-based Flags
- Final Weighted Score

Purpose:

Support explainability, analytics, and future model improvements.

---

## DB-007

### Title

Implement Claim Feedback Model

Priority:

P1

Complexity:

M

Fields:

- User
- Claim
- Feedback Type

Allowed values:

- HELPFUL
- NOT_HELPFUL

Constraint:

One feedback entry per user per claim.

---

## DB-008

### Title

Implement Audit Log Model

Priority:

P1

Complexity:

M

Fields:

- User
- Action
- Target
- Metadata
- Timestamp

Purpose:

Track important administrative actions.

---

## DB-009

### Title

Configure Foreign Key Relationships

Priority:

P0

Complexity:

S

Verify:

- User → Claims
- Claim → Analysis
- Claim → Feedback
- User → Feedback
- User → Audit Logs

---

## DB-010

### Title

Add Database Constraints

Priority:

P0

Complexity:

M

Examples:

- Unique email
- Unique feedback
- Score range (0–100)
- Valid verdict values
- Non-null claim text

---

## DB-011

### Title

Add Database Indexes

Priority:

P1

Complexity:

M

Indexes:

- User email
- Claim submission date
- Claim owner
- Verdict
- Credibility score
- Audit timestamp

---

## DB-012

### Title

Implement Model Validation

Priority:

P1

Complexity:

M

Validate:

- Claim length
- Score range
- Enum values
- Required fields

---

## DB-013

### Title

Generate Initial Database Migrations

Priority:

P0

Complexity:

S

Tasks:

- Create migrations
- Review generated SQL
- Apply migrations

---

## DB-014

### Title

Register Models in Django Admin

Priority:

P1

Complexity:

M

Register:

- Users
- Claims
- Analyses
- Feedback
- Audit Logs

Configure:

- Search
- Filters
- List Display

---

## DB-015

### Title

Create Seed Data Command

Priority:

P2

Complexity:

M

Generate:

- Admin user
- Sample users
- Sample claims
- Sample analysis results

Purpose:

Simplify local development, testing, and demonstrations.

---

## DB-016

### Title

Verify Relationship Integrity

Priority:

P0

Complexity:

S

Check:

- Cascade behavior
- Protected deletes
- Related object access

---

## DB-017

### Title

Verify Constraint Enforcement

Priority:

P0

Complexity:

S

Attempt invalid operations:

- Duplicate feedback
- Invalid verdict
- Out-of-range score
- Empty claim

Ensure the database rejects invalid data.

---

## DB-018

### Title

Create Model Unit Tests

Priority:

P1

Complexity:

L

Test:

- Model creation
- Relationships
- Constraints
- Validation
- Cascade behavior

---

## DB-019

### Title

Document Database Schema

Priority:

P2

Complexity:

S

Update documentation with:

- ER Diagram
- Model descriptions
- Relationships
- Constraints

---

## DB-020

### Title

Verify Database Readiness

Priority:

P0

Complexity:

S

Checklist:

✓ All models created

✓ Migrations applied

✓ Relationships verified

✓ Constraints enforced

✓ Django Admin operational

✓ Tests passing

---

# Milestone 3 Verification Checklist

Verify:

✓ Claim model implemented

✓ Analysis model implemented

✓ Hybrid Credibility Engine fields present

✓ Feedback model operational

✓ Audit log model operational

✓ Foreign keys configured

✓ Constraints enforced

✓ Indexes created

✓ Django Admin configured

✓ Seed data generated

✓ Unit tests passing

✓ Documentation updated

---

# Milestone 3 Definition of Done

Milestone 3 is complete only if:

- All core models exist.
- Database schema matches `ARCHITECTURE.md`.
- Migrations are complete and reproducible.
- Relationships and constraints are verified.
- Django Admin provides management capabilities.
- Seed data can initialize a development environment.
- Model tests pass successfully.

Development may proceed to **Milestone 4 — Backend Foundation & REST APIs** only after all database tasks are complete.

---

# End of Part 3
# Milestone 4 — Backend Foundation & REST APIs

## Goal

Build the complete backend API foundation for InfoTrust.

This milestone implements:

- REST API architecture
- Claim Management APIs
- Validation
- Service Layer
- Selector Layer
- API documentation
- Error handling
- API testing

At the end of this milestone, the backend is fully functional **without running the Hybrid Credibility Engine**.

Claims can be created, viewed, updated, and deleted independently of the analysis pipeline.

---

# Deliverables

- REST API structure
- Claim CRUD APIs
- Service layer
- Selector layer
- Serializer layer
- Validation
- Error handling
- Pagination
- Filtering
- Search
- API documentation

---

# Dependencies

Requires:

- Milestone 1 completed
- Milestone 2 completed
- Milestone 3 completed

---

# Task List

---

## API-001

### Title

Create API Version Structure

Priority:

P0

Complexity:

S

Tasks:

- Create `/api/v1/`
- Configure routing
- Register endpoints

Definition of Done:

Versioned routing is operational.

---

## API-002

### Title

Create Common API Response Format

Priority:

P0

Complexity:

S

Standardize:

- Success response
- Error response
- Validation response

Purpose:

Maintain consistency across all APIs.

---

## API-003

### Title

Create Custom Exception Handler

Priority:

P0

Complexity:

M

Handle:

- Validation errors
- Authentication errors
- Permission errors
- Database exceptions
- Unexpected exceptions

Return standardized JSON responses.

---

## API-004

### Title

Create Claim Serializer

Priority:

P0

Complexity:

M

Responsibilities:

- Validate claim text
- Enforce length limits
- Reject empty submissions

---

## API-005

### Title

Create Claim Validators

Priority:

P1

Complexity:

S

Custom validation rules:

- Maximum length
- Minimum meaningful length
- Plain text only
- Trim leading/trailing whitespace

---

## API-006

### Title

Create Claim Service

Priority:

P0

Complexity:

L

Business logic:

- Submit claim
- Update claim
- Delete claim
- Retrieve claim

Business logic must reside in the service layer.

Views should remain thin.

---

## API-007

### Title

Create Claim Selectors

Priority:

P1

Complexity:

M

Read operations:

- Get claim
- List claims
- User claim history
- Recent claims

Selectors must not modify data.

---

## API-008

### Title

Create Submit Claim API

Priority:

P0

Complexity:

M

Endpoint:

POST

```
/api/v1/claims/
```

Result:

Claim stored successfully.

The Hybrid Credibility Engine is **not executed** during this milestone.

---

## API-009

### Title

Create Claim Detail API

Priority:

P0

Complexity:

M

Endpoint:

GET

```
/api/v1/claims/{id}
```

Return:

Complete claim information.

---

## API-010

### Title

Create User Claim History API

Priority:

P0

Complexity:

M

Endpoint:

GET

```
/api/v1/claims/history
```

Supports:

- Pagination
- Sorting

---

## API-011

### Title

Create Update Claim API

Priority:

P1

Complexity:

M

Endpoint:

PUT/PATCH

Rules:

- Only the owner may edit the claim.
- Claims can only be edited before analysis begins.

---

## API-012

### Title

Create Delete Claim API

Priority:

P1

Complexity:

M

Rules:

User:

- Soft delete own claim.

Admin:

- Delete or moderate any claim.

---

## API-013

### Title

Implement Pagination

Priority:

P1

Complexity:

S

Apply to:

- Claim history
- Administrative lists

---

## API-014

### Title

Implement Search

Priority:

P1

Complexity:

M

Search by:

- Claim text
- Submission date

---

## API-015

### Title

Implement Filtering

Priority:

P1

Complexity:

M

Filters:

- Analysis status
- Verdict (future-ready)
- Submission date
- User

---

## API-016

### Title

Implement Ordering

Priority:

P2

Complexity:

S

Allow sorting by:

- Submission date
- Credibility score
- Analysis status

---

## API-017

### Title

Implement Permissions

Priority:

P0

Complexity:

M

Verify:

Guest

↓

Cannot access protected APIs

User

↓

Can access only their own resources

Admin

↓

Can access all resources

---

## API-018

### Title

Implement Audit Logging

Priority:

P1

Complexity:

M

Log:

- Claim submitted
- Claim updated
- Claim deleted

---

## API-019

### Title

Implement API Rate Limiting

Priority:

P2

Complexity:

M

Protect:

- Authentication endpoints
- Claim submission endpoint
- Analysis endpoint (future milestone)

---

## API-020

### Title

Generate OpenAPI Documentation

Priority:

P2

Complexity:

M

Include:

- Endpoints
- Request schema
- Response schema
- Authentication
- Error responses

---

## API-021

### Title

Write API Unit Tests

Priority:

P1

Complexity:

L

Test:

- CRUD operations
- Permissions
- Validation
- Error handling

---

## API-022

### Title

Write Integration Tests

Priority:

P1

Complexity:

L

Verify:

- End-to-end API flow
- Frontend-compatible responses
- Authentication and authorization

---

## API-023

### Title

Performance Review

Priority:

P2

Complexity:

S

Check:

- Query counts
- N+1 queries
- Slow endpoints

Optimize where necessary.

---

## API-024

### Title

Finalize Backend API Layer

Priority:

P0

Complexity:

S

Checklist:

✓ Endpoints complete

✓ Validation complete

✓ Tests passing

✓ Documentation updated

✓ Error handling verified

---

# Milestone 4 Verification Checklist

Verify:

✓ API versioning working

✓ CRUD operations complete

✓ Service layer implemented

✓ Selector layer implemented

✓ Validation complete

✓ Permissions enforced

✓ Pagination working

✓ Search working

✓ Filtering working

✓ Ordering working

✓ Audit logging active

✓ API documentation generated

✓ Tests passing

---

# Milestone 4 Definition of Done

Milestone 4 is complete only if:

- All REST endpoints are operational.
- Backend follows the approved architecture.
- Business logic resides in the service layer.
- Read operations use selectors.
- Standardized API responses are implemented.
- Validation is enforced.
- Permissions are correctly applied.
- Automated tests pass.
- Documentation is updated.

Development may proceed to **Milestone 5 — Hybrid Credibility Engine** only after the backend foundation is stable.

---

# End of Part 4
# Milestone 5 — Hybrid Credibility Engine & Narrative Activity

## Goal

Implement the complete AI-powered claim analysis pipeline.

This milestone transforms a submitted claim into a complete credibility analysis by combining multiple evidence sources.

The Hybrid Credibility Engine consists of:

- Claim preprocessing
- Fine-tuned misinformation classification model inference
- Fact-check retrieval
- Narrative Activity detection
- Rule-based validation
- Weighted credibility scoring
- Explainability generation

At the end of this milestone, InfoTrust can analyze claims and generate explainable verdicts.

---

# Deliverables

- AI pipeline
- Hybrid Credibility Engine
- Fine-tuned model training and evaluation
- Versioned model artifact
- Fine-tuned model integration
- Fact-check integration
- Narrative Activity Engine
- Explainability Panel data
- Credibility scoring
- Verdict generation
- Analysis persistence

---

# Dependencies

Requires:

- Milestones 1–4 completed
- Backend APIs operational

---

# Task List

---

## AI-001

### Title

Create AI App Structure

Priority:

P0

Complexity:

S

Tasks:

- Create AI services package
- Create inference package
- Create engine package
- Create utilities package
- Create model loading package

Definition of Done:

Project structure matches the approved architecture.

---

## AI-002

### Title

Implement Claim Preprocessing

Priority:

P0

Complexity:

M

Responsibilities:

- Trim whitespace
- Normalize spacing
- Remove invisible characters
- Normalize Unicode text
- Remove unsupported characters
- Validate minimum and maximum length
- Reject empty claims

Output:

Clean claim text ready for model inference.

---

## AI-003A

### Status

COMPLETED

### Title

Fine-tune InfoTrust Misinformation Classification Model

Priority:

P0

Complexity:

XL

Responsibilities:

- Prepare the approved misinformation dataset for training and validation
- Use the approved transformer base model
- Fine-tune the classifier in Google Colab
- Evaluate the trained model using appropriate classification metrics
- Save the trained model and tokenizer artifacts
- Record the model version, training configuration, dataset version, and evaluation results
- Export artifacts in a format consumable by the InfoTrust inference layer

Architecture Rule:

Fine-tuning is a model-development activity. The resulting model must integrate through the existing model adapter/inference interface and must not introduce dependencies into the Hybrid Credibility Engine.

Definition of Done:

A validated, versioned fine-tuned model artifact is available for integration into InfoTrust.

---

## AI-003

### Title

Integrate InfoTrust Fine-tuned Classification Model

Priority:

P0

Complexity:

L

Responsibilities:

- Load the InfoTrust-specific fine-tuned misinformation classification model
- Load the corresponding tokenizer
- Keep the model artifact and version configurable
- Initialize the reusable inference pipeline
- Perform prediction
- Return predicted class
- Return prediction confidence
- Handle inference errors gracefully
- Keep model-specific implementation isolated from the Hybrid Credibility Engine

Output:

Structured prediction generated by the fine-tuned classification model.

Definition of Done:

The fine-tuned model loads successfully and can classify claims through a reusable, replaceable inference service without coupling the rest of InfoTrust to a specific model implementation.

---

## AI-004

### Title

Create Model Inference Service

Priority:

P0

Complexity:

M

Responsibilities:

- Accept cleaned claim text
- Invoke the classification model
- Parse prediction output
- Normalize confidence values
- Return structured inference results
- Handle invalid model outputs

Business logic must remain outside API views.

---

## AI-005

### Title

Integrate Fact-check Service

Priority:

P0

Complexity:

L

Responsibilities:

- Connect to the selected fact-check API
- Query relevant evidence
- Parse API responses
- Normalize returned data
- Handle no-match scenarios
- Handle API failures gracefully

Store:

- Number of matches
- Source names
- Summary
- Evidence URLs

Definition of Done:

Fact-check evidence can be retrieved and normalized for downstream processing.

---

## AI-006

### Title

Create Narrative Activity Engine

Priority:

P0

Complexity:

L

Responsibilities:

- Compare incoming claims with historical claims
- Generate embeddings using Sentence Transformers
- Calculate semantic similarity
- Detect recurring narratives
- Count similar claims
- Identify earliest occurrence
- Identify latest occurrence

Output:

Narrative Activity object containing similarity metrics.

---

## AI-007

### Title

Implement Similarity Scoring

Priority:

P0

Complexity:

L

Calculate:

- Highest similarity score
- Average similarity score
- Number of related claims

Purpose:

Provide semantic similarity signals for the Hybrid Credibility Engine.

Definition of Done:

Similarity metrics are generated consistently for every analyzed claim.

---

## AI-008

### Title

Create Rule-based Validation Layer

Priority:

P1

Complexity:

M

Implement heuristic rules including:

- Excessive capitalization
- Excessive punctuation
- Clickbait phrases
- Sensational wording
- Very short or vague claims
- Spam-like patterns

Output:

Rule-based credibility signals and rule scores.

Definition of Done:

Rule engine successfully evaluates claims and produces structured outputs.

---

## AI-009

### Title

Implement Hybrid Credibility Engine

Priority:

P0

Complexity:

XL

Combine signals from:

- Fine-tuned classification model
- Fact-check service
- Narrative Activity Engine
- Rule-based validation

Responsibilities:

- Apply configurable weights
- Calculate component scores
- Generate final credibility score (0–100)
- Produce structured output for downstream services

Definition of Done:

The Hybrid Credibility Engine successfully combines all available evidence into a single credibility score.

---

## AI-010

### Title

Generate Verdict

Priority:

P0

Complexity:

M

Verdict categories:

- Credible
- Uncertain
- Misleading

Responsibilities:

- Map credibility score to verdict
- Support configurable score thresholds
- Return standardized verdict values

Definition of Done:

Every analyzed claim receives a valid verdict.

---

## AI-011

### Title

Generate Explainability Data

Priority:

P0

Complexity:

L

Produce structured explanation including:

- Model prediction
- Model confidence
- Fact-check findings
- Narrative Activity summary
- Rule-based observations
- Component score breakdown
- Final credibility score

Purpose:

Power the Explainability Panel shown to users.

Definition of Done:

Every analysis includes a complete explainability report.

---

## AI-012

### Title

Persist Analysis Results

Priority:

P0

Complexity:

M

Store:

- Verdict
- Credibility score
- Model prediction
- Model confidence
- Explainability JSON
- Component scores
- Timestamp

Definition of Done:

Analysis results are stored successfully and linked to their claims.

---

## AI-013

### Title

Expose Analysis API

Priority:

P0

Complexity:

M

Endpoint:

POST

```
/api/v1/analysis/{claim_id}
```

Returns:

- Verdict
- Credibility score
- Explainability report
- Supporting evidence

Definition of Done:

Clients can request a complete analysis through the REST API.

---

## AI-014

### Title

Implement Analysis Status Tracking

Priority:

P1

Complexity:

M

States:

- Pending
- Processing
- Completed
- Failed

Purpose:

Support long-running analysis jobs and future asynchronous processing.

Definition of Done:

Analysis status updates correctly throughout the pipeline.

---

## AI-015

### Title

Handle Inference Failures Gracefully

Priority:

P1

Complexity:

M

Handle:

- Model loading failures
- Inference timeout
- Corrupted model files
- Fact-check API failures
- Network failures
- Unexpected exceptions

Requirements:

- Log failures
- Return meaningful API responses
- Prevent application crashes

Definition of Done:

Pipeline failures are handled safely and users receive informative error messages.

---

## AI-016

### Title

Optimize AI Pipeline Performance

Priority:

P2

Complexity:

M

Optimize by:

- Avoiding duplicate analyses
- Reusing previously computed results
- Loading the fine-tuned model only once
- Minimizing unnecessary database queries
- Preparing the architecture for future caching

Definition of Done:

Pipeline performance is optimized without affecting correctness.

---

## AI-017

### Title

Implement Model Management

Priority:

P1

Complexity:

M

Responsibilities:

- Store model metadata
- Track model version
- Configure the active model artifact/path outside business logic
- Validate model availability during startup
- Keep model loading behind a stable model adapter/inference interface
- Enable retraining or compatible model replacement without changing the Hybrid Credibility Engine or public API contracts

Definition of Done:

Model management is centralized and supports future model versioning.

---

## AI-018

### Title

Test Individual Pipeline Components

Priority:

P1

Complexity:

L

Test:

- Claim preprocessing
- Fine-tuned model inference
- Fact-check integration
- Narrative Activity Engine
- Similarity scoring
- Rule-based validation
- Hybrid scoring engine

Each component must pass independently.

Definition of Done:

All pipeline components have passing unit tests.

---

## AI-019

### Title

Test End-to-End Pipeline

Priority:

P0

Complexity:

L

Flow:

Submit claim

↓

Preprocess claim

↓

Run fine-tuned model inference

↓

Retrieve fact-check evidence

↓

Detect Narrative Activity

↓

Execute rule-based validation

↓

Calculate weighted credibility score

↓

Generate verdict

↓

Generate explainability data

↓

Persist analysis

↓

Retrieve analysis

Definition of Done:

The complete pipeline executes successfully from claim submission to analysis retrieval.

---

## AI-020

### Title

Verify Explainability Output

Priority:

P0

Complexity:

M

Ensure:

- Every verdict includes an explainability report
- Score breakdown is internally consistent
- Model confidence is displayed correctly
- Supporting evidence is shown when available
- Missing evidence is handled gracefully

Definition of Done:

Explainability output is complete, accurate, and understandable.

---

## AI-021

### Title

Performance Review

Priority:

P2

Complexity:

M

Measure:

- Average inference time
- Model loading time
- Database query count
- Fact-check API latency
- Overall pipeline execution time
- Memory usage

Optimize obvious bottlenecks where necessary.

Definition of Done:

Pipeline performance meets acceptable latency targets for the MVP.

---

## AI-022

### Title

Finalize Hybrid Credibility Engine

Priority:

P0

Complexity:

S

Checklist:

✓ Claim preprocessing operational

✓ Fine-tuned model inference working

✓ Fact-check integration working

✓ Narrative Activity Engine functioning

✓ Rule-based validation operational

✓ Hybrid scoring engine producing credibility scores

✓ Verdict generation complete

✓ Explainability report generated

✓ Analysis stored successfully

✓ Tests passing

Definition of Done:

The complete Hybrid Credibility Engine is production-ready.

---

# Milestone 5 Verification Checklist

Verify:

✓ Claim preprocessing complete

✓ Fine-tuned model training and evaluation completed

✓ Versioned model artifact available

✓ InfoTrust fine-tuned misinformation classification model integrated

✓ Model inference working correctly

✓ Fact-check integration operational

✓ Narrative Activity detects similar claims

✓ Semantic similarity scoring implemented

✓ Rule-based validation operational

✓ Hybrid Credibility Engine operational

✓ Credibility scores generated

✓ Verdict categories generated

✓ Explainability reports generated

✓ Analysis persisted successfully

✓ Analysis API operational

✓ Error handling verified

✓ Pipeline tests passing

---

# Milestone 5 Definition of Done

Milestone 5 is complete only if:

- The complete Hybrid Credibility Engine functions end-to-end.
- Every analyzed claim receives:
  - A credibility score
  - A verdict
  - A detailed explainability report
- The InfoTrust fine-tuned misinformation classification model performs inference successfully.
- The classification model remains replaceable without requiring changes to the Hybrid Credibility Engine or public API contracts.
- Narrative Activity contributes to the final credibility score.
- Fact-check evidence is incorporated whenever available.
- Rule-based validation contributes to the final credibility score.
- Pipeline failures are handled gracefully.
- Analysis results are stored successfully.
- Automated tests pass.
- Documentation has been updated.

Development may proceed to **Milestone 6 — Frontend & User Experience** only after the Hybrid Credibility Engine is stable, thoroughly tested, and produces reliable, explainable credibility assessments.

---

# End of Part 5
# Milestone 6 — Frontend & User Experience

## Goal

Build a modern, responsive, and accessible frontend for InfoTrust.

This milestone implements:

- Application layout
- Navigation
- Authentication pages
- Dashboard
- Claim submission
- Analysis results
- Explainability Panel
- Claim history
- User profile
- Feedback system
- Responsive design

The frontend integrates seamlessly with the backend APIs and the Hybrid Credibility Engine developed in previous milestones.

---

# Deliverables

- Responsive application
- Protected routes
- Dashboard
- Claim submission flow
- Analysis view
- Explainability Panel
- Claim history
- Profile management
- Loading and error states

---

# Dependencies

Requires:

- Milestones 1–5 completed
- Backend APIs operational
- Hybrid Credibility Engine functional

---

# Task List

---

## FE-001

### Title

Create Global Application Layout

Priority:

P0

Complexity:

M

Layout:

- Header
- Sidebar (desktop)
- Mobile navigation
- Main content area
- Footer

Definition of Done:

Consistent layout across all pages.

---

## FE-002

### Title

Create Design System

Priority:

P1

Complexity:

M

Define:

- Typography
- Color palette
- Spacing
- Border radius
- Shadows
- Button styles
- Form styles

Purpose:

Ensure a consistent and modern user interface.

---

## FE-003

### Title

Implement Global Routing

Priority:

P0

Complexity:

S

Routes:

- Home
- Login
- Register
- Dashboard
- Submit Claim
- Claim Details
- Claim History
- Profile
- Admin (protected)

---

## FE-004

### Title

Create Reusable UI Components

Priority:

P1

Complexity:

L

Components:

- Button
- Input
- Textarea
- Card
- Badge
- Modal
- Alert
- Loader
- Empty State

---

## FE-005

### Title

Build Landing Page

Priority:

P1

Complexity:

M

Sections:

- Hero
- Features
- How It Works
- Call-to-Action
- Footer

Purpose:

Introduce InfoTrust and explain how credibility analysis works.

---

## FE-006

### Title

Build User Dashboard

Priority:

P0

Complexity:

L

Display:

- Total claims analyzed
- Recent analyses
- Credibility score trends
- Quick actions
- Recent activity

Dashboard should provide an overview of the user's activity.

---

## FE-007

### Title

Build Submit Claim Page

Priority:

P0

Complexity:

M

Components:

- Claim textarea
- Character counter
- Input validation
- Submit button

After successful submission:

Navigate to the analysis results page.

---

## FE-008

### Title

Integrate Claim Submission API

Priority:

P0

Complexity:

M

Verify:

- Claim submission succeeds
- Validation errors displayed correctly
- Loading indicator shown
- Backend errors handled gracefully

Definition of Done:

Claims are successfully submitted through the backend API and appropriate feedback is shown to the user.

---
## FE-009

### Title

Build Analysis Results Page

Priority:

P0

Complexity:

L

Display:

- Submitted claim
- Final verdict
- Overall credibility score
- Confidence score
- Analysis timestamp
- Feedback controls

The page should present the complete analysis in a clear and user-friendly format.

---

## FE-010

### Title

Build Explainability Panel

Priority:

P0

Complexity:

L

Display the outputs generated by the Hybrid Credibility Engine.

Sections:

- Final verdict
- Credibility score breakdown
- Fine-tuned model prediction
- Fact-check findings
- Narrative Activity summary
- Rule-based observations
- Confidence indicators

Purpose:

Help users understand how the final credibility score and verdict were produced.

---

## FE-011

### Title

Visualize Credibility Score

Priority:

P1

Complexity:

M

Display:

- Circular score meter
- Progress bar
- Verdict badge
- Color-coded credibility level

Provide an intuitive visualization of the overall credibility score.

---

## FE-012

### Title

Visualize Narrative Activity

Priority:

P1

Complexity:

M

Display:

- Similar claim count
- Highest similarity score
- First occurrence
- Latest occurrence

Present narrative activity in an easy-to-understand visual format instead of raw numerical values.

---

## FE-013

### Title

Build Claim History Page

Priority:

P0

Complexity:

L

Features:

- Pagination
- Search
- Sorting
- Status badges
- View analysis details

Users should be able to browse all previously analyzed claims.

---

## FE-014

### Title

Build User Profile Page

Priority:

P1

Complexity:

M

Display:

- Full name
- Email address
- Account information

Allow:

- Update profile information
- Change password (future-ready placeholder if not implemented)

---

## FE-015

### Title

Implement Helpful / Not Helpful Feedback

Priority:

P1

Complexity:

M

Allow users to provide feedback on an analysis.

Requirements:

- Helpful
- Not Helpful
- Prevent duplicate feedback submissions

---

## FE-016

### Title

Implement Global Loading States

Priority:

P1

Complexity:

S

Examples:

- Page loading
- Form submission
- Claim analysis processing
- API requests

Provide consistent loading indicators throughout the application.

---

## FE-017

### Title

Implement Empty States

Priority:

P1

Complexity:

S

Examples:

- No claims submitted
- No search results
- No completed analyses

Display informative guidance to help users understand what to do next.

---
## FE-018

### Title

Implement Error States

Priority:

P1

Complexity:

S

Handle:

- Network failures
- API errors
- Unauthorized access
- Analysis failures

Provide clear, user-friendly error messages along with recovery actions where appropriate.

---

## FE-019

### Title

Implement Toast Notifications

Priority:

P2

Complexity:

S

Examples:

- Login successful
- Registration successful
- Claim submitted
- Analysis completed
- Profile updated
- Error occurred

Notifications should provide immediate feedback without interrupting the user's workflow.

---

## FE-020

### Title

Ensure Responsive Design

Priority:

P0

Complexity:

L

Support:

- Mobile
- Tablet
- Desktop

Verify layouts across common screen sizes and breakpoints.

---

## FE-021

### Title

Implement Accessibility Improvements

Priority:

P1

Complexity:

M

Verify:

- Keyboard navigation
- Focus indicators
- ARIA labels where appropriate
- Sufficient color contrast
- Accessible form validation messages

Ensure the application is usable by as many users as possible.

---

## FE-022

### Title

Optimize Frontend Performance

Priority:

P2

Complexity:

M

Techniques:

- Lazy loading routes
- Code splitting
- Memoization where beneficial
- Reduce unnecessary re-renders
- Optimize API requests

---

## FE-023

### Title

Cross-Browser Testing

Priority:

P2

Complexity:

S

Verify compatibility with:

- Google Chrome
- Mozilla Firefox
- Microsoft Edge

Resolve browser-specific UI or functionality issues.

---

## FE-024

### Title

Finalize Frontend

Priority:

P0

Complexity:

S

Checklist:

✓ All pages complete

✓ Responsive layouts verified

✓ Accessible UI implemented

✓ Backend integration verified

✓ Hybrid Credibility Engine results displayed correctly

✓ Explainability Panel operational

✓ Loading states implemented

✓ Error handling complete

✓ Frontend tests passing

---

# Milestone 6 Verification Checklist

Verify:

✓ Global application layout implemented

✓ Dashboard operational

✓ Claim submission integrated

✓ Analysis results page displays Hybrid Credibility Engine outputs

✓ Explainability Panel functional

✓ Credibility score visualization complete

✓ Narrative Activity visualization complete

✓ Claim history operational

✓ User profile management working

✓ Feedback system implemented

✓ Responsive design verified

✓ Accessibility improvements completed

✓ Performance optimizations applied

✓ Frontend integrates successfully with backend APIs

---

# Milestone 6 Definition of Done

Milestone 6 is complete only if:

- All user-facing pages are fully implemented.
- Frontend integrates seamlessly with backend APIs.
- Results from the Hybrid Credibility Engine are displayed correctly.
- The Explainability Panel clearly communicates how the final credibility score and verdict were generated using:
  - Fine-tuned misinformation model prediction
  - Fact-check evidence
  - Narrative Activity analysis
  - Rule-based validation
- Responsive behavior is verified across supported devices.
- Accessibility standards are reasonably satisfied.
- Loading and error states are implemented consistently.
- Frontend performance is optimized.
- Documentation is updated.

Development may proceed to **Milestone 7 — Deployment, Monitoring & Finalization** only after the frontend provides a complete, polished, and production-ready user experience.

---

# End of Part 6
# Milestone 7 — Admin Dashboard, Testing & Deployment

## Goal

Complete the administrative functionality and prepare InfoTrust for production deployment.

This milestone implements:

- Admin Dashboard
- User Management
- Claim Moderation
- Platform Analytics
- Comprehensive testing
- Performance optimization
- Security review
- Docker verification
- CI/CD
- Production deployment

At the end of this milestone, InfoTrust should be production-ready and demonstration-ready.

---

# Deliverables

- Admin Dashboard
- User management
- Claim moderation
- Platform analytics
- Complete test suite
- Security review
- Production deployment
- Documentation finalized

---

# Dependencies

Requires:

- Milestones 1–6 completed

---

# Task List

---

## ADMIN-001

### Title

Create Admin Dashboard Layout

Priority:

P0

Complexity:

M

Sections:

- Overview cards
- Charts
- Recent activity
- Quick actions
- Navigation

Definition of Done:

Admin dashboard layout complete.

---

## ADMIN-002

### Title

Display Platform Statistics

Priority:

P0

Complexity:

M

Metrics:

- Total users
- Total claims
- Total analyses
- Average credibility score
- Verdict distribution

---

## ADMIN-003

### Title

Create User Management Page

Priority:

P0

Complexity:

L

Features:

- List users
- Search
- Filter
- View details

---

## ADMIN-004

### Title

Implement Disable / Enable User

Priority:

P0

Complexity:

M

Rules:

- Admin only
- Prevent self-disable
- Audit log required

---

## ADMIN-005

### Title

Create Claim Moderation Page

Priority:

P0

Complexity:

L

Display:

- Submitted claims
- Analysis status
- User
- Date

Actions:

- View
- Delete inappropriate claims

---

## ADMIN-006

### Title

Implement Administrative Analytics

Priority:

P1

Complexity:

L

Charts:

- Claims over time
- Verdict distribution
- Narrative Activity frequency
- User registrations
- Credibility score distribution
- Hybrid Engine component usage

---

## ADMIN-007

### Title

Create Audit Log Viewer

Priority:

P1

Complexity:

M

Display:

- Admin actions
- Timestamps
- Actor
- Target

Search and filter supported.

---

## ADMIN-008

### Title

Protect Admin Routes

Priority:

P0

Complexity:

S

Verify:

Only ADMIN role can access administrative pages and APIs.

---

## ADMIN-009

### Title

Create Admin API Tests

Priority:

P1

Complexity:

L

Verify:

- Authorization
- User management
- Claim moderation
- Analytics endpoints

---

## TEST-001

### Title

Write Unit Tests

Priority:

P0

Complexity:

L

Cover:

- Models
- Services
- Validators
- Utility functions
- Hybrid Credibility Engine components

---

## TEST-002

### Title

Write Integration Tests

Priority:

P0

Complexity:

L

Verify:

- Authentication
- Claim flow
- Hybrid Credibility Engine
- Feedback
- Admin features

---

## TEST-003

### Title

Perform End-to-End Testing

Priority:

P0

Complexity:

L

Scenarios:

- Register
- Login
- Submit claim
- Analyze claim
- View explainability report
- Provide feedback
- Admin moderation

---

## TEST-004

### Title

Security Testing

Priority:

P1

Complexity:

M

Verify:

- Authentication
- Authorization
- Input validation
- JWT handling
- SQL injection protection
- XSS protection

---

## TEST-005

### Title

Performance Testing

Priority:

P1

Complexity:

M

Measure:

- API response time
- Hybrid Credibility Engine latency
- Database query performance
- Page load times

---

## TEST-006

### Title

Accessibility Testing

Priority:

P2

Complexity:

S

Verify:

- Keyboard navigation
- Focus management
- Screen reader compatibility
- Color contrast

---

## TEST-007

### Title

Manual Testing Checklist

Priority:

P0

Complexity:

M

Confirm every user story works as expected before deployment.

---

## DEPLOY-001

### Title

Verify Docker Environment

Priority:

P0

Complexity:

M

Confirm:

- Backend container
- Frontend container
- Database container

All start successfully.

---

## DEPLOY-002

### Title

Configure Production Environment Variables

Priority:

P0

Complexity:

S

Verify:

- Secrets
- API keys
- Database URL
- Allowed hosts

No sensitive values committed to Git.

---

## DEPLOY-003

### Title

Configure CI/CD Pipeline

Priority:

P1

Complexity:

M

Pipeline:

- Install dependencies
- Lint
- Test
- Build
- Deploy

---

## DEPLOY-004

### Title

Deploy Frontend

Priority:

P0

Complexity:

M

Recommended:

- Vercel

Verify:

- HTTPS
- Environment variables
- API connectivity

---

## DEPLOY-005

### Title

Deploy Backend

Priority:

P0

Complexity:

M

Recommended:

- Render (or equivalent Docker-compatible platform)

Verify:

- HTTPS
- Database connectivity
- API availability

---

## DEPLOY-006

### Title

Deploy PostgreSQL Database

Priority:

P0

Complexity:

S

Recommended:

- Neon PostgreSQL

Verify:

- Secure connection
- Migrations applied

---

## DEPLOY-007

### Title

Run Production Smoke Tests

Priority:

P0

Complexity:

M

Verify:

- Registration
- Login
- Claim submission
- Hybrid claim analysis
- Dashboard
- Admin panel

---

## DEPLOY-008

### Title

Finalize Documentation

Priority:

P1

Complexity:

M

Update:

- README
- API documentation
- Deployment guide
- Architecture notes
- Known limitations

---

## DEPLOY-009

### Title

Tag First Stable Release

Priority:

P2

Complexity:

S

Create:

```
v1.0.0
```

Document release notes.

---

## DEPLOY-010

### Title

Project Sign-off

Priority:

P0

Complexity:

S

Checklist:

✓ All milestones complete

✓ Tests passing

✓ Production deployed

✓ Documentation complete

✓ Demo ready

---

# Milestone 7 Verification Checklist

Verify:

✓ Admin dashboard operational

✓ User management functional

✓ Claim moderation implemented

✓ Analytics displayed

✓ Audit logs accessible

✓ Unit tests passing

✓ Integration tests passing

✓ End-to-end scenarios verified

✓ Security review completed

✓ Performance acceptable

✓ Accessibility checked

✓ Docker verified

✓ CI/CD operational

✓ Production deployment successful

✓ Documentation complete

---

# Milestone 7 Definition of Done

Milestone 7 is complete only if:

- Administrative functionality is fully operational.
- The Hybrid Credibility Engine is functioning correctly in the deployed environment.
- All planned testing has been completed successfully.
- Security and performance reviews are satisfactory.
- The application is deployed to production.
- Documentation is complete and up to date.
- The project is ready for demonstration, evaluation, and future maintenance.

Completion of this milestone marks the completion of **InfoTrust v1.0.0**.

---

# End of Part 7
# Engineering Rules

These rules apply throughout the entire development lifecycle.

---

## Rule 1 — One Task at a Time

Never implement multiple unrelated tasks simultaneously.

Complete the current task before starting the next.

---

## Rule 2 — Respect Dependencies

Do not skip milestones.

Example:

Authentication must exist before protected APIs.

Claims must exist before ML analysis.

ML analysis must exist before dashboards.

---

## Rule 3 — Keep Commits Small

Each completed task should ideally correspond to one Git commit.

Example:

```
feat(auth): implement JWT login API

feat(claims): create claim submission endpoint

feat(ai): integrate misinformation classifier

fix(api): handle timeout exceptions
```

---

## Rule 4 — Test Before Moving On

Every completed task must be verified.

Never postpone testing until the end.

---

## Rule 5 — Documentation is Part of Development

Whenever a major feature is completed, update:

- README
- API documentation
- Architecture (if changed)
- Task status

---

## Rule 6 — Refactor Continuously

Improve:

- Naming
- Structure
- Duplication
- Readability

Avoid large refactoring sessions.

---

## Rule 7 — Never Break Existing Features

Before merging:

Verify previously completed functionality still works.

---

## Rule 8 — Business Logic Stays in Services

Views should:

- Validate requests
- Call services
- Return responses

Views must not contain business logic.

---

## Rule 9 — Selectors Are Read Only

Selectors:

✔ Read

✔ Query

✔ Aggregate

Selectors never modify data.

---

## Rule 10 — Configuration Over Hardcoding

Avoid hardcoded values.

Examples:

- API URLs
- ML model path
- Confidence thresholds
- Similarity thresholds
- Environment settings
- Timeouts

Use configuration files or environment variables.

---

## Rule 11 — Explainability First

Every credibility prediction must include structured explanations.

Users should understand why the model produced a verdict.

---

## Rule 12 — Keep AI Components Modular

Each AI component should remain independent.

Examples:

- Text preprocessing
- Misinformation classifier
- Fact-check retrieval
- Narrative Activity Engine
- Similarity Engine
- Rule-based validation
- Explainability generator

This allows future model upgrades without affecting the rest of the system.

---

# AI Collaboration Rules

These rules apply when using Antigravity CLI, Gemini CLI, or any coding assistant.

---

## AI-Rule 1

Never generate the entire project at once.

---

## AI-Rule 2

Only work on the current milestone.

---

## AI-Rule 3

Complete one task before requesting the next.

---

## AI-Rule 4

Always explain technical decisions before implementation.

---

## AI-Rule 5

Follow:

- PROJECT_RULES.md
- PRD.md
- ARCHITECTURE.md
- TASK.md

If generated code conflicts with these documents, the documentation takes precedence.

---

## AI-Rule 6

Prefer modifying existing code over rewriting large sections unless refactoring is explicitly planned.

---

## AI-Rule 7

After each completed task, provide:

- Summary of work completed
- Files created
- Files modified
- Tests performed
- Remaining work
- Technical debt (if any)

---

## AI-Rule 8

If requirements are ambiguous:

Stop.

Ask questions.

Never guess.

---

## AI-Rule 9

Never replace, retrain, or change the selected InfoTrust fine-tuned misinformation classifier without approval.

The project uses an InfoTrust-specific fine-tuned transformer-based misinformation classifier rather than a fixed third-party pre-trained misinformation detector.

The model layer must remain replaceable. Future model upgrades, retraining, or replacement must preserve the standardized inference interface so that the Hybrid Credibility Engine and other application components do not require changes.

---

## AI-Rule 10

Do not hardcode model outputs.

All predictions must come directly from the ML inference pipeline.

---

# Progress Tracking

Track milestone completion.

| Milestone | Status |
|-----------|--------|
| Project Initialization | ⬜ |
| Authentication | ⬜ |
| Database & Models | ⬜ |
| Backend APIs | ⬜ |
| Hybrid Credibility Engine | ⬜ |
| Frontend | ⬜ |
| Admin & Deployment | ⬜ |

Update this table as work progresses.

---

# Feature Completion Checklist

Before marking any feature complete, verify:

- Requirements implemented
- Validation complete
- Error handling implemented
- Tests passing
- Documentation updated
- Code reviewed
- No known regressions

---

# Pull Request Checklist

Even as a solo developer, review your own work.

Checklist:

- Clear purpose
- Small scope
- No debugging code
- No commented-out code
- No secrets committed
- Naming consistent
- Linting passes
- Tests pass
- Documentation updated

---

# Code Quality Checklist

Before every commit:

✓ Code formatted

✓ Linting passes

✓ Type checking passes (frontend)

✓ No unused imports

✓ No duplicated logic

✓ No TODOs without issue reference

✓ No hardcoded secrets

---

# Definition of Done (DoD)

A task is complete only if:

- Implementation finished
- Works as expected
- Edge cases considered
- Validation added
- Error handling implemented
- Tests written (where applicable)
- Documentation updated
- Code reviewed
- No critical warnings remain

---

# Final Project Completion Checklist

InfoTrust is considered complete only if:

## Functional

✓ User registration

✓ User login

✓ JWT authentication

✓ Claim submission

✓ Hybrid Credibility Engine

✓ InfoTrust fine-tuned misinformation classifier integrated

✓ Fact-check integration

✓ Narrative Activity detection

✓ Semantic similarity analysis

✓ Explainability Panel

✓ Claim history

✓ User dashboard

✓ Admin dashboard

✓ Feedback system

---

## Technical

✓ Clean Architecture followed

✓ REST API implemented

✓ PostgreSQL database

✓ Docker support

✓ Environment variables

✓ Logging

✓ Audit logs

✓ Validation

✓ Security review

✓ Automated tests

✓ CI/CD

✓ Transformer-based model inference integrated

---

## Quality

✓ Responsive UI

✓ Accessibility considered

✓ Error handling complete

✓ Performance reviewed

✓ Documentation complete

---

## Academic

✓ Problem statement addressed

✓ Innovation demonstrated

✓ Machine Learning integration justified

✓ Explainability included

✓ Real-world applicability shown

✓ Architecture documented

✓ Database documented

✓ Deployment completed

---

# Project Completion Summary

Upon completion, InfoTrust should demonstrate:

- Professional software architecture
- Modern full-stack web development
- Transformer-based misinformation detection
- Explainable AI principles
- Semantic similarity analysis
- Fact-check integration
- Secure authentication
- Clean RESTful APIs
- Scalable database design
- Responsive frontend
- Administrative capabilities
- Production-ready deployment practices

The project should be suitable for:

- Final-year B.Tech evaluation
- Technical portfolio
- Resume showcase
- GitHub portfolio
- Internship interviews
- Further research and future enhancements

---

# Version History

| Version | Date | Description |
|---------|------|-------------|
| 2.0.0 | Planning Update | Updated roadmap to use a transformer model, Hybrid Credibility Engine, semantic similarity, and explainable ML architecture. |
| 2.1.0 | July 2026 | Replaced the fixed pre-trained misinformation detector with an InfoTrust-specific fine-tuned classifier while preserving the Hybrid Credibility Engine and model-replaceable architecture. |
| 2.2.0 | September 2026 | Recorded completion of final model fine-tuning/evaluation and the frozen `final_model_corrected` artifact; application integration remains pending. |

Update this table whenever major planning changes are made.

---

# End of TASK.md

---

# ML Execution Status

The final ML training and evaluation phase is complete.

Completed:
* Final selection of `microsoft/deberta-v3-base`.
* Final selection of cleaned WELFake + FEVER for production training.
* Leakage-safe training/validation/test preparation.
* Final production fine-tuning.
* Validation-based checkpoint selection.
* Held-out WELFake evaluation.
* Held-out FEVER evaluation.
* Combined evaluation.
* External LIAR evaluation.
* Frozen/versioned model artifact and tokenizer.
* Final experiment record and recovery manifest.

Current ML artifact:
* `final_model_corrected`
* Best checkpoint: `checkpoint-12369`
* Best validation Macro F1: `0.930224`

Still pending:
* Integrate the frozen model through the Model Adapter and AI Analysis Service.
* Complete the remaining application-level AI pipeline tasks.
* Do not retrain the frozen model unless intentionally creating a new experiment/version.

# Final ML / Dataset Decision — July 2026

The following machine-learning decisions are now the approved source of truth for InfoTrust Version 1.

## Selected Base Model

The selected transformer base model is:

```text
microsoft/deberta-v3-base
```

The final InfoTrust production classifier has been fine-tuned from this base model. The final training and evaluation workflow is complete, and the frozen artifact is `final_model_corrected`.

## Production Training Data

The final production training workflow will use cleaned data from:

* **WELFake**
* **FEVER**

The two datasets are aligned to InfoTrust's binary classification target.

### WELFake Label Mapping

```text
FAKE -> MISINFORMATION
REAL -> CREDIBLE
```

### FEVER Label Mapping

```text
REFUTES -> MISINFORMATION
SUPPORTS -> CREDIBLE
```

Records that do not fit the approved binary mapping must not be silently forced into a class.

## Sampling and Split Strategy

The final production dataset preparation must:

* Clean and normalize the approved WELFake and FEVER records.
* Prevent train/validation/test leakage.
* Apply balanced **domain × class** sampling so that one dataset or class does not dominate the training distribution.
* Create reproducible train, validation, and test partitions.
* Use the validation partition for checkpoint/model selection.
* Keep the held-out test partition isolated from model-selection decisions.

## External Evaluation Dataset

**LIAR is not a production training dataset.**

LIAR must remain untouched by production training and is reserved only for external evaluation of cross-dataset generalization.

LIAR data must not be merged into the WELFake + FEVER training pool.

## Preliminary Experiments A–D

Experiments A–D are **preliminary feasibility and model-selection experiments**. They are evidence used to choose the final ML direction; they are **not** the final production training run and their checkpoints are not the final production model.

Recorded preliminary results:

| Experiment | Purpose | Result |
| --- | --- | --- |
| A | WELFake-only feasibility | ~93.93% Macro F1 on WELFake |
| B | FEVER-only feasibility | ~83.10% Macro F1 on FEVER |
| A -> B | Cross-dataset generalization check | ~42.00% Macro F1 |
| B -> A | Cross-dataset generalization check | ~49.36% Macro F1 |
| C | Mixed WELFake + FEVER feasibility | ~94.22% Macro F1 on WELFake and ~81.91% Macro F1 on FEVER |
| D | Unseen LIAR external evaluation of the preliminary mixed-model direction | ~47.54% Macro F1 and ~47.92% accuracy |

These results demonstrate strong in-domain feasibility but materially weaker cross-dataset generalization. They therefore justify the final combined-data strategy and the decision to keep LIAR as a separate external generalization test.

## Final Production Model — Completed ML Record

The final InfoTrust misinformation classification model has completed the approved training and evaluation workflow.

### Frozen Model

| Item | Final Value |
|---|---|
| Base model | `microsoft/deberta-v3-base` |
| Frozen model artifact | `final_model_corrected` |
| Best checkpoint | `checkpoint-12369` |
| Model precision | FP32 |
| Training GPU | Tesla T4 |
| Epochs | 3 |
| Learning rate | `2e-5` |
| Weight decay | `0.01` |
| Per-device training batch | 8 |
| Gradient accumulation | 4 |
| Effective batch size | 32 |
| Evaluation batch size | 8 |
| Maximum sequence length | 128 |
| Primary validation metric | Macro F1 |
| Best validation Macro F1 | 0.930224 |

### Final Evaluation

| Dataset | Samples | Accuracy | Macro Precision | Macro Recall | Macro F1 |
|---|---:|---:|---:|---:|---:|
| WELFake | 6,271 | 99.2186% | 99.1989% | 99.2218% | **99.2102%** |
| FEVER | 10,221 | 89.8151% | 88.3021% | 85.6822% | **86.8523%** |
| Combined | 16,492 | 93.3907% | 93.3980% | 92.5392% | **92.9310%** |
| LIAR (external) | 1,267 | 53.7490% | — | — | **46.6208%** |

The final experiment record identifies `final_model_corrected` as the frozen model and the corrected WELFake/FEVER test packages as the authoritative final evaluation data.

An earlier WELFake evaluation was discarded after leakage and label-conflict checks found train/test and validation/test overlap. The invalid evaluation must not be used as a final result.

### Final ML Status

- Final fine-tuning: **COMPLETED**
- Validation-based checkpoint selection: **COMPLETED**
- Held-out WELFake evaluation: **COMPLETED**
- Held-out FEVER evaluation: **COMPLETED**
- Combined evaluation: **COMPLETED**
- External LIAR evaluation: **COMPLETED**
- Model/tokenizer artifact saved: **COMPLETED**
- Experiment status: **FROZEN / FINAL**
- Application integration through the Model Adapter / AI Analysis Service: **PENDING**


## Current Production-Model Status

As of this documentation update:

* Base-model selection is complete.
* Dataset selection and label mapping are complete.
* Preliminary Experiments A–D are complete.
* The final production training recipe is defined.
* The **final production model has completed training and evaluation**. Application integration remains a separate implementation task.
* No preliminary Experiment A–D checkpoint should be described as the final production model.
* A production model artifact/version must be recorded only after the final WELFake + FEVER training, validation-based checkpoint selection, held-out testing, and external LIAR evaluation are completed.

The final trained model will continue to remain behind the existing **AI Analysis Service / Model Adapter** boundary. These ML decisions do not change the Hybrid Credibility Engine, its existing signal responsibilities, or unrelated InfoTrust architecture.
