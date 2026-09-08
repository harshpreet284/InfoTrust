# API_SPEC.md

> Version: 1.2
> Project: InfoTrust
> API Style: REST
> Data Format: JSON
> Authentication: JWT (Access + Refresh Tokens)
> Base URL (Development): http://localhost:8000/api/v1
> Base URL (Production): https://<your-domain>/api/v1

---

# 1. API Philosophy

The InfoTrust API is designed according to RESTful principles and follows a contract-first approach.

Goals:

- Predictable and consistent endpoints
- Stateless communication
- Secure authentication
- Standardized responses
- Clear error handling
- Versioned APIs
- Easy frontend integration
- Future scalability
- AI model independence through a dedicated inference layer

The API serves four primary clients:

- Web Frontend (React)
- Admin Dashboard
- Internal AI Inference Service
- Future third-party integrations

The AI analysis endpoints are intentionally model-agnostic. InfoTrust v1 uses an InfoTrust-specific fine-tuned misinformation classification model behind the dedicated AI Analysis Service. The public API contract remains unchanged if the model is retrained or replaced with another compatible classifier.

---

# 2. API Design Principles

The API follows these principles throughout the project.

## 2.1 Resource-Oriented URLs

Good:

GET /claims

GET /claims/{id}

POST /claims

Bad:

GET /getClaims

POST /createClaim

---

## 2.2 Use HTTP Methods Correctly

GET

Retrieve resources.

POST

Create new resources.

PUT

Replace an entire resource.

PATCH

Update part of a resource.

DELETE

Remove a resource (soft delete where applicable).

---

## 2.3 Stateless Requests

Every request must contain all information required for processing.

The server does not store session state.

Authentication is handled using JWT access tokens.

---

## 2.4 JSON Everywhere

All request and response bodies use JSON.

Content-Type:

application/json

Accept:

application/json

---

## 2.5 Consistent Naming

Use:

snake_case for JSON fields.

Examples:

created_at

credibility_score

analysis_status

Avoid mixed naming styles.

---

## 2.6 UUID Identifiers

Public resources use UUIDs instead of sequential IDs.

Example:

550e8400-e29b-41d4-a716-446655440000

Benefits:

- Harder to enumerate
- Better security
- Easier distributed systems
- Professional API design

---

# 3. API Versioning

Current version:

v1

Base path:

/api/v1/

Example:

GET /api/v1/claims

Future versions:

/api/v2/

Older versions remain supported during migration.

---

# 4. Authentication

Authentication method:

JWT

Tokens:

- Access Token
- Refresh Token

Access Token:

Used for authenticated API requests.

Refresh Token:

Used only to obtain a new access token.

Authorization header:

Authorization: Bearer <access_token>

Guest endpoints:

- Register
- Login
- Refresh Token
- Health Check

Authenticated endpoints:

Require a valid JWT access token.

---

# 5. User Roles

Three roles exist.

## Guest

Permissions:

- Register
- Login
- View landing page

Cannot:

- Submit claims
- View history
- Access dashboard

---

## User

Permissions:

- Submit claims
- View own history
- View analysis
- Provide feedback
- Update profile

Cannot:

- Manage users
- Delete other users' claims
- Access admin dashboard

---

## Admin

Permissions:

Everything a User can do, plus:

- View platform analytics
- Manage users
- Disable accounts
- Delete inappropriate claims
- View audit logs

---

# 6. Request Headers

Standard headers:

Content-Type: application/json

Accept: application/json

Authorization: Bearer <access_token>

Optional:

X-Request-ID

Purpose:

Request tracing for debugging.

---

# 7. Standard Request Rules

Requests must satisfy:

- UTF-8 encoding
- Valid JSON
- Required fields present
- Correct data types
- No unknown fields (where validation is strict)
- Maximum request size limits enforced

Invalid requests return HTTP 400 or 422 depending on the error.

---

# 8. Standard Success Response

Every successful response follows a consistent structure.

Example:

```json
{
    "success": true,
    "message": "Claim submitted successfully.",
    "data": {
        ...
    }
}
```

Fields:

success

Boolean indicating request status.

message

Human-readable summary.

data

Requested resource or operation result.

---

# 9. Standard Error Response

Every failed request follows a common format.

Example:

```json
{
    "success": false,
    "message": "Validation failed.",
    "errors": {
        "claim_text": [
            "This field is required."
        ]
    }
}
```

Fields:

success

Always false.

message

High-level description.

errors

Field-level validation details or general error information.

---

# 10. HTTP Status Codes

The API uses standard HTTP status codes.

200 OK

Request completed successfully.

201 Created

Resource created successfully.

202 Accepted

Analysis request accepted for processing.

204 No Content

Operation completed with no response body.

400 Bad Request

Malformed request.

401 Unauthorized

Authentication required or invalid token.

403 Forbidden

Authenticated but insufficient permissions.

404 Not Found

Requested resource does not exist.

409 Conflict

Conflict with current resource state.

422 Unprocessable Entity

Validation failed.

429 Too Many Requests

Rate limit exceeded.

500 Internal Server Error

Unexpected server error.

503 Service Unavailable

Temporary service outage or unavailable external dependency (e.g., fact-check provider).

---

# 11. Pagination Standard

Endpoints returning collections support pagination.

Query Parameters:

?page=1

&page_size=10

Standard response:

```json
{
    "count": 125,
    "next": "...",
    "previous": "...",
    "results": []
}
```

Default page size:

10

Maximum page size:

100

---

# 12. Filtering & Sorting

Filtering uses query parameters.

Examples:

GET /claims?status=completed

GET /claims?verdict=credible

Sorting:

GET /claims?ordering=-created_at

Prefix:

- indicates descending order.

---

# 13. Search

Search parameter:

search

Example:

GET /claims?search=vaccine

Search behavior:

- Case-insensitive
- Partial matches
- Trim whitespace

---

# 14. Date & Time Format

All timestamps use:

ISO 8601

Example:

2026-06-30T14:25:18Z

Timezone:

UTC

The frontend is responsible for displaying dates in the user's local timezone.

---

# 15. Idempotency

GET

Safe and idempotent.

PUT

Idempotent.

PATCH

Not guaranteed.

POST

Not idempotent.

DELETE

Idempotent when deleting an already deleted resource returns the appropriate response.

---

# 16. Security Standards

The API must:

- Require HTTPS in production.
- Validate all inputs.
- Sanitize user-provided data where appropriate.
- Never expose internal exceptions.
- Never expose stack traces.
- Never return sensitive fields (e.g., password hashes).
- Use environment variables for secrets.
- Store the AI model identifier, version, and artifact path in configuration rather than hardcoding them.
- Apply rate limiting to sensitive endpoints.

---

# 17. API Documentation Standards

Every endpoint documented later in this file must include:

- Purpose
- Endpoint
- HTTP Method
- Authentication Required
- User Roles
- Request Body
- Path Parameters
- Query Parameters
- Success Response
- Error Responses
- Validation Rules
- Business Rules
- Example Request
- Example Response

This ensures every API contract is complete, implementation-ready, and independent of the underlying AI model implementation.

