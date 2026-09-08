# PROJECT_RULES.md

> **Project:** InfoTrust
> **Version:** 1.0
> **Document Type:** Permanent Engineering & AI Coding Rules
> **Status:** Active
> **Last Updated:** July 2026

---

# Purpose

This document defines the permanent engineering standards, coding conventions, architectural principles, and AI development rules for the **InfoTrust** project.

Every AI-assisted development session must follow these rules unless explicitly instructed otherwise.

These rules exist to ensure that the project remains:

* Maintainable
* Scalable
* Secure
* Modular
* Professional
* Suitable for a final-year B.Tech project

---

# Project Overview

**InfoTrust** is an AI-powered misinformation detection and claim credibility assessment platform.

Users can submit textual claims, which are analyzed using a **Hybrid Credibility Engine** composed of multiple independent services.

The AI Analysis Service uses the frozen **InfoTrust-specific fine-tuned misinformation classification model** to generate an AI prediction and confidence score. The final model was fine-tuned from `microsoft/deberta-v3-base` using the approved cleaned WELFake + FEVER production training strategy. The final training and evaluation workflow is complete; application integration remains a separate implementation task.

The AI model is **not treated as the final authority**. Its prediction is considered one evidence signal and is combined with external fact-check results, rule-based analysis, and narrative activity detection to produce the final credibility assessment.

The underlying AI model must remain **replaceable**. Retraining, upgrading, or replacing the model must not require changes to the Hybrid Credibility Engine or unrelated application components.

Core features include:

* User Authentication
* Claim Submission
* AI-based Claim Classification
* Hybrid Credibility Engine
* Explainability Panel
* Narrative Activity Detection
* Fact-check Integration
* User Dashboard
* Admin Dashboard
* Feedback System

The project follows **Clean Architecture**, **RESTful API** principles, and a **modular service-oriented architecture**.

---

# Engineering Philosophy

Every implementation should optimize for the following priorities:

1. Correctness
2. Simplicity
3. Maintainability
4. Readability
5. Security
6. Scalability
7. Performance

Never sacrifice long-term maintainability for short-term convenience.

The project prioritizes **explainable hybrid credibility assessment** over relying solely on AI predictions.

---

# AI Assistant Behavior

The AI assistant acts as a **Senior Software Engineer**, not a code generator.

Always:

* Explain technical decisions.
* Challenge poor design choices.
* Recommend better alternatives.
* Follow existing architecture.
* Keep implementations modular.
* Think before generating code.

Never generate code simply because it is requested if the requested implementation violates project architecture.

---

# Mandatory Development Rules

## Rule 1 — One Milestone at a Time

Never implement multiple milestones together.

Each implementation session must focus on one clearly defined milestone or task.

---

## Rule 2 — Explain Before Implementing

Before writing code:

* Explain the solution.
* Explain why it was chosen.
* Mention trade-offs.
* List files that will be created or modified.

---

## Rule 3 — Never Skip Foundations

Do not implement higher-level features before foundational work is complete.

Implementation order must follow:

1. Project Setup
2. Database
3. Authentication
4. Backend Foundation
5. Frontend Foundation
6. Claim Management
7. AI Integration
8. Narrative Activity
9. Dashboards
10. Admin Features
11. Testing
12. Deployment

---

## Rule 4 — Keep Everything Modular

Large files should always be split into smaller modules.

Avoid "God files."

Prefer:

* Multiple focused files
* Small components
* Small services

---

## Rule 5 — Single Responsibility Principle

Every class, function, component, and service should have one responsibility.

---

## Rule 6 — Never Duplicate Logic

If similar code appears twice:

* Extract a reusable function.
* Extract a reusable hook.
* Extract a shared component.
* Extract a shared service.

---

## Rule 7 — Business Logic Never Belongs in UI

Business logic must never live inside:

* React Components
* Django Views
* Serializers

Business logic belongs in dedicated service modules.

---

## Rule 8 — Thin Controllers

Views/controllers should only:

* Validate request
* Call services
* Return response

No business logic.

---

## Rule 9 — Environment Variables Only

Never hardcode:

* API Keys
* Secrets
* Database Credentials
* URLs
* Tokens
* Sensitive Configuration

Everything belongs in environment variables.

---

## Rule 10 — No Magic Values

Extract:

* Constants
* Enums
* Configuration Values

Avoid unexplained literals in code.

---

## Rule 11 — Self-Documenting Code

Use descriptive names.

Prefer:

```text
credibilityScore
```

instead of

```text
score
```

Comments should explain **why**, not **what**.

---

## Rule 12 — Simplicity Over Cleverness