---

# End of Part 1
# Authentication APIs

Base Path:

/api/v1/auth

Authentication:

Not required unless explicitly stated.

---

# AUTH-001 — Register User

## Purpose

Create a new user account.

---

## Endpoint

POST

```
/api/v1/auth/register
```

---

## Authentication

Not Required

---

## Allowed Roles

- Guest

---

## Request Body

```json
{
  "full_name": "Harshpreet Singh",
  "email": "harsh@example.com",
  "password": "StrongPassword123!",
  "confirm_password": "StrongPassword123!"
}
```

---

## Validation Rules

### full_name

- Required
- 2–100 characters
- Leading/trailing whitespace trimmed

### email

- Required
- Valid email format
- Converted to lowercase
- Must be unique

### password

- Required
- Minimum 8 characters
- Maximum 128 characters
- At least:
  - One uppercase letter
  - One lowercase letter
  - One number
  - One special character

### confirm_password

- Required
- Must exactly match password

---

## Business Rules

- Every newly registered account is assigned the **USER** role.
- Passwords are hashed using Django's password hashing framework.
- Duplicate email addresses are rejected.
- Email addresses are stored in lowercase.
- Users are active by default.

---

## Success Response

HTTP **201 Created**

```json
{
  "success": true,
  "message": "Registration successful.",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "full_name": "Harshpreet Singh",
    "email": "harsh@example.com",
    "role": "USER",
    "created_at": "2026-06-30T12:00:00Z"
  }
}
```

---

## Possible Errors

400

Malformed request

409

Email already exists

422

Validation failed

---

# AUTH-002 — Login

## Purpose

Authenticate a user and issue JWT tokens.

---

## Endpoint

POST

```
/api/v1/auth/login
```

---

## Authentication

Not Required

---

## Allowed Roles

- Guest

---

## Request Body

```json
{
  "email": "harsh@example.com",
  "password": "StrongPassword123!"
}
```

---

## Validation Rules

- Email required
- Password required

---

## Business Rules

- Email comparison is case-insensitive.
- Disabled accounts cannot log in.
- Successful login returns both Access and Refresh tokens.

---

## Success Response

HTTP **200 OK**

```json
{
  "success": true,
  "message": "Login successful.",
  "data": {
    "access_token": "<jwt_access_token>",
    "refresh_token": "<jwt_refresh_token>",
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "full_name": "Harshpreet Singh",
      "email": "harsh@example.com",
      "role": "USER"
    }
  }
}
```

---

## Possible Errors

401

Invalid credentials

403

Account disabled

422

Validation failed

---

# AUTH-003 — Refresh Access Token

## Purpose

Generate a new access token using a valid refresh token.

---

## Endpoint

POST

```
/api/v1/auth/refresh
```

---

## Authentication

Refresh Token Required

---

## Request Body

```json
{
  "refresh_token": "<jwt_refresh_token>"
}
```

---

## Business Rules

- Refresh token must be valid.
- Blacklisted tokens are rejected.
- Only a new access token is returned.

---

## Success Response

HTTP **200 OK**

```json
{
  "success": true,
  "message": "Token refreshed successfully.",
  "data": {
    "access_token": "<new_access_token>"
  }
}
```

---

## Possible Errors

401

Invalid refresh token

403

Token blacklisted

---

# AUTH-004 — Logout

## Purpose

Invalidate the current refresh token.

---

## Endpoint

POST

```
/api/v1/auth/logout
```

---

## Authentication

Required

---

## Allowed Roles

- USER
- ADMIN

---

## Request Body

```json
{
  "refresh_token": "<jwt_refresh_token>"
}
```

---

## Business Rules

- Refresh token is added to the blacklist.
- Existing access tokens remain valid until expiration.
- Users must authenticate again after access token expiry.

---

## Success Response

HTTP **200 OK**

```json
{
  "success": true,
  "message": "Logged out successfully.",
  "data": {}
}
```

---

## Possible Errors

401

Invalid token

403

Token already blacklisted

---

# AUTH-005 — Get Current User

## Purpose

Retrieve the authenticated user's profile.

---

## Endpoint

GET

```
/api/v1/auth/me
```

---

## Authentication

Required

---

## Allowed Roles

- USER
- ADMIN

---

## Request Headers

Authorization:

Bearer <access_token>

---

## Success Response

HTTP **200 OK**

```json
{
  "success": true,
  "message": "User profile retrieved successfully.",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "full_name": "Harshpreet Singh",
    "email": "harsh@example.com",
    "role": "USER",
    "created_at": "2026-06-30T12:00:00Z",
    "is_active": true
  }
}
```

---

## Possible Errors

401

Missing or invalid access token

403

Account disabled

---

# Authentication Flow

```text
Guest
   │
   ▼
Register
   │
   ▼
Login
   │
   ▼
Receive Access Token + Refresh Token
   │
   ▼
Access Protected APIs
   │
   ▼
Access Token Expires
   │
   ▼
Refresh Token API
   │
   ▼
Receive New Access Token
   │
   ▼
Logout
   │
   ▼
Refresh Token Blacklisted
```

---

# Authentication API Summary

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| /auth/register | POST | No | Register a new user |
| /auth/login | POST | No | Authenticate and receive JWT tokens |
| /auth/refresh | POST | Refresh Token | Issue a new access token |
| /auth/logout | POST | Yes | Logout and blacklist refresh token |
| /auth/me | GET | Yes | Retrieve the authenticated user's profile |

---

# End of Part 2
# Claim APIs

Base Path:

/api/v1/claims

Authentication:

Required unless otherwise specified.

---

# CLAIM-001 — Submit Claim

## Purpose

Create a new claim for later credibility analysis.

---

## Endpoint

POST

```
/api/v1/claims
```

---

## Authentication

Required

---

## Allowed Roles

- USER
- ADMIN

---

## Request Body

```json
{
  "claim_text": "COVID-19 vaccines contain microchips."
}
```

---

## Validation Rules

### claim_text

- Required
- Minimum length: 10 characters
- Maximum length: 2000 characters
- Leading and trailing whitespace trimmed
- Must not be empty
- Plain text only

---

## Business Rules

- Claim belongs to the authenticated user.
- The claim is stored before analysis begins.
- Credibility analysis is automatically triggered by the backend immediately after successful claim submission.
- The client does not manually start analysis through a public Analysis API.
- Initial status is:

```
PENDING
```

---

## Success Response

HTTP **201 Created**

```json
{
  "success": true,
  "message": "Claim submitted successfully.",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "claim_text": "COVID-19 vaccines contain microchips.",
    "status": "PENDING",
    "created_at": "2026-06-30T12:15:00Z"
  }
}
```

---

## Possible Errors

400

Malformed request

401

Unauthorized

422

Validation failed

429

Rate limit exceeded

---

# CLAIM-002 — List My Claims

## Purpose

Retrieve all claims submitted by the authenticated user.

---

## Endpoint

GET

```
/api/v1/claims
```

---

## Authentication

Required

---

## Query Parameters

- page
- page_size
- search
- ordering
- status
- verdict