Prefer readable code over clever code.

Future maintainability is more important than reducing a few lines.

---

# Architecture Rules

Follow Clean Architecture.

```text
React UI

↓

API Layer

↓

Service Layer

↓

Repository / ORM

↓

Database
```

Do not bypass architectural layers without justification.

Each service should communicate through well-defined interfaces to maintain loose coupling and enable future enhancements.

The AI Analysis Service must expose a stable interface so that the underlying AI model can be replaced without requiring changes to the Hybrid Credibility Engine or other application services.

---

# Backend Rules

Technology:

* Python
* Django
* Django Ninja
* PostgreSQL

Rules:

* Feature-based organization.
* Thin views.
* Services contain business logic.
* Models represent data.
* Schemas validate request and response data.
* Utilities contain shared helpers.
* Keep apps cohesive.
* External AI and third-party APIs must always be accessed through dedicated service classes.

---

# Frontend Rules

Technology:

* React
* TypeScript
* Vite
* Tailwind CSS

Rules:

* Functional components only.
* Hooks over class components.
* Small reusable components.
* Reusable custom hooks.
* Avoid deeply nested JSX.
* Prefer composition over inheritance.
* Keep presentation separate from business logic.

---

# API Rules

Follow REST standards.

Always use:

```text
/api/v1/
```

Consistent response format:

Success:

```json
{
  "success": true,
  "data": {}
}
```

Failure:

```json
{
  "success": false,
  "message": "",
  "error_code": ""
}
```

Never return inconsistent JSON structures.

API endpoints should never expose internal implementation details such as AI model names or business logic.

---

# Database Rules

Rules:

* Use PostgreSQL.
* Use proper normalization.
* Use foreign keys where appropriate.
* Avoid duplicate data.
* Index frequently queried fields.
* Use UUIDs where beneficial.
* Add timestamps (`created_at`, `updated_at`) to all major tables.
* Soft delete only where business requirements justify it.
* Design tables for scalability and maintainability.

---

# AI Integration Rules

The AI module is implemented as an **AI Analysis Service**.

The AI Analysis Service is responsible only for generating an **AI prediction** and a **confidence score** from a submitted claim.

The current implementation uses an **InfoTrust-specific fine-tuned misinformation classification model**.

The model is fine-tuned separately from the main application using a suitable pretrained base model and selected misinformation/claim-classification dataset(s). Training and experimentation may be performed using **Google Colab**.

The trained model must always be accessed through a dedicated service layer.

Never invoke the AI model directly from:

* React Components
* Django Views
* Serializers

The AI model is **not the source of truth**.

Its prediction is treated as **one credibility signal** and must always be combined with other independent verification mechanisms.

The AI Analysis Service and underlying model integration must remain **replaceable**.

Model-specific responsibilities such as model loading, tokenization, inference, label mapping, and output interpretation must remain isolated within the AI model integration layer.

Replacing, retraining, or upgrading the underlying model must not require changes to:

* Hybrid Credibility Engine
* Fact-check Service
* Narrative Engine
* Rule Engine
* Frontend
* Claim management
* Database logic
* Public API contracts

The rest of the application should depend only on the stable output contract of the AI Analysis Service.

---

# Hybrid Credibility Engine

The final credibility assessment must **never** depend on the AI model alone.

Instead, the Hybrid Credibility Engine combines multiple independent signals to produce the final credibility score.

Modules:

* Preprocessing Service
* AI Analysis Service
* Fact-check Service
* Narrative Engine
* Rule Engine
* Hybrid Credibility Engine
* Explainability Engine

Responsibilities:

### Preprocessing Service

* Normalize claim text.
* Remove unnecessary whitespace.
* Standardize formatting before analysis.

### AI Analysis Service

Uses the **InfoTrust-specific fine-tuned misinformation classification model**.

Outputs:

* Prediction
* Confidence Score

Example:

```json
{
  "prediction": "Likely Misinformation",
  "confidence": 0.91
}
```

The underlying model implementation must remain hidden from other application services so that the model can be replaced without affecting the rest of the credibility pipeline.

### Fact-check Service

Responsibilities:

* Query Google Fact Check Tools API.
* Retrieve matching fact-check results.
* Extract useful metadata.
* Provide external verification signals.

### Rule Engine

Examples:

* Excessive capitalization
* Sensational language
* Suspicious wording
* Clickbait indicators
* Duplicate punctuation
* Other predefined heuristics

### Narrative Engine

Responsibilities:

* Detect repeated claim submissions.
* Track narrative activity over time.
* Identify recurring misinformation patterns.
* Support trend visualization.

### Hybrid Credibility Engine

Combines:

* AI prediction
* AI confidence
* Fact-check results
* Rule-based heuristics
* Narrative activity

Produces:

* Final Credibility Score
* Credibility Category
* Confidence Level

The Hybrid Credibility Engine owns all scoring logic.

No individual module may directly determine the final credibility score.

The Hybrid Credibility Engine must depend only on the standardized output of the AI Analysis Service and must not contain model-specific logic.

### Explainability Engine

Generates user-friendly explanations describing why a claim received its credibility assessment.

The explanation should summarize the contribution of each verification module in clear and understandable language.

---

# Security Rules

Always:

* Validate all inputs.
* Sanitize user-generated content.
* Protect against SQL Injection.
* Protect against XSS.
* Protect against CSRF.
* Store passwords using secure hashing.
* Secure API keys using environment variables.
* Apply authentication and authorization consistently.
* Follow the principle of least privilege.

Never expose:

* Secrets
* Tokens
* Database credentials
* Internal AI service configuration
* Private API keys

---

# Logging Rules

Log important events including:

* User authentication
* Claim submissions
* AI analysis results
* Fact-check API requests
* Narrative activity updates
* Errors
* Exceptions
* Administrative actions

Do not log:

* Passwords
* Secrets
* API keys
* Authentication tokens
* Sensitive personal information

---

# Testing Rules

Every feature should include appropriate testing.

Testing levels:

* Unit Tests
* Integration Tests
* API Tests

Critical modules requiring special attention:

* Authentication
* Claim submission
* AI Analysis Service
* Fact-check Service
* Hybrid Credibility Engine
* Narrative Engine

The AI Analysis Service should be tested through its standardized interface so that replacing the underlying model does not require rewriting unrelated application tests.

Testing should prioritize correctness and reliability over code coverage percentages.

---

# Git Workflow

Commit frequently.

Use meaningful commit messages.

Examples:

```text
feat(auth): implement JWT authentication
```

```text
feat(ai-analysis): integrate InfoTrust fine-tuned model
```

```text
feat(credibility): implement hybrid credibility engine
```

```text
fix(api): improve validation for claim submission
```

```text
refactor(ai-analysis): simplify AI service implementation
```

Never commit:

* Secrets
* Environment files
* API keys
* Generated artifacts
* Large datasets
* Large model checkpoints
* Temporary files

---

# Code Review Checklist

Before merging code, verify:

* Architecture is respected.
* No duplicated logic exists.
* Business logic remains inside services.
* Components remain reusable.
* APIs follow project standards.
* Environment variables are used correctly.
* Error handling is implemented.
* Logging is appropriate.
* Tests pass.
* Documentation is updated where necessary.
* AI model-specific logic remains isolated from the Hybrid Credibility Engine and unrelated application components.

---

# Definition of Done

A feature is complete only if:

* Functionality works correctly.
* Code follows project architecture.
* Code is modular.
* Edge cases are handled.
* Errors are managed gracefully.
* Tests pass.
* Documentation is updated.
* No secrets are exposed.
* Code is readable and maintainable.

For AI-related implementation, the underlying model must remain replaceable without requiring changes to unrelated application components.

---

# Future Enhancements

The architecture should support future improvements without major refactoring.

Possible enhancements include:

* Retraining or improving the InfoTrust fine-tuned model.
* Replacing the current model with a better compatible classification model.
* Supporting multilingual claim analysis.
* Additional credibility signals.
* Improved narrative detection.
* Enhanced explainability.
* More external verification sources.

The modular architecture should allow these improvements by replacing or extending individual services rather than redesigning the entire system.

---

# Guiding Principle

**Build software that is easy to understand, easy to maintain, and easy to extend.**

Prefer clean architecture over shortcuts.

Prefer modularity over complexity.

Prefer explainability over black-box decisions.

Treat AI as an intelligent assistant within the system—not as the sole authority.

Keep the underlying AI model replaceable without coupling the rest of InfoTrust to a specific model implementation.

Every architectural decision should improve the reliability, transparency, and long-term maintainability of **InfoTrust**.

---

# Final ML Development Rules

For all future AI-assisted development sessions:

* Do not replace `microsoft/deberta-v3-base` without an explicit new project decision.
* Do not add LIAR to production training data.
* Do not change the approved WELFake or FEVER label mappings silently.
* Do not report preliminary Experiments A–D as final production-model results.
* Do not claim that a production model artifact exists until the final training workflow is actually completed.
* Preserve leakage prevention, balanced domain × class sampling, validation-based checkpoint selection, and isolated held-out testing.
* Treat model-training changes separately from Hybrid Credibility Engine changes.

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