---

## Success Response

HTTP **200 OK**

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "claim_text": "...",
      "status": "COMPLETED",
      "verdict": "MISINFORMATION",
      "credibility_score": 18,
      "created_at": "..."
    }
  ]
}
```

---

## Business Rules

- Users can only view their own claims.
- Admins use dedicated administrative endpoints.

---

# CLAIM-003 — Get Claim Details

## Purpose

Retrieve a specific claim.

---

## Endpoint

GET

```
/api/v1/claims/{claim_id}
```

---

## Authentication

Required

---

## Path Parameter

claim_id

(UUID)

---

## Success Response

```json
{
  "success": true,
  "message": "Claim retrieved successfully.",
  "data": {
    "id": "uuid",
    "claim_text": "...",
    "status": "COMPLETED",
    "created_at": "...",
    "updated_at": "...",
    "analysis_available": true
  }
}
```

---

## Business Rules

- Owner may access.
- Admin may access.
- Other users receive **403 Forbidden**.

---

# CLAIM-004 — Update Claim

## Purpose

Update a claim before credibility analysis begins.

---

## Endpoint

PATCH

```
/api/v1/claims/{claim_id}
```

---

## Authentication

Required

---

## Request Body

```json
{
  "claim_text": "Updated claim text."
}
```

---

## Business Rules

- Only the owner may update the claim.
- Updates are allowed only while status is:

```
PENDING
```

Updates are rejected if status is:

- PROCESSING
- COMPLETED
- FAILED

---

## Success Response

```json
{
  "success": true,
  "message": "Claim updated successfully.",
  "data": {
    "id": "uuid"
  }
}
```

---

## Possible Errors

403

Forbidden

409

Analysis already started

422

Validation failed

---

# CLAIM-005 — Delete Claim

## Purpose

Soft delete a claim.

---

## Endpoint

DELETE

```
/api/v1/claims/{claim_id}
```

---

## Authentication

Required

---

## Business Rules

Owner:

- May delete only pending claims.

Admin:

- May delete any inappropriate claim.

Deletion uses soft delete.

---

## Success Response

HTTP **204 No Content**

---

## Possible Errors

403

Forbidden

404

Not Found

409

Cannot delete analyzed claim

---

# CLAIM-006 — Search Claims

## Purpose

Search claims submitted by the authenticated user.

---

## Endpoint

GET

```
/api/v1/claims?search=vaccine
```

---

## Authentication

Required

---

## Search Fields

- Claim text

---

## Business Rules

- Case-insensitive
- Partial matches supported
- Leading/trailing whitespace ignored

---

# CLAIM-007 — Filter Claims

## Endpoint

GET

```
/api/v1/claims?status=COMPLETED
```

---

## Supported Filters

- status
- verdict
- date_from
- date_to

---

# CLAIM-008 — Sort Claims

## Endpoint

GET

```
/api/v1/claims?ordering=-created_at
```

---

## Allowed Fields

- created_at
- credibility_score
- status

---

# Claim Status Values

### PENDING

Claim stored successfully.

Awaiting credibility analysis.

---

### PROCESSING

Hybrid Credibility Engine is analyzing the claim.

---

### COMPLETED

Credibility analysis completed successfully.

---

### FAILED

Analysis could not be completed.

---

# Claim Lifecycle

```text
Submit Claim
      │
      ▼
PENDING
      │
      ▼
Analysis Requested
      │
      ▼
PROCESSING
      │
      ├──────────────┐
      ▼              ▼
COMPLETED         FAILED
```

---

# Permission Matrix

| Action | Guest | User | Admin |
|----------|-------|------|--------|
| Submit Claim | ❌ | ✅ | ✅ |
| View Own Claims | ❌ | ✅ | ✅ |
| Update Pending Claim | ❌ | ✅ | ✅ |
| Delete Pending Claim | ❌ | ✅ | ✅ |
| View Any Claim | ❌ | ❌ | ✅ |
| Delete Any Claim | ❌ | ❌ | ✅ |

---

# Claim API Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| /claims | POST | Submit a new claim |
| /claims | GET | List authenticated user's claims |
| /claims/{id} | GET | Retrieve claim details |
| /claims/{id} | PATCH | Update a pending claim |
| /claims/{id} | DELETE | Soft delete a claim |
| /claims?search= | GET | Search claims |
| /claims?status= | GET | Filter claims |
| /claims?ordering= | GET | Sort claims |

---

# End of Part 3
# Analysis APIs

Base Path:

/api/v1/analysis

Authentication:

Required

---

# ANALYSIS-001 — Get Analysis Status

## Purpose

Retrieve the current processing status of an AI analysis for a submitted claim.

Analysis is automatically started by the backend immediately after claim submission. Users do not manually initiate analysis.

---

## Endpoint

GET

```
/api/v1/analysis/{claim_id}/status
```

---

## Authentication

Required

---

## Allowed Roles

- Owner
- Admin

---

## Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| claim_id | UUID | Claim identifier |

---

## Success Response

HTTP 200 OK

```json
{
  "success": true,
  "message": "Analysis status retrieved successfully.",
  "data": {
    "claim_id": "uuid",
    "status": "PROCESSING"
  }
}
```

---

## Status Values

PENDING

Claim accepted and waiting to be processed.

PROCESSING

Hybrid Credibility Engine is analyzing the claim.

COMPLETED

Analysis completed successfully.

FAILED

Analysis could not be completed.

---

## Possible Errors

401 Unauthorized

403 Forbidden

404 Claim not found

---

# ANALYSIS-002 — Get Analysis Result

## Purpose

Retrieve the completed AI analysis for a claim.

If analysis is still in progress, the client should continue polling the status endpoint.

---

## Endpoint

GET

```
/api/v1/analysis/{claim_id}
```

---

## Authentication

Required

---

## Allowed Roles

- Owner
- Admin

---

## Success Response

HTTP 200 OK

```json
{
  "success": true,
  "message": "Analysis retrieved successfully.",
  "data": {
    "claim_id": "uuid",
    "analysis_status": "COMPLETED",
    "verdict": "MISINFORMATION",
    "credibility_score": 22,
    "created_at": "2026-06-30T13:05:00Z"
  }
}
```

---

## Possible Errors

401 Unauthorized

403 Forbidden

404 Analysis not found

409 Analysis still processing

---

# ANALYSIS-003 — Get Explainability

## Purpose

Return the complete explainability report generated by the Hybrid Credibility Engine.

This endpoint powers the Explainability Panel in the frontend.

---

## Endpoint

GET

```
/api/v1/analysis/{claim_id}/explanation
```

---

## Authentication

Required

---

## Success Response

```json
{
  "success": true,
  "message": "Explainability data retrieved successfully.",
  "data": {
    "verdict": "MISINFORMATION",
    "credibility_score": 22,
    "score_breakdown": {
      "classification_model": 40,
      "fact_check": 15,
      "narrative": -20,
      "rule_engine": -13
    },
    "reasoning": [
      "The AI classification model predicts this claim is likely misinformation.",
      "Trusted fact-check sources contradict the claim.",
      "Similar misinformation narratives have appeared previously."
    ]
  }
}
```

---

## Business Rules

The Explainability Panel must include:

- Final verdict
- Final credibility score
- Component score breakdown
- Fact-check findings
- Narrative Activity summary
- Rule Engine observations

---

# ANALYSIS-004 — Get Narrative Activity

## Purpose

Retrieve Narrative Activity information generated during analysis.

This helps users understand whether similar claims have previously circulated.

---

## Endpoint

GET

```
/api/v1/analysis/{claim_id}/narrative
```

---

## Authentication

Required

---

## Success Response

```json
{
  "success": true,
  "message": "Narrative activity retrieved successfully.",
  "data": {
    "similar_claims": 18,
    "highest_similarity": 94,
    "first_seen": "2026-06-20T09:12:00Z",
    "latest_occurrence": "2026-06-30T10:42:00Z",
    "activity_level": "HIGH"
  }
}
```

---

## Activity Levels

LOW

MEDIUM

HIGH

These values are derived from configurable thresholds.

---

# ANALYSIS-005 — Get Fact-check Evidence

## Purpose

Retrieve fact-check evidence used during analysis.

---

## Endpoint

GET

```
/api/v1/analysis/{claim_id}/fact-check
```

---

## Authentication

Required

---

## Success Response

```json
{
  "success": true,
  "message": "Fact-check evidence retrieved successfully.",
  "data": {
    "matches_found": 2,
    "sources": [
      {
        "title": "Independent Fact Check",
        "summary": "No evidence supports this claim.",
        "url": "https://example.org/article"
      }
    ]
  }
}
```

---

## Business Rules

- Only metadata required for explainability is stored.
- Copyrighted article content is never stored.
- External URLs are returned for reference.
- Missing fact-check results do not prevent analysis completion.

---

# Hybrid Credibility Engine

The Hybrid Credibility Engine combines multiple evidence sources to determine the final credibility score.

The AI Analysis signal is produced by an InfoTrust-specific fine-tuned misinformation classification model.

The model artifact, tokenizer, identifier, and version are configurable implementation details behind the AI Analysis Service. The model may be retrained or replaced with another compatible classifier without affecting the public API or the Hybrid Credibility Engine contract.

The engine combines signals from:

- Claim preprocessing
- AI classification model
- Fact-check retrieval
- Narrative Activity Engine
- Rule Engine
- Weighted scoring system

---

# Hybrid Engine Output

Every completed analysis produces:

| Field | Description |
|--------|-------------|
| verdict | Final classification |
| credibility_score | Final score (0–100) |
| classification_model_score | AI model contribution |
| fact_check_score | Fact-check contribution |
| narrative_score | Narrative contribution |
| rule_engine_score | Rule Engine contribution |
| explanation | Explainability report |

The internal AI Analysis Service should normalize model-specific output into a stable structure such as:

```json
{
  "prediction": "MISINFORMATION",
  "confidence": 0.96,
  "model_version": "v1"
}
```

The Hybrid Credibility Engine consumes this standardized result rather than model-specific labels or framework objects.

---

# Verdict Categories

| Verdict | Description |
|----------|-------------|
| CREDIBLE | Strong evidence supports the claim |
| UNCERTAIN | Conflicting or insufficient evidence |
| MISINFORMATION | Evidence indicates the claim is misinformation or false |

---

# Analysis Pipeline

```text
Submit Claim
      │
      ▼
Claim Stored
      │
      ▼
Automatic Analysis Triggered
      │
      ▼
Claim Preprocessing
      │
      ▼
AI Analysis Service
      │
      ▼
Model Adapter
      │
      ▼
Fine-tuned Misinformation
Classification Model
      │
      ▼
Fact-check Retrieval
      │
      ▼
Narrative Activity Detection
      │
      ▼
Rule Engine
      │
      ▼
Hybrid Credibility Engine
      │
      ▼
Explainability Generation
      │
      ▼
Store Analysis
      │
      ▼
Status = COMPLETED
      │
      ▼
Frontend Retrieves Results
```

---


## Analysis Execution Model

Claim analysis is treated as an asynchronous application workflow.

1. The claim is validated and persisted with status `PENDING`.
2. Analysis processing is triggered after claim creation.
3. The analysis workflow changes the claim status to `PROCESSING`.
4. The AI Analysis Service, Fact-check Service, Narrative Activity Engine, and Rule Engine produce their signals.
5. The Hybrid Credibility Engine calculates the final result.
6. The analysis and explainability data are persisted.
7. The claim status becomes `COMPLETED`, or `FAILED` when processing cannot complete.
8. The frontend retrieves the status and then the completed analysis.

The public API must not require clients to wait for the complete inference pipeline during the initial claim-submission request.


# Analysis API Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| /analysis/{claim_id}/status | GET | Retrieve analysis status |
| /analysis/{claim_id} | GET | Retrieve completed analysis |
| /analysis/{claim_id}/explanation | GET | Retrieve explainability data |
| /analysis/{claim_id}/narrative | GET | Retrieve narrative activity |
| /analysis/{claim_id}/fact-check | GET | Retrieve fact-check evidence |

---

# End of Part 4
# Feedback, Profile & Dashboard APIs

Authentication:

Required

Base Paths:

/api/v1/feedback

/api/v1/users

/api/v1/dashboard

---

# FEEDBACK-001 — Submit Analysis Feedback

## Purpose

Allow a user to rate whether an AI-generated analysis was helpful.

---

## Endpoint

POST

```
/api/v1/feedback
```

---

## Authentication

Required

---

## Allowed Roles

- User
- Admin

---

## Request Body

```json
{
  "claim_id": "uuid",
  "feedback": "HELPFUL"
}
```

---

## Allowed Feedback Values

HELPFUL

NOT_HELPFUL

---

## Business Rules

- One feedback per user per claim.
- User must own the claim (unless Admin).
- Feedback may be updated by submitting a new value.
- Feedback can only be submitted after analysis status is **COMPLETED**.

---

## Success Response

HTTP 201 Created

```json
{
  "success": true,
  "message": "Feedback submitted successfully.",
  "data": {
    "claim_id": "uuid",
    "feedback": "HELPFUL"
  }
}
```

---

## Possible Errors

401 Unauthorized

403 Forbidden

404 Claim not found

409 Feedback already exists (if updates are disabled)

422 Validation Error

---

# FEEDBACK-002 — Get My Feedback

## Purpose

Retrieve feedback previously submitted by the authenticated user.

---

## Endpoint

GET

```
/api/v1/feedback
```

---

## Authentication

Required

---

## Success Response

```json
{
  "success": true,
  "message": "Feedback retrieved successfully.",
  "data": [
    {
      "claim_id": "uuid",
      "feedback": "HELPFUL",
      "submitted_at": "2026-06-30T13:45:00Z"
    }
  ]
}
```

---

# USER-001 — Get User Profile

## Purpose

Retrieve the authenticated user's profile.

---

## Endpoint

GET

```
/api/v1/users/profile
```

---

## Authentication

Required

---

## Success Response

```json
{
  "success": true,
  "message": "Profile retrieved successfully.",
  "data": {
    "id": "uuid",
    "full_name": "Harshpreet Singh",
    "email": "harsh@example.com",
    "role": "USER",
    "created_at": "2026-06-30T10:00:00Z"
  }
}
```

---

# USER-002 — Update Profile

## Purpose

Update profile information.

---

## Endpoint

PATCH

```
/api/v1/users/profile
```

---

## Request Body

```json
{
  "full_name": "Harshpreet Singh"
}
```

---

## Validation Rules

Full name

- Required
- 2–100 characters
- Leading and trailing whitespace trimmed

Email changes are **not supported in v1**.

---

## Success Response

```json
{
  "success": true,
  "message": "Profile updated successfully.",
  "data": {
    "full_name": "Harshpreet Singh"
  }
}
```

---

# USER-003 — Deactivate Account

## Purpose

Allow users to deactivate their own account.

---

## Endpoint

DELETE

```
/api/v1/users/profile
```

---

## Business Rules

- Soft delete only.
- Existing claims and analyses remain for audit purposes.
- User account becomes inactive.
- Refresh tokens are invalidated.

---

## Success Response

HTTP 204 No Content

---

# DASHBOARD-001 — Get User Dashboard

## Purpose

Return summary statistics for the authenticated user.

---

## Endpoint

GET

```
/api/v1/dashboard
```

---

## Authentication

Required

---

## Success Response

```json
{
  "success": true,
  "message": "Dashboard data retrieved successfully.",
  "data": {
    "total_claims": 18,
    "completed_analyses": 17,
    "processing_analyses": 1,
    "failed_analyses": 0,
    "average_credibility_score": 63,
    "recent_claims": [
      {
        "claim_id": "uuid",
        "analysis_status": "COMPLETED",
        "verdict": "UNCERTAIN",
        "created_at": "2026-06-30T11:15:00Z"
      }
    ]
  }
}
```

---

# DASHBOARD-002 — Get Credibility Trends

## Purpose

Return historical credibility score data for chart visualization.

---

## Endpoint

GET

```
/api/v1/dashboard/trends
```

---

## Success Response

```json
{
  "success": true,
  "message": "Trend data retrieved successfully.",
  "data": [
    {
      "date": "2026-06-25",
      "average_score": 61
    },
    {
      "date": "2026-06-26",
      "average_score": 67
    }
  ]
}
```

---

# DASHBOARD-003 — Get Recent Activity

## Purpose

Return recent user activity.

---

## Endpoint

GET

```
/api/v1/dashboard/activity
```

---

## Success Response

```json
{
  "success": true,
  "message": "Recent activity retrieved successfully.",
  "data": [
    {
      "type": "CLAIM_SUBMITTED",
      "timestamp": "2026-06-30T10:40:00Z"
    },
    {
      "type": "ANALYSIS_STARTED",
      "timestamp": "2026-06-30T10:40:05Z"
    },
    {
      "type": "ANALYSIS_COMPLETED",
      "timestamp": "2026-06-30T10:42:00Z"
    },
    {
      "type": "FEEDBACK_SUBMITTED",
      "timestamp": "2026-06-30T10:45:00Z"
    }
  ]
}
```

---

# Dashboard Widgets

The dashboard displays:

- Total claims
- Completed analyses
- Processing analyses
- Failed analyses
- Average credibility score
- Recent claims
- Credibility trend chart
- Recent activity

---

# Permission Matrix

| Endpoint | Guest | User | Admin |
|----------|-------|------|--------|
| POST /feedback | ❌ | ✅ | ✅ |
| GET /feedback | ❌ | ✅ | ✅ |
| GET /users/profile | ❌ | ✅ | ✅ |
| PATCH /users/profile | ❌ | ✅ | ✅ |
| DELETE /users/profile | ❌ | ✅ | ✅ |
| GET /dashboard | ❌ | ✅ | ✅ |
| GET /dashboard/trends | ❌ | ✅ | ✅ |
| GET /dashboard/activity | ❌ | ✅ | ✅ |

---

# Part 5 API Summary

## Feedback

| Endpoint | Method | Description |
|----------|--------|-------------|
| /feedback | POST | Submit or update analysis feedback |
| /feedback | GET | Retrieve user feedback |

---

## User

| Endpoint | Method | Description |
|----------|--------|-------------|
| /users/profile | GET | Retrieve profile |
| /users/profile | PATCH | Update profile |
| /users/profile | DELETE | Deactivate account |

---

## Dashboard

| Endpoint | Method | Description |
|----------|--------|-------------|
| /dashboard | GET | Retrieve dashboard summary |
| /dashboard/trends | GET | Retrieve credibility trends |
| /dashboard/activity | GET | Retrieve recent activity |

---

# End of Part 5
# Admin APIs

Base Path:

/api/v1/admin

Authentication:

Required

Authorization:

Admin role only

---

# Authorization Rules

Every endpoint in this section requires:

- Valid JWT Access Token
- User role = ADMIN

If either condition fails:

401 Unauthorized

or

403 Forbidden

---

# ADMIN-001 — Dashboard Overview

## Purpose

Retrieve overall platform statistics.

---

## Endpoint

GET

```
/api/v1/admin/dashboard
```

---

## Success Response

```json
{
  "success": true,
  "message": "Dashboard statistics retrieved successfully.",
  "data": {
    "total_users": 124,
    "active_users": 117,
    "disabled_users": 7,
    "total_claims": 832,
    "completed_analyses": 804,
    "processing_analyses": 18,
    "failed_analyses": 10,
    "average_credibility_score": 61.7
  }
}
```

---

# ADMIN-002 — Platform Analytics

## Purpose

Retrieve platform-wide analytics for monitoring and reporting.

---

## Endpoint

GET

```
/api/v1/admin/analytics
```

---

## Query Parameters

date_from

date_to

---

## Success Response

```json
{
  "success": true,
  "message": "Analytics retrieved successfully.",
  "data": {
    "claims_per_day": [],
    "verdict_distribution": {
      "credible": 215,
      "uncertain": 193,
      "misinformation": 396
    },
    "analysis_status_distribution": {
      "completed": 804,
      "processing": 18,
      "failed": 10
    },
    "user_registrations": [],
    "narrative_activity_distribution": {
      "low": 301,
      "medium": 247,
      "high": 92
    }
  }
}
```

---

# ADMIN-003 — List Users

## Purpose

Retrieve registered users.

---

## Endpoint

GET

```
/api/v1/admin/users
```

---

## Query Parameters

page

page_size

search

ordering

status

role

---

## Success Response

```json
{
  "count": 124,
  "results": [
    {
      "id": "uuid",
      "full_name": "Harshpreet Singh",
      "email": "harsh@example.com",
      "role": "USER",
      "is_active": true,
      "created_at": "2026-06-30T10:00:00Z"
    }
  ]
}
```

---

# ADMIN-004 — Get User Details

## Purpose

Retrieve detailed information about a specific user.

---

## Endpoint

GET

```
/api/v1/admin/users/{user_id}
```

---

## Success Response

```json
{
  "success": true,
  "message": "User retrieved successfully.",
  "data": {
    "id": "uuid",
    "full_name": "Harshpreet Singh",
    "email": "harsh@example.com",
    "role": "USER",
    "is_active": true,
    "claims_submitted": 18,
    "completed_analyses": 17,
    "processing_analyses": 1,
    "failed_analyses": 0
  }
}
```

---

# ADMIN-005 — Disable User

## Purpose

Disable a user account.

---

## Endpoint

PATCH

```
/api/v1/admin/users/{user_id}/disable
```

---

## Business Rules

- Admin only.
- Cannot disable another admin.
- Cannot disable own account.
- Audit log entry is automatically created.

---

## Success Response

```json
{
  "success": true,
  "message": "User disabled successfully."
}
```

---

# ADMIN-006 — Enable User

## Purpose

Re-enable a previously disabled account.

---

## Endpoint

PATCH

```
/api/v1/admin/users/{user_id}/enable
```

---

## Business Rules

- Audit log entry is automatically created.

---

## Success Response

```json
{
  "success": true,
  "message": "User enabled successfully."
}
```

---

# ADMIN-007 — Review Claims

## Purpose

Retrieve submitted claims and their analysis status.

---

## Endpoint

GET

```
/api/v1/admin/claims
```

---

## Query Parameters

page

page_size

status

verdict

search

ordering

---

## Success Response

```json
{
  "count": 832,
  "results": [
    {
      "claim_id": "uuid",
      "claim_text": "...",
      "submitted_by": "Harshpreet Singh",
      "analysis_status": "COMPLETED",
      "verdict": "MISINFORMATION",
      "created_at": "2026-06-30T10:25:00Z"
    }
  ]
}
```

---

# ADMIN-008 — View Claim Details

## Purpose

Retrieve complete information about a submitted claim.

---

## Endpoint

GET

```
/api/v1/admin/claims/{claim_id}
```

---

## Returns

- Claim
- Complete Hybrid Credibility Engine analysis
- Explainability report
- Narrative Activity summary
- Fact-check evidence
- User feedback (if available)

---

# ADMIN-009 — Delete Claim

## Purpose

Soft delete an inappropriate claim.

---

## Endpoint

DELETE

```
/api/v1/admin/claims/{claim_id}
```

---

## Business Rules

- Soft delete only.
- Audit log entry required.
- Analysis remains stored for auditing.
- User feedback remains associated with the archived analysis.

---

## Success Response

HTTP 204 No Content

---

# ADMIN-010 — Audit Logs

## Purpose

Retrieve administrative actions.

---

## Endpoint

GET

```
/api/v1/admin/audit-logs
```

---

## Query Parameters

page

date_from

date_to

action

admin_id

---

## Success Response

```json
{
  "count": 42,
  "results": [
    {
      "id": "uuid",
      "admin": "Admin User",
      "action": "DISABLE_USER",
      "target": "user_uuid",
      "timestamp": "2026-06-30T12:10:00Z"
    }
  ]
}
```

---

# Admin Permission Matrix

| Action | Admin |
|---------|:-----:|
| View Dashboard | ✅ |
| View Analytics | ✅ |
| List Users | ✅ |
| View User Details | ✅ |
| Disable User | ✅ |
| Enable User | ✅ |
| Review Claims | ✅ |
| View Claim Details | ✅ |
| Delete Claims | ✅ |
| View Audit Logs | ✅ |

---

# Audit Log Events

Record at least the following actions:

- ADMIN_LOGIN
- ADMIN_LOGOUT
- USER_DISABLED
- USER_ENABLED
- CLAIM_DELETED
- CLAIM_RESTORED (future-ready)
- ADMIN_PROFILE_UPDATED (future-ready)

Each audit log should contain:

- Event ID
- Admin ID
- Target ID
- Action
- Timestamp
- IP Address (optional)
- Correlation ID (if available)

---

# Administrative Monitoring

The Admin Dashboard provides operational visibility into the Hybrid Credibility Engine by monitoring:

- Claim submission volume
- Analysis throughput
- Analysis success and failure rates
- Verdict distribution
- Narrative Activity trends
- Overall platform usage

InfoTrust v1 uses an InfoTrust-specific fine-tuned misinformation classification model through the AI Analysis Service.

The model implementation is configurable and replaceable. Retraining or replacing the classifier must not require changes to the public API, administrative APIs, or Hybrid Credibility Engine contract.

---

# Admin API Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| /admin/dashboard | GET | Platform overview |
| /admin/analytics | GET | Platform analytics |
| /admin/users | GET | List users |
| /admin/users/{id} | GET | User details |
| /admin/users/{id}/disable | PATCH | Disable user |
| /admin/users/{id}/enable | PATCH | Enable user |
| /admin/claims | GET | Review claims |
| /admin/claims/{id} | GET | View complete claim details |
| /admin/claims/{id} | DELETE | Soft delete claim |
| /admin/audit-logs | GET | View audit logs |

---

# End of Part 6 
# Health, Error Handling, Rate Limiting & Security APIs

Authentication:

Mixed (some public, some authenticated)

---

# HEALTH-001 — API Health Check

## Purpose

Verify that the backend API is running.

---

## Endpoint

GET

```
/api/v1/health
```

---

## Authentication

Not Required

---

## Success Response

HTTP 200 OK

```json
{
  "success": true,
  "message": "API is healthy.",
  "data": {
    "status": "UP",
    "timestamp": "2026-06-30T12:00:00Z",
    "version": "1.0.0"
  }
}
```

---

# HEALTH-002 — Readiness Check

## Purpose

Verify that the application is ready to serve requests.

Checks:

- PostgreSQL database connectivity
- Local AI model availability
- External fact-check service availability (if enabled)
- Redis connection (if caching is enabled)

---

## Endpoint

GET

```
/api/v1/health/ready
```

---

## Authentication

Admin Only

---

## Success Response

```json
{
  "success": true,
  "message": "System is ready.",
  "data": {
    "database": "UP",
    "ai_model": "UP",
    "fact_check_service": "UP",
    "cache": "UP"
  }
}
```

---

# HEALTH-003 — Liveness Check

## Purpose

Used by Docker, Render, Railway, Kubernetes, or other deployment platforms to verify that the application process is alive.

---

## Endpoint

GET

```
/api/v1/health/live
```

---

## Authentication

Not Required

---

## Success Response

```json
{
  "status": "UP"
}
```

---

# HEALTH-004 — AI Model Health

## Purpose

Verify that the configured AI model is successfully loaded and ready for inference.

---

## Endpoint

GET

```
/api/v1/health/model
```

---

## Authentication

Admin Only

---

## Success Response

```json
{
  "success": true,
  "message": "AI model is ready.",
  "data": {
    "model_id": "infotrust-misinformation-classifier",
    "model_version": "v1",
    "status": "LOADED",
    "device": "CPU"
  }
}
```

---

## Business Rules

InfoTrust v1 uses an InfoTrust-specific fine-tuned misinformation classification model.

The model identifier, version, artifact path, tokenizer configuration, and loading settings are configurable. The model may be retrained or replaced by another compatible misinformation classifier without changing the public API, provided the AI Analysis Service continues to return the standardized output expected by the Hybrid Credibility Engine.

---

# Standard Error Codes

All APIs use consistent application-level error responses.

| HTTP Code | Meaning |
|-----------|---------|
| 200 | Success |
| 201 | Resource Created |
| 202 | Accepted for Processing |
| 204 | No Content |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Failed |
| 429 | Too Many Requests |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

---

# Standard Error Response

```json
{
  "success": false,
  "message": "Validation failed.",
  "errors": {
    "claim_text": [
      "This field is required."
    ]
  },
  "request_id": "uuid"
}
```

---

# Validation Error Example

HTTP 422

```json
{
  "success": false,
  "message": "Validation failed.",
  "errors": {
    "email": [
      "Enter a valid email address."
    ],
    "password": [
      "Password must contain at least one uppercase letter."
    ]
  }
}
```

---

# Internal Server Error Example

HTTP 500

```json
{
  "success": false,
  "message": "An unexpected error occurred."
}
```

Never expose:

- Stack traces
- Internal exception messages
- Database details
- File paths

---

# Rate Limiting

Sensitive endpoints are protected.

| Endpoint | Limit |
|----------|-------|
| POST /auth/login | 10 requests/minute/IP |
| POST /auth/register | 5 requests/minute/IP |
| GET /analysis/{claim_id}/status | 120 requests/hour/user |
| POST /claims | 30 requests/hour/user |
| POST /feedback | 20 requests/hour/user |

---

## Rate Limit Response

HTTP 429

```json
{
  "success": false,
  "message": "Rate limit exceeded. Please try again later."
}
```

---

# Security Standards

## Authentication

- JWT Access Tokens
- JWT Refresh Tokens
- Short-lived Access Tokens
- Refresh Token Blacklisting
- Optional Refresh Token Rotation (future enhancement)

---

## Password Security

Passwords are stored using Argon2 (preferred) or bcrypt.

Passwords are never:

- Stored in plain text
- Logged
- Returned by any API

---

## Input Validation

Validate:

- Required fields
- Maximum lengths
- Minimum lengths
- UUID format
- Email format
- JSON schema
- Data types

Reject malformed requests.

---

## Authorization

Every protected endpoint verifies:

- JWT authentication
- User role
- Resource ownership
- Admin privileges (where required)

---

## AI Model Security

The production classification model is loaded behind the AI Analysis Service.

Requirements:

- Model identifier, version, and artifact path must be configurable.
- Model loading and preprocessing must remain isolated behind the model adapter.
- Do not expose internal inference details.
- Log inference failures.
- Return generic error responses if model inference fails.
- Allow retraining or compatible model replacement without changing public API contracts.
- Preserve the standardized AI Analysis Service output required by the Hybrid Credibility Engine.

---

## Transport Security

Production requirements:

- HTTPS only
- HSTS enabled
- Secure cookies (if introduced later)

---

## Secrets Management

Never commit:

- JWT secrets
- Database credentials
- API keys
- Hugging Face tokens (if required)
- Environment files

Use environment variables for all sensitive configuration.

---

## Logging Rules

Log:

- Authentication events
- AI inference requests
- Analysis failures
- Admin actions
- Validation failures (summary only)
- Unexpected server errors

Never log:

- Passwords
- JWT tokens
- API secrets
- Personal information
- Complete claim text (production logging)

---

# CORS Policy

Allow:

- Frontend origin(s) defined through environment variables

Block:

- Unknown origins

Allowed Methods:

- GET
- POST
- PATCH
- DELETE

Allowed Headers:

- Authorization
- Content-Type
- Accept
- X-Request-ID

---

# API Performance Targets

| Endpoint Type | Target |
|---------------|--------|
| CRUD APIs | < 300 ms |
| Dashboard APIs | < 500 ms |
| Claim Submission / Analysis Trigger | < 500 ms before background processing |
| Analysis Retrieval | < 300 ms |
| Health Checks | < 100 ms |

The AI inference process may require additional time depending on hardware. Long-running analysis should be processed asynchronously while clients poll the analysis status endpoint.

---

# Monitoring Recommendations

Track:

- Total API requests
- Response times
- Error rates
- Failed logins
- Failed analyses
- AI inference duration
- Average model confidence
- Database query times

---

# API Security Checklist

Before production deployment:

- HTTPS enabled
- JWT authentication verified
- Role-based authorization tested
- Input validation completed
- Rate limiting enabled
- CORS configured
- Environment variables configured
- Secrets protected
- Logging reviewed
- Error responses sanitized
- AI model loaded successfully

---

# Operational Readiness Checklist

Verify:

- Health endpoints respond correctly
- Database connectivity confirmed
- AI model loaded successfully
- Fact-check service reachable (if enabled)
- Redis operational (if enabled)
- Logging operational
- Monitoring configured
- Docker containers healthy
- Environment variables configured correctly

---

# End of Part 7
# API Examples, Best Practices & Future Evolution

> Version: 1.2
> Project: InfoTrust
> API Style: REST
> Authentication: JWT (Access + Refresh Tokens)

---

# Complete API Flow Example

The following sequence demonstrates the standard user journey through the InfoTrust API.

```text
Register
    │
    ▼
Login
    │
    ▼
Receive JWT Tokens
    │
    ▼
Submit Claim
    │
    ▼
Automatic Analysis Trigger
    │
    ▼
AI Analysis Service
    │
    ▼
Model Adapter
    │
    ▼
Fine-tuned Classification Model
    │
    ▼
Hybrid Credibility Engine
    │
    ├──────────────┐
    │              │
    ▼              ▼
AI Analysis     Fact-check
Signal            Search
    │              │
    └──────┬───────┘
           │
           ▼
Narrative Activity Detection
           │
           ▼
Rule-based Validation
           │
           ▼
Weighted Credibility Score
           │
           ▼
Explainability Generation
           │
           ▼
Retrieve Analysis
           │
           ▼
Submit Feedback
```

---

# Example 1 — Register

POST

```
/api/v1/auth/register
```

Request

```json
{
  "full_name": "Harshpreet Singh",
  "email": "harsh@example.com",
  "password": "StrongPassword123!",
  "confirm_password": "StrongPassword123!"
}
```

Response

```json
{
  "success": true,
  "message": "Registration successful.",
  "data": {
    "id": "uuid",
    "role": "USER"
  }
}
```

---

# Example 2 — Login

POST

```
/api/v1/auth/login
```

Request

```json
{
  "email": "harsh@example.com",
  "password": "StrongPassword123!"
}
```

Response

```json
{
  "success": true,
  "message": "Login successful.",
  "data": {
    "access_token": "<jwt_access_token>",
    "refresh_token": "<jwt_refresh_token>",
    "user": {
      "id": "uuid",
      "role": "USER"
    }
  }
}
```

---

# Example 3 — Submit Claim

POST

```
/api/v1/claims
```

Authorization

```
Bearer <access_token>
```

Request

```json
{
  "claim_text": "COVID-19 vaccines contain microchips."
}
```

Response

```json
{
  "success": true,
  "message": "Claim submitted successfully.",
  "data": {
    "id": "uuid",
    "status": "PENDING"
  }
}
```

---

# Example 4 — Retrieve Analysis

GET

```
/api/v1/analysis/{claim_id}
```

Response

```json
{
  "success": true,
  "message": "Analysis retrieved successfully.",
  "data": {
    "analysis_status": "COMPLETED",
    "verdict": "MISINFORMATION",
    "credibility_score": 22,
    "ai_prediction": "MISINFORMATION",
    "ai_confidence": 0.96
  }
}
```

---

# Example 5 — Explainability Panel

GET

```
/api/v1/analysis/{claim_id}/explanation
```

Response

```json
{
  "success": true,
  "message": "Explainability retrieved successfully.",
  "data": {
    "score_breakdown": {
      "ai_model": 52,
      "fact_check": 24,
      "narrative_activity": -12,
      "rule_engine": -8
    },
    "reasoning": [
      "The AI model classified the claim as misleading.",
      "Trusted fact-check sources contradict the claim.",
      "Similar misinformation has been detected previously."
    ]
  }
}
```

---

# Example 6 — Fact-check Evidence

GET

```
/api/v1/analysis/{claim_id}/fact-check
```

Response

```json
{
  "success": true,
  "message": "Fact-check evidence retrieved successfully.",
  "data": {
    "matches_found": 2,
    "sources": [
      {
        "title": "Independent Fact Check",
        "url": "https://example.org/article"
      }
    ]
  }
}
```

---

# Example 7 — Narrative Activity

GET

```
/api/v1/analysis/{claim_id}/narrative
```

Response

```json
{
  "success": true,
  "message": "Narrative activity retrieved successfully.",
  "data": {
    "similar_claims": 18,
    "highest_similarity": 94,
    "activity_level": "HIGH"
  }
}
```

---

# Example 8 — Submit Feedback

POST

```
/api/v1/feedback
```

Request

```json
{
  "claim_id": "uuid",
  "feedback": "HELPFUL"
}
```

Response

```json
{
  "success": true,
  "message": "Feedback submitted successfully."
}
```

---

# Example 9 — Admin Dashboard

GET

```
/api/v1/admin/dashboard
```

Response

```json
{
  "success": true,
  "message": "Dashboard statistics retrieved successfully.",
  "data": {
    "total_users": 214,
    "total_claims": 1247,
    "completed_analyses": 1180,
    "average_credibility_score": 61.3
  }
}
```

---

# API Naming Conventions

Resources should use plural nouns.

Examples

```
/users
/claims
/analysis
/feedback
/admin
```

Avoid verbs in endpoint names.

Good

```
GET /claims
```

Bad

```
GET /getClaims
```

---

# API Development Guidelines

Every endpoint should:

- Validate all inputs
- Return standardized JSON responses
- Handle exceptions gracefully
- Log important events
- Enforce authentication
- Enforce authorization
- Follow RESTful conventions
- Return appropriate HTTP status codes

---

# OpenAPI Documentation

Interactive API documentation should be automatically generated.

Recommended endpoints

```
/api/docs/
```

OpenAPI specification

```
/api/openapi.json
```

Documentation should always be generated from source code to prevent inconsistencies.

---

# API Testing

Recommended tools

- Postman
- Bruno
- Insomnia

Automated testing should cover

- Authentication
- Authorization
- Validation
- CRUD operations
- Hybrid credibility engine
- Fact-check integration
- Narrative Activity
- Feedback APIs
- Admin APIs

---

# AI Model Strategy

InfoTrust v1 uses an InfoTrust-specific fine-tuned misinformation classification model.

The model is accessed only through the AI Analysis Service and model adapter. The public API and Hybrid Credibility Engine depend on a standardized AI analysis result rather than a specific model implementation.

The model may be retrained, versioned, optimized, or replaced with another compatible classifier without requiring public API changes.

Model-specific changes should remain limited primarily to:

- Model configuration
- Model adapter
- Model loading
- Preprocessing and tokenization
- Inference
- Output mapping

The Hybrid Credibility Engine remains unchanged unless a separate architectural decision explicitly changes its scoring behavior.

---

# API Versioning Strategy

Current version

```
v1
```

Future versions

```
v2
```

Breaking API changes require a new version.

Minor improvements should remain backward compatible.

---

# Deprecation Policy

When introducing a new API version:

- Maintain the previous version during migration.
- Clearly document deprecated endpoints.
- Notify API consumers before endpoint removal.

---

# Future API Enhancements

Potential additions beyond v1 include:

- URL claim analysis
- Image-based misinformation detection
- Video misinformation detection
- Batch claim submission
- Report export (PDF / CSV)
- Multi-language support
- AI model comparison endpoint
- Queue-based asynchronous analysis
- Configurable AI model switching
- Real-time misinformation trend analytics

These features are intentionally outside the scope of the current final-year project.

---

# API Design Principles Recap

The InfoTrust API follows:

- REST architecture
- Stateless communication
- JWT authentication
- Role-based authorization
- UUID resource identifiers
- Standard JSON responses
- Consistent error handling
- Secure defaults
- Modular AI integration
- Production-ready conventions

---

# API Readiness Checklist

Before implementation begins, verify that:

✓ API endpoints are finalized

✓ Resource ownership rules are defined

✓ Authentication flow is complete

✓ Authorization matrix is documented

✓ Validation rules are specified

✓ Response formats are standardized

✓ Error handling is consistent

✓ AI integration contracts are documented

✓ Versioning strategy is established

✓ Security requirements are documented

✓ Future extensibility has been considered

---

# API Specification Version History

| Version | Date | Description |
|----------|------|-------------|
| 1.0.0 | Initial Release | Initial API specification |
| 1.1.0 | Architecture Update | Updated for the Hybrid Credibility Engine, Explainability, Narrative Activity, and modular AI service. |
| 1.2.0 | July 2026 | Replaced the fixed pre-trained model decision with an InfoTrust-specific fine-tuned misinformation classifier, preserved model replaceability, and aligned the API with automatic analysis triggering. |
| 1.3.0 | September 2026 | Recorded final ML completion, standardized the final verdict vocabulary, and clarified asynchronous analysis execution. |

---

# End of API_SPEC.md

---

# ML Decision and API Boundary Clarification

The final ML selection does **not** create a new public API contract.

The selected base model is `microsoft/deberta-v3-base`, and final production training will use cleaned WELFake + FEVER. LIAR remains external-evaluation-only. These are internal ML implementation decisions behind the AI Analysis Service.

Experiments A–D are preliminary feasibility/model-selection experiments, and the final production model has completed training and evaluation; application integration remains a separate implementation task.

Public API consumers must continue to depend on standardized InfoTrust analysis fields rather than:

* Base-model names
* Dataset names
* Training experiment identifiers
* Model checkpoint paths
* Tokenizer implementation
* Raw transformer outputs

After final production training, the deployed model version may be stored internally for traceability without coupling the public API to the underlying model.

---

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
