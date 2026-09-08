# DECISIONS.md

> Project: InfoTrust
> Version: 1.1
> Status: Active
> Last Updated: September 2026

---

# Purpose

This document records the major architectural and technical decisions made during the development of **InfoTrust**.

Rather than documenting *what* was built (covered in the PRD and Architecture documents), this document explains **why** key decisions were made.

Goals:

* Capture important design decisions
* Explain trade-offs
* Prevent repeated discussions
* Help future contributors understand the architecture
* Provide justification during project evaluation and technical interviews

Every significant architectural decision should be recorded here.

---

# Decision Record Template

Each Architecture Decision Record (ADR) follows the same structure.

## Decision ID

Unique identifier.

Example:

ADR-001

---

## Title

Short descriptive name.

Example:

Technology Stack Selection

---

## Status

Possible values:

* Proposed
* Accepted
* Superseded
* Deprecated

Current project decisions should normally be marked **Accepted**.

---

## Impact

Possible values:

High

Medium

Low

Meaning:

**High**

Changing later would require major architectural changes or database migration.

**Medium**

Can be changed with moderate effort.

**Low**

Can be changed with minimal effort.

---

## Context

Describe the problem or decision that needed to be made.

---

## Decision

Describe the selected solution.

---

## Alternatives Considered

List other options that were evaluated.

---

## Advantages

Benefits of the chosen decision.

---

## Disadvantages

Trade-offs or limitations.

---

## Why This Decision Was Chosen

Explain why the selected option best fits the project's goals and constraints.

---

## Future Review

Describe when this decision should be reconsidered.

---

# ADR-001 — Technology Stack Selection

## Status

Accepted

---

## Impact

High

---

## Context

InfoTrust requires a technology stack that:

* Supports AI-assisted misinformation detection
* Is free and open-source where possible
* Has strong documentation
* Is suitable for a single developer
* Can be completed within a few months
* Produces an industry-standard portfolio project
* Allows future replacement or upgrade of the AI classification model with minimal code changes

---

## Decision

The selected technology stack is:

### Frontend

* React
* TypeScript
* Vite
* Tailwind CSS

### Backend

* Django
* Django Ninja

### Database

* PostgreSQL

### Authentication

* JWT (Access + Refresh Tokens)

### AI

* Hybrid Credibility Engine
* AI Service abstraction layer
* InfoTrust-specific fine-tuned misinformation classification model
* Model configuration through environment variables/settings to enable retraining, upgrading, or future replacement
* Stable AI Service contract to prevent the rest of the application from depending on a specific model implementation

### Deployment

Frontend

* Vercel

Backend

* Render

Database

* Neon PostgreSQL

---

## Alternatives Considered

### Backend

* FastAPI
* Flask
* Express.js
* Spring Boot

### Frontend

* Angular
* Vue
* Next.js

### Database

* MySQL
* SQLite
* MongoDB

### Authentication

* Session Authentication
* OAuth

### AI Models

* Fixed pre-trained misinformation classifiers
* RoBERTa-based fake news classifiers
* DistilBERT classifiers
* Alternative fine-tuned Transformer models

---

## Advantages

* Mature ecosystem
* Large community support
* Excellent Python AI ecosystem
* Strong typing on the frontend
* Easy deployment
* Good scalability for a final-year project
* Professional industry-standard stack
* Fine-tuned model provides a project-specific AI classification component
* AI model can be retrained, upgraded, or replaced without changing the API or frontend
* Clean separation between application logic and AI implementation

---

## Disadvantages

* Django is more opinionated than FastAPI.
* PostgreSQL has a steeper learning curve than SQLite.
* TypeScript adds initial complexity compared to JavaScript.
* Transformer-based models require more computational resources than traditional machine learning models.
* Fine-tuning introduces additional work for dataset preparation, training, evaluation, and model management.

---

## Why This Decision Was Chosen

The selected stack provides the best balance between:

* Learning value
* Development speed
* Maintainability
* Industry relevance
* AI ecosystem support
* Final-year project feasibility
* Future extensibility

Rather than using a fixed pretrained misinformation classifier as the final project model, InfoTrust uses its own **fine-tuned misinformation classification model**.

Fine-tuning allows the classification component to be adapted to the selected misinformation detection task while giving the project greater control over model training and evaluation.

The model remains behind an **AI Service abstraction layer**.

The rest of the application communicates with the AI Service through a stable contract rather than depending directly on:

* The base model
* Model architecture
* Tokenizer
* Model storage location
* Model version
* Inference implementation

This ensures that the fine-tuned model can later be retrained, upgraded, or replaced without requiring changes to the frontend, public API contracts, Hybrid Credibility Engine, or unrelated backend modules.

---

## Future Review

Reconsider the model implementation if:

* The current fine-tuned model does not achieve acceptable evaluation results.
* A different base model provides materially better results.
* Improved training data becomes available.
* Model inference creates unacceptable deployment or performance constraints.
* The model needs to be retrained or replaced.

A change to the underlying classification model should **not automatically require reconsideration of the overall InfoTrust architecture**.

As long as a replacement model satisfies the standardized AI Service contract, the change should remain isolated primarily to the AI layer.

---

# ADR-002 — Backend Framework

## Status

Accepted

---

## Impact

High

---

## Context

The backend must support:

* REST APIs
* Authentication
* AI integration
* Database operations
* Admin functionality
* Clean Architecture
* Easy maintenance
* Modular service-based design

Several Python frameworks were evaluated.

---

## Decision

Use:

* Django
* Django Ninja

Architecture style:

* Modular Monolith
* Clean Architecture principles
* Service Layer pattern
* Repository abstraction where appropriate

API style:

* REST

---

## Alternatives Considered

* FastAPI
* Flask
* Express.js
* Spring Boot

---

## Advantages

* Mature ecosystem
* Excellent ORM
* Built-in admin capabilities
* Strong security defaults
* Robust authentication support
* Excellent integration with Python AI libraries
* Clear separation of concerns
* Easy integration of configurable AI services

---

## Disadvantages

* Larger framework than Flask.
* More opinionated than FastAPI.
* Some built-in features are unnecessary for this project's scope.

---

## Why This Decision Was Chosen

Django offers the best balance of productivity, security, maintainability, and ecosystem support for a single-developer AI-powered web application.

Django Ninja provides modern, type-safe API development while leveraging Django's mature ecosystem.

A Modular Monolith architecture keeps the project manageable while allowing AI components, business logic, APIs, and data access layers to remain cleanly separated.

The fine-tuned classification model remains isolated behind the AI Service abstraction rather than being directly integrated into API routes or unrelated business services.

This separation ensures that model-specific operations such as:

* Model loading
* Tokenization
* Input preparation
* Inference
* Label mapping
* Confidence extraction
* Model version handling

remain inside the AI layer.

---

## Future Review

If AI processing becomes sufficiently resource-intensive to justify independent deployment, the AI analysis component may be extracted into a dedicated service while keeping Django as the primary application backend.

Likewise, the underlying fine-tuned classification model may be retrained, upgraded, or replaced without requiring extraction into a microservice.

Model replacement and service extraction are separate architectural decisions.

As long as the AI Service maintains its standardized contract, the rest of the application should remain unaffected by changes to the underlying model implementation.

---

# End of Part 1
# ADR-003 — Frontend Framework

## Status

Accepted

---

## Impact

High

---

## Context

InfoTrust requires a frontend that:

* Supports modern component-based development
* Provides an excellent developer experience
* Is easy to maintain and scale
* Supports responsive and accessible UI
* Integrates cleanly with REST APIs
* Has strong industry adoption
* Separates presentation from business logic

---

## Decision

Use:

* React
* TypeScript
* Vite
* Tailwind CSS

State Management:

* React Context API (authentication and global state)
* TanStack Query (React Query) for server state management
* Custom Hooks for reusable logic

HTTP Client:

* Axios

Routing:

* React Router

Forms:

* React Hook Form
* Zod validation

Charts & Data Visualization:

* Recharts

---

## Alternatives Considered

* Angular
* Vue.js
* Next.js
* Plain React (JavaScript)

---

## Advantages

* Large ecosystem
* Strong community support
* Fast development with Vite
* Type safety through TypeScript
* Highly reusable component architecture
* Efficient API data fetching with React Query
* Excellent resume and industry value
* Easy integration with Django REST APIs

---

## Disadvantages

* TypeScript introduces additional learning.
* React requires more architectural decisions than opinionated frameworks.
* React Query introduces another dependency that developers must understand.

---

## Why This Decision Was Chosen

This stack provides the best balance between:

* Performance
* Developer productivity
* Maintainability
* Industry relevance
* Learning outcomes
* Scalability

React, together with TypeScript and Vite, enables rapid development while keeping the codebase modular and maintainable. React Query simplifies server-state synchronization and caching, reducing boilerplate and improving API performance.

---

## Future Review

If SEO, server-side rendering, or edge rendering becomes a requirement, evaluate migration to Next.js while preserving the existing component architecture.

---

# ADR-004 — Database Selection

## Status

Accepted

---

## Impact

High

---

## Context

InfoTrust stores:

* Users
* Claims
* AI analyses
* Explainability data
* Narrative Activity metadata
* Fact-check metadata
* User feedback
* Audit logs

The database must support:

* Relational data
* Strong consistency
* Complex queries
* Efficient indexing
* ACID transactions
* Production deployment

---

## Decision

Use PostgreSQL.

Hosted on:

* Neon PostgreSQL (Production)

Access through:

* Django ORM

---

## Alternatives Considered

* SQLite
* MySQL
* MongoDB

---

## Advantages

* Excellent relational capabilities
* ACID compliance
* Strong indexing support
* Mature ecosystem
* Powerful JSON support where needed
* Excellent Django integration
* Production-ready scalability

---

## Disadvantages

* Slightly more setup than SQLite.
* More advanced than necessary for very small applications.

---

## Why This Decision Was Chosen

InfoTrust has a highly relational data model.

Users, Claims, AI Analyses, Feedback, and Audit Logs naturally fit relational database design.

PostgreSQL offers the best balance of reliability, performance, scalability, and industry relevance while remaining easy to integrate with Django.

---

## Future Review

Evaluate read replicas, partitioning, or horizontal scaling only if the application experiences significant production growth.

---

# ADR-005 — Authentication Strategy

## Status

Accepted

---

## Impact

High

---

## Context

InfoTrust requires secure authentication for:

* Registered users
* Administrators

The frontend and backend are deployed independently and communicate exclusively through REST APIs.

---

## Decision

Authentication:

* JWT Authentication

Tokens:

* Access Token
* Refresh Token

User Identifier:

* Email Address

Authorization:

* Role-Based Access Control (RBAC)

Roles:

* Guest
* User
* Admin

Token Storage:

* Access Token stored securely on the client
* Refresh Token used only for obtaining new access tokens

---

## Alternatives Considered

* Django Session Authentication
* OAuth
* API Keys

---

## Advantages

* Stateless authentication
* Easy React integration
* Well suited for REST APIs
* Horizontally scalable
* Industry standard
* Clean separation between frontend and backend

---

## Disadvantages

* Requires careful token handling.
* Refresh-token revocation adds implementation complexity.

---

## Why This Decision Was Chosen

JWT authentication provides the best balance of:

* Security
* Simplicity
* Scalability
* Compatibility with a decoupled React frontend

Using email as the canonical user identifier simplifies registration, login, validation, and user management while avoiding unnecessary username management.

---

## Security Decisions

### Passwords

* Never stored in plain text.
* Hashed using Django's secure password hashing mechanism.

### Access Tokens

* Short-lived.
* Required for every protected API request.

### Refresh Tokens

* Used only to obtain new access tokens.
* Invalidated during logout.

---

# End of Part 2
# ADR-006 — Hybrid Credibility Engine

## Status

Accepted

---

## Impact

High

---

## Context

Relying entirely on a single AI model for misinformation detection creates several problems:

* Model predictions may be incorrect.
* Confidence scores do not guarantee factual correctness.
* A model may lack external evidence.
* A model may fail on claims outside its training distribution.
* A model may become outdated or need replacement.
* A single-model approach provides limited explainability.

InfoTrust therefore requires a credibility assessment architecture that does not treat the AI model as the final authority.

The system should combine multiple independent signals while keeping the underlying classification model replaceable.

---

## Decision

Use a **Hybrid Credibility Engine**.

The engine combines four primary credibility signals:

1. Fact-check Evidence
2. AI Analysis
3. Narrative Activity
4. Rule Engine

Initial weighting:

| Signal              | Weight |
| ------------------- | -----: |
| Fact-check Evidence |    40% |
| AI Analysis         |    35% |
| Narrative Activity  |    15% |
| Rule Engine         |    10% |

Weights remain configurable.

The AI Analysis signal is provided through the **AI Analysis Service**, which uses the configured InfoTrust-specific fine-tuned misinformation classification model.

The fine-tuned model provides an AI prediction and confidence score but does not independently determine the final credibility assessment.

---

## Alternatives Considered

### Single AI Model

Use only the classification model prediction.

Rejected because:

* Too dependent on one model.
* Limited explainability.
* No external evidence.
* Model errors directly become final verdict errors.

---

### Fact-check API Only

Use only external fact-check databases.

Rejected because:

* Many claims may not already have fact-check records.
* External API availability cannot be guaranteed.
* Does not provide useful analysis for unseen claims.

---

### Rule-Based System Only

Use deterministic linguistic heuristics.

Rejected because:

* Too simplistic.
* Weak semantic understanding.
* Easy to bypass.
* Cannot provide sufficient credibility assessment alone.

---

### Multiple AI Models / Ensemble

Use several classifiers simultaneously.

Rejected for Version 1 because:

* Higher inference cost.
* Greater deployment complexity.
* More difficult evaluation.
* Unnecessary for the current project scope.

The architecture does not prevent compatible ensemble approaches from being evaluated in future versions.

---

## Advantages

* Reduces dependence on a single AI prediction.
* Combines multiple independent credibility signals.
* Better explainability.
* Modular architecture.
* Easier future improvements.
* AI model can be replaced without affecting APIs.
* Hybrid Credibility Engine does not depend directly on model implementation details.
* Better academic demonstration of software architecture.

---

## Disadvantages

* Higher implementation complexity.
* Multiple evidence sources require orchestration.
* More configuration than a single-model solution.
* Weight selection requires evaluation and may require future calibration.
* Fine-tuned model development requires dataset preparation, training, evaluation, and model management.

---

## Why This Decision Was Chosen

The Hybrid Credibility Engine provides the best balance between:

* Accuracy
* Explainability
* Maintainability
* Extensibility
* Academic value

It also demonstrates good software engineering practices by separating AI inference from business logic.

The move from a fixed pretrained misinformation classifier to an InfoTrust-specific fine-tuned classification model does **not** change the Hybrid Credibility Engine itself.

The model continues to provide only the **AI Analysis signal**, while:

* Fact-check Evidence remains an independent signal.
* Narrative Activity remains an independent contextual signal.
* Rule Engine analysis remains deterministic.
* The Hybrid Credibility Engine remains responsible for combining the signals.

This separation prevents model-specific implementation decisions from spreading into the core credibility logic.

---

## Architectural Principles

The Hybrid Credibility Engine must:

* Be modular.
* Support configurable scoring weights.
* Continue operating when one evidence provider is unavailable where possible.
* Never couple business logic to a specific AI model.
* Store sufficient evidence for future explanation.
* Consume standardized AI Analysis Service output rather than raw model-specific output.
* Allow the underlying classification model to be retrained, upgraded, or replaced without redesigning the engine.

---

## AI Model Strategy

Version 1 uses an **InfoTrust-specific fine-tuned misinformation classification model**.

The target production model will be fine-tuned from the selected `microsoft/deberta-v3-base` base model using the approved cleaned WELFake + FEVER production training strategy. The final production model has completed training and evaluation; application integration remains a separate implementation task.

The fine-tuned model is treated as an implementation detail behind the AI Analysis Service.

The dependency structure is:

```text
Hybrid Credibility Engine
        ↓
AI Analysis Service
        ↓
Model Adapter / Loader
        ↓
Configured Fine-tuned Model
```

The AI Analysis Service is responsible for:

* Loading the configured model.
* Preparing model input.
* Tokenizing claim text where required.
* Running inference.
* Interpreting raw model output.
* Mapping model-specific labels to InfoTrust's standardized labels.
* Extracting confidence scores.
* Validating model output.
* Returning standardized AI analysis results.

A standardized result may contain:

```json
{
  "prediction": "MISINFORMATION",
  "confidence": 0.91
}
```

The Hybrid Credibility Engine depends on this standardized output rather than the underlying model architecture.

Therefore, if the current fine-tuned model is replaced:

```text
Hybrid Credibility Engine
        ↓
AI Analysis Service
        ↓
Model Adapter / Loader
        ↓
Replacement Compatible Model
```

the rest of the credibility pipeline should continue operating without redesign.

The replacement model must satisfy the expected AI Analysis Service contract.

---

## Model Replaceability Requirement

Model replaceability is an explicit architectural requirement.

The classification model may need to change because:

* Evaluation results are insufficient.
* A better base model becomes available.
* Improved training data becomes available.
* The current model is too resource-intensive.
* Deployment constraints change.
* Retraining produces a better model version.
* A different compatible classifier becomes more suitable.

Changing the model should primarily require modifications within:

* Model configuration
* Model adapter
* Model loading
* Tokenization or preprocessing
* Label mapping
* Inference implementation

It should **not** require changes to:

* Frontend
* Public REST API contracts
* Authentication
* Claim management
* Fact-check Service
* Narrative Activity
* Rule Engine
* Hybrid Credibility Engine
* Dashboard functionality
* Administrative functionality

provided that the standardized AI Analysis Service contract remains compatible.

---

## Model Versioning

Each deployed model should have an identifiable version.

Where practical, analysis records should retain the model version associated with the AI prediction.

This supports:

* Reproducibility
* Debugging
* Evaluation
* Comparison between model versions
* Rollback

Model versioning should remain lightweight for Version 1 and should not introduce unnecessary model-registry infrastructure.

---

## Failure Handling

If model inference fails:

* The failure should be logged.
* The system must not fabricate an AI prediction.
* Other independent credibility signals should continue where possible.
* The Hybrid Credibility Engine should handle the unavailable AI signal according to its configured aggregation policy.
* Unrelated application functionality should remain operational.

This prevents failure of the ML component from becoming failure of the entire application.

---

## Future Review

Potential future enhancements:

* Improved fine-tuned misinformation models
* Alternative compatible base models
* Additional training datasets
* Confidence calibration
* Ensemble classifiers
* Source credibility scoring
* Multi-model voting

These enhancements should be evaluated separately.

Replacing or retraining the current classification model does not by itself require replacing the Hybrid Credibility Engine.

---

# ADR-007 — Narrative Activity Detection

## Status

Accepted

---

## Impact

Medium

---

## Context

False or misleading claims often appear repeatedly with slight wording changes.

Traditional fact-checking cannot identify recurring misinformation within the application's own database.

Recognizing repeated narratives provides useful context during analysis.

---

## Decision

Implement **Narrative Activity Detection**.

The system compares newly analyzed claims against previously analyzed claims to measure semantic similarity.

For each claim, the system stores:

* Similar claim count
* Highest similarity score
* First occurrence
* Latest occurrence
* Activity level

Narrative Activity contributes supporting evidence to the Hybrid Credibility Engine but is never the sole determinant of a verdict.

---

## Alternatives Considered

* Exact text matching
* Keyword matching
* No similarity detection

---

## Advantages

* Detects recurring misinformation.
* Improves explainability.
* Adds an original feature beyond basic fake news classification.
* Provides valuable analytics.

---

## Disadvantages

* Similarity search increases computation.
* Similarity thresholds require tuning.

---

## Why This Decision Was Chosen

Narrative Activity adds meaningful contextual evidence while remaining feasible for a final-year project.

It demonstrates practical use of semantic similarity without requiring large-scale social network analysis.

---

## Architectural Principles

Narrative Activity is:

* Informational
* Independent
* Non-deterministic

It supports—but never overrides—the Hybrid Credibility Engine.

---

## Future Review

Potential enhancements:

* Narrative clustering
* Trend graphs
* Temporal analysis
* Cross-language similarity
* Visualization dashboards

---

# ADR-008 — Explainability Panel

## Status

Accepted

---

## Impact

High

---

## Context

Generated verdicts should be understandable.

Displaying only a credibility score provides little transparency.

Explainability improves user trust and strengthens the academic value of the project.

---

## Decision

Every completed analysis includes an **Explainability Panel**.

The panel presents:

* Final verdict
* Credibility score
* AI model prediction
* Fact-check evidence summary
* Narrative Activity summary
* Rule Engine observations
* Component score breakdown
* Human-readable explanation

---

## Example Components

* AI Classification
* Fact-check Evidence
* Narrative Activity
* Rule Engine
* Final Hybrid Score

---

## Alternatives Considered

* Verdict only
* Score only
* AI prediction only

---

## Advantages

* Improves transparency.
* Builds user trust.
* Makes AI decisions easier to understand.
* Supports explainable AI principles.
* Strengthens project evaluation during demonstrations.

---

## Disadvantages

* Requires storing additional analysis metadata.
* Explanation quality depends on available supporting evidence.

---

## Why This Decision Was Chosen

Explainability is a core objective of InfoTrust.

The project focuses not only on predicting misinformation but also on helping users understand why a particular verdict was reached.

This aligns with modern Explainable AI (XAI) principles.

The Explainability Panel presents the standardized prediction produced by the AI Analysis Service rather than depending on implementation-specific details of the underlying fine-tuned model.

This allows the classification model to change while preserving the user-facing explanation structure.

---

## Architectural Principles

The Explainability Panel should:

* Reflect stored evidence only.
* Never fabricate explanations.
* Clearly separate evidence from interpretation.
* Produce consistent results for stored analyses.
* Depend on standardized analysis data rather than model-specific raw outputs.

---

## Future Review

Potential enhancements:

* Interactive explanation graphs
* Confidence visualization
* Source reliability indicators
* Explanation comparison across analyses

These are intentionally outside the scope of Version 1.

---

# Design Philosophy

The core analysis workflow is:

```text
Claim
   │
   ▼
AI Analysis Service
   │
   ▼
Fine-tuned Classification Model
   │
   ▼
Standardized AI Classification
   │
   ├──────────────┐
   ▼              ▼
Fact-check    Narrative
 Evidence      Activity
   │              │
   └──────┬───────┘
          ▼
Rule Engine
          │
          ▼
Hybrid Credibility Engine
          │
          ▼
Explainability Panel
          │
          ▼
Final User Experience
```

InfoTrust is designed to provide not only a credibility verdict but also a transparent, evidence-based explanation that enables users to understand how that verdict was produced.

The classification model remains one component of this workflow rather than the final authority.

Its implementation remains isolated behind the AI Analysis Service so that model changes do not unnecessarily affect the rest of the application.

---

# End of Part 3
# ADR-009 — Backend Architecture

## Status

Accepted

---

## Impact

High

---

## Context

The backend should be:

* Modular
* Maintainable
* Easy to test
* Easy to extend
* Suitable for a single developer
* Scalable without unnecessary complexity
* Independent of infrastructure where practical
* Independent of specific AI model implementations

The backend must also support the Hybrid Credibility Engine while ensuring that changes to the underlying fine-tuned classification model do not unnecessarily affect unrelated application modules.

---

## Decision

Use a **Clean Architecture** with a **Modular Monolith** deployment.

The application is organized into feature modules while maintaining clear architectural layers.

Example modules:

* Authentication
* Users
* Claims
* Analysis
* Dashboard
* Feedback
* Admin

Each module contains, where applicable:

* Models
* Schemas
* Services
* Selectors
* API Routes
* Permissions
* Tests

Business logic remains independent from API implementation wherever practical.

AI model inference is isolated behind the **AI Analysis Service**.

The backend must not allow unrelated modules to communicate directly with the underlying fine-tuned classification model.

The intended dependency direction is:

```text
API Layer
    ↓
Application Services
    ↓
Analysis Services
    ↓
Hybrid Credibility Engine
    ↓
AI Analysis Service
    ↓
Model Adapter / Loader
    ↓
Configured Fine-tuned Model
```

Other analysis components such as:

* Fact-check Service
* Narrative Activity
* Rule Engine

remain independently accessible to the Hybrid Credibility Engine.

---

## Alternatives Considered

* Traditional Layered Monolith
* Microservices
* Serverless Architecture

---

## Advantages

* Clear separation of concerns
* Easier testing
* Easier maintenance
* Easier onboarding
* Simple deployment
* Well suited for a final-year project
* Can evolve into microservices if required
* AI implementation remains isolated
* Classification model can be replaced with limited backend changes
* Prevents model-specific logic from spreading across application modules

---

## Disadvantages

* More project structure than a simple CRUD application.
* Requires discipline to maintain architectural boundaries.
* AI abstraction introduces a small amount of additional structure.

---

## Why This Decision Was Chosen

Clean Architecture provides long-term maintainability without introducing unnecessary operational complexity.

Deploying as a Modular Monolith keeps development simple while preserving clear module boundaries.

This architecture is especially important for the AI component because the fine-tuned classification model may evolve independently from the rest of InfoTrust.

The application therefore depends on the **AI Analysis Service contract**, not directly on a particular model implementation.

If the classification model is retrained, upgraded, or replaced, changes should remain primarily within the AI Analysis implementation rather than propagating through the backend.

---

## Future Review

If the project grows into multiple independently deployable services, consider extracting the AI Analysis Service into a dedicated service while preserving its existing contract.

Microservices should not be introduced unless operational or scaling requirements justify the additional complexity.

---

# ADR-010 — API Architecture

## Status

Accepted

---

## Impact

High

---

## Context

The frontend and backend require a stable communication interface.

The API should:

* Be easy to understand.
* Be easy to test.
* Support React integration.
* Support authentication.
* Be versioned.
* Remain independent of internal AI model implementation details.

Changes to the classification model should not require frontend API changes when the externally visible analysis contract remains compatible.

---

## Decision

Use a **REST API**.

All endpoints are:

* Versioned
* Stateless
* JSON-based
* Documented
* JWT-protected where required

Base path:

```text
/api/v1/
```

API documentation will be generated automatically using Django Ninja's OpenAPI support.

The public API exposes standardized InfoTrust analysis results rather than raw model-specific outputs.

For example, API consumers may receive standardized fields representing:

* AI prediction
* AI confidence
* Final credibility score
* Credibility category
* Fact-check evidence
* Narrative Activity
* Rule Engine observations
* Explainability data

Internal model details such as:

* Model architecture
* Raw logits
* Tokenizer implementation
* Framework-specific tensors
* Internal label identifiers

must not become part of the public API contract unless explicitly required.

---

## Alternatives Considered

* GraphQL
* gRPC
* SOAP

---

## Advantages

* Industry standard
* Easy frontend integration
* Excellent tooling
* Simple debugging
* Strong OpenAPI support
* Keeps frontend independent of AI implementation details
* Supports future model replacement without unnecessary API changes

---

## Disadvantages

* Some screens may require multiple requests.

---

## Why This Decision Was Chosen

REST provides the best balance of simplicity, tooling, maintainability, and industry relevance for InfoTrust.

A stable REST contract also creates an important boundary between the application and the underlying AI implementation.

The frontend should consume standardized analysis results and should not need to know which fine-tuned model generated the AI classification signal.

---

## Future Review

Evaluate GraphQL only if frontend data requirements become significantly more complex.

Changing the underlying classification model alone is not sufficient reason to introduce a new API version.

A new API version should be considered only when externally visible API contracts require breaking changes.

---

# ADR-011 — Business Logic Placement

## Status

Accepted

---

## Impact

High

---

## Context

Business logic can easily become scattered across:

* Views
* Models
* Schemas
* Utility functions
* AI inference code

This makes testing and maintenance difficult.

Model-specific inference logic can create additional coupling if preprocessing, model loading, label interpretation, or confidence handling becomes embedded directly inside general business services.

---

## Decision

Business logic belongs primarily in **Service Classes**.

Views (API Controllers) should:

* Validate requests
* Authorize access
* Call services
* Return responses

Services should:

* Execute business rules
* Coordinate the Hybrid Credibility Engine
* Manage transactions
* Interact with models
* Call external services

Models should:

* Represent persistent data
* Enforce database integrity

Selectors should:

* Perform read-only queries
* Aggregate data
* Never modify data

The **AI Analysis Service** is responsible for coordinating classification inference through the configured model implementation.

Model-specific responsibilities should remain inside the AI layer, including:

* Model loading
* Tokenization
* Model-specific preprocessing
* Inference
* Raw output interpretation
* Label mapping
* Confidence extraction
* Model version identification

General application services must consume standardized AI analysis results rather than raw model outputs.

---

## Alternatives Considered

* Fat Models
* Fat Views
* Utility-only Architecture
* Direct model calls from business services

---

## Advantages

* Better separation of concerns
* Easier testing
* Reusable business logic
* Improved readability
* Easier future refactoring
* Model-specific code remains isolated
* Easier model replacement
* AI Analysis Service can be mocked during application testing

---

## Disadvantages

* More files
* Slightly more architectural discipline required
* Requires maintaining a clear contract between the AI layer and application services

---

## Why This Decision Was Chosen

Service classes provide a clean separation between HTTP handling and business logic while remaining lightweight and scalable.

Separating AI inference from general business logic is particularly important because the classification model is expected to remain replaceable.

Application services should care about the result of AI analysis, not how a particular model produced that result.

For example:

```text
Claim Service
      ↓
Hybrid Credibility Engine
      ↓
AI Analysis Service
      ↓
Configured Model Adapter
      ↓
Fine-tuned Model
```

If the model changes, the upper layers should continue operating against the same standardized AI Analysis Service contract.

---

## Future Review

Introduce domain services or application services only if business rules become significantly more complex.

If multiple fundamentally different model implementations are introduced later, the AI layer may introduce additional adapters or provider interfaces without changing the general service-layer architecture.

---

# ADR-012 — Data Access Strategy

## Status

Accepted

---

## Impact

Medium

---

## Context

Some architectures introduce a Repository Pattern between business logic and the ORM.

For a project of this size, the additional abstraction may not provide sufficient value.

InfoTrust also needs to store analysis metadata such as AI predictions and sufficient information to understand which model version produced a stored prediction.

---

## Decision

Use Django ORM directly within Service Classes and Selectors.

Do **not** introduce a Repository Pattern in Version 1.

Selectors are responsible for complex read operations.

Services are responsible for write operations and business rules.

Analysis persistence should remain independent of model-specific implementation details wherever practical.

Stored AI analysis metadata may include standardized information such as:

* Prediction
* Confidence score
* Model identifier
* Model version
* Analysis timestamp

Raw framework-specific model objects or inference structures must not be persisted as application-domain data.

---

## Alternatives Considered

* Repository Pattern
* Custom Data Access Layer

---

## Advantages

* Less boilerplate
* Faster development
* Easier debugging
* Aligns with Django best practices
* Simpler learning curve
* Supports model traceability without coupling persistence to model internals

---

## Disadvantages

* Data access remains coupled to Django ORM.

---

## Why This Decision Was Chosen

The Repository Pattern would introduce unnecessary complexity without significant architectural benefit for a final-year project.

Django ORM already provides a mature abstraction for database access.

The replaceability of the AI model does not require introducing another database abstraction layer.

Model independence should instead be achieved through the AI Analysis Service and standardized persisted analysis data.

If future requirements justify additional persistence abstraction, it can be introduced incrementally.

---

## Future Review

Revisit this decision if:

* Multiple databases are introduced.
* Data access becomes significantly more complex.
* Django ORM is replaced.
* Independent persistence layers become necessary.

Changing or retraining the AI classification model alone does not justify introducing a Repository Pattern.

---

# Architectural Principles

Every future implementation must follow these principles.

## Separation of Concerns

Each layer has one responsibility.

* API Routes handle HTTP.
* Services contain business logic.
* Selectors perform read-only queries.
* Models manage persistence.
* Schemas validate data.
* AI Services communicate with AI models.
* Model adapters contain model-specific integration logic.

---

## SOLID Principles

Follow:

* Single Responsibility Principle
* Open/Closed Principle
* Liskov Substitution Principle
* Interface Segregation Principle
* Dependency Inversion Principle

Where practical.

---

## Dependency Injection

Where practical, depend on interfaces or abstractions instead of concrete implementations.

This particularly applies to:

* AI model implementations
* External APIs
* Fact-check providers

The Hybrid Credibility Engine must depend on the AI Analysis Service contract rather than a concrete fine-tuned model.

---

## AI Model Isolation

The underlying classification model is an implementation detail.

Model-specific logic must remain isolated within the AI layer.

The following components must not directly depend on a specific model implementation:

* API Routes
* Authentication
* Claims
* Dashboard
* Feedback
* Admin
* Fact-check Service
* Narrative Activity
* Rule Engine
* Hybrid Credibility Engine
* Explainability presentation logic

Model replacement should primarily affect:

* Model configuration
* Model adapter
* Model loader
* Tokenization or preprocessing
* Inference implementation
* Output mapping

provided that the standardized AI Analysis Service contract remains compatible.

---

## Stable AI Contract

The AI Analysis Service should return a standardized result independent of the underlying model.

Conceptually:

```text
AIAnalysisResult
├── prediction
├── confidence
├── model_identifier
└── model_version
```

Additional internal metadata may be retained when required, but application business logic should not depend on model-specific raw outputs.

---

## Keep It Simple

Avoid unnecessary abstraction.

Prefer the simplest solution that satisfies the requirements.

Model replaceability does not justify building a complex plugin framework, model registry, or microservice architecture in Version 1.

---

## DRY (Don't Repeat Yourself)

Extract reusable logic.

Avoid duplicated validation, business rules, queries, preprocessing, or model-output mapping.

---

## Fail Fast

Validate inputs early.

Return meaningful errors before performing expensive operations.

AI input should be validated before inference is triggered.

---

## Graceful AI Failure

Failure of the classification model must not unnecessarily crash unrelated application functionality.

If AI inference fails:

* Log the failure.
* Do not fabricate an AI prediction.
* Mark the AI signal as unavailable.
* Continue independent analysis components where possible.
* Allow the Hybrid Credibility Engine to apply its configured fallback behavior.

---

## Configuration Over Hardcoding

Store configurable values such as:

* AI model location or identifier
* AI model version
* Credibility weights
* API keys
* Rate limits
* Timeouts
* Similarity thresholds

outside application business logic.

Model-specific assumptions should not be hardcoded throughout the application.

---

## Secure by Default

Every new endpoint assumes:

* Authentication required
* Authorization required
* Validation required

Public endpoints must be explicitly documented.

---

# Architecture Philosophy

The architecture prioritizes:

1. Maintainability
2. Readability
3. Simplicity
4. Testability
5. Extensibility
6. Modularity

Performance optimizations should only be introduced after measurable bottlenecks are identified.

The fine-tuned classification model is intentionally treated as a **replaceable component**, not as the foundation of the application architecture.

InfoTrust should therefore remain operationally and structurally stable when the model is:

* Retrained
* Updated
* Reconfigured
* Replaced with another compatible classifier

provided that the AI Analysis Service continues to satisfy its defined contract.

---

# End of Part 4
# ADR-013 — Containerization Strategy

## Status

Accepted

---

## Impact

Medium

---

## Context

The application should run consistently across:

* Local development
* Testing
* Production

Developers should avoid "works on my machine" issues while keeping the development environment easy to set up.

The backend environment must also provide the dependencies required to run the configured fine-tuned classification model consistently.

---

## Decision

Use Docker for containerization.

Separate containers for:

* Backend (Django + Django Ninja + AI Analysis Service)
* PostgreSQL (local development)
* Redis (optional, reserved for future enhancements)

Use Docker Compose for local development.

Each service should be independently configurable through environment variables.

For Version 1, the AI Analysis Service may remain inside the backend application/container rather than being deployed as a separate microservice.

The configured fine-tuned classification model is accessed through the AI Analysis Service regardless of whether inference runs within the backend process or is separated in a future deployment.

---

## Alternatives Considered

* Native local setup
* Virtual Machines
* Kubernetes
* Dedicated AI inference container for Version 1

---

## Advantages

* Consistent environments
* Easy onboarding
* Simplified deployment
* Better reproducibility
* Production-ready workflow
* Consistent ML dependencies across environments
* Allows future separation of model inference if required

---

## Disadvantages

* Additional learning curve
* Slightly longer initial setup
* Model dependencies may increase backend container size

---

## Why This Decision Was Chosen

Docker provides a professional development workflow while remaining practical for a single-developer academic project.

It also helps ensure that dependencies required by the fine-tuned classification model behave consistently across development and deployment environments.

A separate model-inference container is intentionally not required for Version 1 because that would introduce additional operational complexity without a demonstrated need.

The logical AI Analysis Service boundary is sufficient to preserve model replaceability even when the model runs inside the backend deployment.

Kubernetes is intentionally excluded because it introduces unnecessary operational complexity.

---

## Future Review

If InfoTrust evolves into a production-scale platform, evaluate managed container orchestration solutions such as Kubernetes.

If model inference becomes sufficiently resource-intensive or requires independent scaling, the AI Analysis Service may be moved into a dedicated inference container or service while preserving the existing service contract.

---

# ADR-014 — Deployment Strategy

## Status

Accepted

---

## Impact

Medium

---

## Context

The project requires an inexpensive, reliable, and easy-to-demonstrate deployment solution.

The deployment strategy must also support the resources and dependencies required by the configured fine-tuned classification model.

---

## Decision

Deploy:

### Frontend

* Vercel

### Backend

* Render

### Database

* Neon PostgreSQL

All deployments should be triggered automatically from the GitHub repository.

The fine-tuned classification model remains behind the AI Analysis Service.

For Version 1, model inference should remain within the existing backend deployment when technically feasible.

The model should not be separated into an independent production service unless actual resource or hosting constraints require it.

Model deployment details must remain isolated from:

* Frontend
* Public REST API
* Hybrid Credibility Engine
* Fact-check Service
* Narrative Activity
* Rule Engine
* Authentication
* Claim management

---

## Alternatives Considered

* Railway
* Fly.io
* AWS
* Azure
* Google Cloud Platform
* Dedicated model inference hosting

---

## Advantages

* Free tiers available
* HTTPS by default
* Simple CI/CD workflow
* Easy GitHub integration
* Minimal DevOps overhead
* Suitable for academic demonstration
* AI deployment can evolve independently through the AI Analysis Service abstraction

---

## Disadvantages

* Free-tier limitations
* Backend cold starts
* Limited compute resources
* Fine-tuned model inference may require more memory or CPU than a normal Django application
* Hosting limitations may require model deployment changes if the selected model cannot run efficiently

---

## Why This Decision Was Chosen

The selected platforms provide the best balance between:

* Cost
* Simplicity
* Reliability
* Academic demonstration value

The deployment architecture should remain simple until actual model resource requirements demonstrate the need for additional infrastructure.

If Render can host the backend and configured fine-tuned model within acceptable resource limits, no separate inference service is necessary.

If it cannot, the AI Analysis Service boundary allows the inference implementation to move elsewhere without redesigning the Hybrid Credibility Engine or frontend.

---

## Model Deployment Requirement

The model deployment mechanism must support:

* Loading the configured fine-tuned model
* Loading the correct tokenizer/preprocessing configuration
* Identifying the deployed model version
* Returning standardized predictions
* Graceful inference failure handling
* Replacement with another compatible model

The application should not assume that one particular model artifact will remain permanently deployed.

---

## Future Review

Evaluate managed cloud providers if scalability, uptime, or advanced infrastructure becomes necessary.

Also reconsider the model deployment strategy if:

* Model inference exceeds available memory.
* Inference latency becomes unacceptable.
* Backend startup becomes excessively slow.
* Model artifacts exceed practical deployment limits.
* Independent model scaling becomes necessary.

These conditions may justify deploying the AI Analysis Service separately without changing the overall InfoTrust architecture.

---

# ADR-015 — Configuration Management

## Status

Accepted

---

## Impact

High

---

## Context

Sensitive configuration must never be stored in source code.

Examples include:

* API keys
* JWT secrets
* Database credentials
* AI model configuration
* External service credentials

Model-specific configuration should also remain centralized so that replacing the classification model does not require modifying unrelated application code.

---

## Decision

Store environment-specific configuration in environment variables.

Maintain a version-controlled `.env.example` file documenting every required variable without exposing secrets.

Configuration should include:

* Database settings
* JWT configuration
* AI model location or identifier
* AI model version
* Fact-check API configuration
* Logging configuration
* Rate limits
* Inference-related configuration where required

Example conceptual configuration:

```text id="config-example"
DATABASE_URL=

SECRET_KEY=

MODEL_PATH=

MODEL_VERSION=

FACT_CHECK_API_KEY=

ACCESS_TOKEN_LIFETIME=

REFRESH_TOKEN_LIFETIME=
```

The exact variable names may evolve during implementation, but model-specific configuration must remain centralized.

If the model is stored locally or bundled with the controlled deployment environment, no external model API credential is required.

If model hosting is moved to an authenticated external inference environment in the future, the required credentials must also be supplied securely through environment variables.

---

## Model Configuration Principle

Application business logic must not hardcode:

* Base model name
* Fine-tuned model path
* Model version
* Model storage location
* Model-specific label identifiers
* External inference credentials

Where model-specific mappings are required, they should remain within the AI layer or its model adapter.

This allows:

```text id="model-config-flow"
Configuration
      ↓
AI Analysis Service
      ↓
Model Adapter
      ↓
Configured Model
```

without requiring model information throughout the rest of the application.

---

## Alternatives Considered

* Hardcoded configuration
* Configuration files containing secrets
* Model identifiers scattered throughout application code

---

## Advantages

* Improved security
* Environment-specific configuration
* Easier deployment
* Industry best practice
* Easier model replacement
* Centralized model configuration
* Supports model version tracking

---

## Disadvantages

* Slightly more setup during development
* Incorrect environment configuration can cause model initialization failures

---

## Why This Decision Was Chosen

Environment variables provide a secure and flexible configuration mechanism suitable for development, testing, and production.

Centralizing model configuration also directly supports the architectural requirement that the fine-tuned classification model remain replaceable.

A model replacement should primarily involve changing the relevant configuration and model adapter/integration rather than searching through unrelated application code for hardcoded model references.

---

## Future Review

If configuration grows significantly, evaluate dedicated secret-management services.

A complex model registry or configuration platform should not be introduced in Version 1 unless actual project requirements justify it.

---

# ADR-016 — Logging Strategy

## Status

Accepted

---

## Impact

Medium

---

## Context

Logging is essential for debugging, monitoring, and demonstrating production-quality software engineering practices.

The fine-tuned classification model introduces additional operational events that should be traceable without exposing sensitive data.

---

## Decision

Implement structured application logging.

Log:

* Authentication events
* Analysis requests
* AI processing failures
* Model loading failures
* Model inference failures
* External API failures
* Admin actions
* Validation failures (summary only)
* Unexpected server errors

Model-related logs may include:

* Model identifier
* Model version
* Inference duration
* Inference success/failure status

Never log:

* Passwords
* JWT tokens
* API keys
* Sensitive personal information
* Complete user claims unless required for debugging
* Database credentials
* External service credentials
* Raw model artifacts

Logs should use structured JSON format where practical.

---

## Model Traceability

Where useful for debugging, model-related log entries should make it possible to determine which model version handled an inference request.

Conceptually:

```text id="model-log-example"
event: model_inference
model_version: <configured-version>
status: success
duration_ms: <duration>
```

This is operational metadata.

It should not expose:

* Internal model storage paths
* Credentials
* Sensitive claim content
* Framework-specific internal objects

---

## Alternatives Considered

* Console logging only
* No centralized logging

---

## Advantages

* Easier debugging
* Better operational visibility
* Future monitoring support
* Easier log analysis
* Better model-version traceability
* Easier diagnosis of inference failures

---

## Disadvantages

* Slight increase in implementation effort
* Excessive logging can increase storage requirements if not controlled

---

## Why This Decision Was Chosen

Structured logging improves maintainability while protecting sensitive user information.

Recording the configured model version also becomes useful when the fine-tuned model is retrained or replaced.

If two model versions produce different behavior, logs can help identify which version handled a particular request without coupling application logic to that model.

---

## Future Review

If production usage increases, integrate with centralized logging platforms such as Grafana Loki or the ELK Stack.

Advanced ML observability platforms are outside Version 1 unless a demonstrated need emerges.

---

# ADR-017 — Dependency Management

## Status

Accepted

---

## Impact

Medium

---

## Context

Uncontrolled dependency growth increases maintenance effort, security risks, and application complexity.

The fine-tuned model also introduces machine-learning dependencies required for:

* Model loading
* Tokenization
* Preprocessing
* Inference

These dependencies must remain controlled and reproducible.

---

## Decision

Adopt a minimal dependency philosophy.

Rules:

* Add dependencies only when they solve a genuine problem.
* Prefer actively maintained libraries.
* Prefer widely adopted libraries.
* Remove unused packages promptly.
* Pin dependency versions where appropriate.
* Regularly review dependencies for security vulnerabilities.
* Keep model-specific dependencies isolated to the AI layer where practical.
* Avoid installing multiple ML frameworks unless actually required.
* Ensure the production environment contains only the dependencies required for inference and application operation.

The training environment and production inference environment do not need to contain identical tooling.

Training-only packages should not automatically become production dependencies.

---

## Model Dependency Principle

The model adapter should isolate framework-specific dependencies where practical.

Conceptually:

```text id="dependency-isolation"
Application
     ↓
AI Analysis Service
     ↓
Model Adapter
     ↓
ML Framework
     ↓
Fine-tuned Model
```

If a future replacement model requires different model-specific dependencies, those changes should remain primarily within the AI implementation and deployment environment.

The rest of InfoTrust should not become directly dependent on a specific ML framework.

---

## Alternatives Considered

* Installing libraries whenever convenient
* Maintaining all experimentation dependencies in production
* Direct framework imports throughout application modules

---

## Advantages

* Smaller dependency surface
* Lower security risk
* Easier maintenance
* More reproducible deployments
* Cleaner production environment
* Easier model replacement
* Reduced coupling to specific ML tooling

---

## Disadvantages

* Requires discipline when adding packages.
* Separate training and inference requirements may require additional dependency management.

---

## Why This Decision Was Chosen

InfoTrust is a single-developer final-year project.

Dependency complexity must therefore remain controlled.

Fine-tuning the classification model does not justify turning the production application into a full machine-learning experimentation environment.

The production backend should contain what is necessary to:

* Load the deployed model
* Preprocess input
* Perform inference
* Produce standardized output

Training, experimentation, dataset preparation, and extensive evaluation tooling can remain in the separate training environment, such as Google Colab.

This keeps the deployed application smaller and easier to maintain.

---

## Future Review

Review dependencies periodically and replace abandoned packages with actively maintained alternatives.

Revisit AI dependencies whenever the configured model or inference framework changes.

---

# Infrastructure Principles

The infrastructure should remain:

* Simple
* Secure
* Repeatable
* Low-cost
* Easy to deploy
* Easy to explain during project evaluation
* Capable of supporting the configured fine-tuned model

Operational complexity should only be introduced when supported by clear business or technical requirements.

The existence of a fine-tuned model alone does not justify introducing:

* Kubernetes
* Dedicated ML orchestration
* Complex model registries
* Distributed inference infrastructure
* Multiple inference services

---

# Deployment Philosophy

InfoTrust prioritizes:

1. Reproducible environments
2. Secure configuration
3. Automated GitHub deployments
4. HTTPS by default
5. Minimal operational overhead
6. Easy rollback and recovery
7. Replaceable model deployment
8. Model version traceability

The infrastructure is designed to support a professional demonstration while remaining practical for a single developer.

The deployment architecture must preserve this boundary:

```text id="deployment-boundary"
InfoTrust Application
        ↓
AI Analysis Service
        ↓
Model Adapter
        ↓
Configured Fine-tuned Model
```

The underlying classification model may change without requiring unrelated infrastructure or application components to be redesigned.

---

# End of Part 5
# ADR-018 — Future Expansion Strategy

## Status

Accepted

---

## Impact

Medium

---

## Context

InfoTrust is a final-year project with limited development time.

Many valuable features exist but cannot reasonably be implemented in Version 1 without increasing project risk.

A strategy is required for managing future expansion while protecting the stability of the current system.

Version 1 already includes the InfoTrust-specific fine-tuned misinformation classification model as part of the AI Analysis Service.

Therefore, fine-tuning the classification model is not considered a future feature.

Future model-related work should instead focus on improving, retraining, evaluating, or replacing the existing classification model when justified.

---

## Decision

Version 1 will intentionally remain focused.

Future features should be added only after:

* Existing features are stable.
* Automated tests pass.
* Documentation is updated.
* Database impact is evaluated.
* API compatibility is reviewed.
* AI Analysis Service compatibility is reviewed when the change affects the classification model.

Changes to the underlying classification model should remain isolated behind the AI Analysis Service whenever possible.

---

## Deferred Features

The following features are intentionally outside the scope of Version 1.

### Authentication

* Multi-Factor Authentication (MFA)
* OAuth Login
* Password Reset via Email

### Claims

* URL Analysis
* Image Analysis
* Video Analysis
* Batch Claim Submission

### Analysis Engine

* Additional fact-check providers
* Confidence calibration
* Advanced rule engine
* Source reputation scoring
* Knowledge graph integration
* Ensemble classification
* Multi-model voting

### AI Model Improvements

The following may be considered after Version 1:

* Retraining the InfoTrust classification model with improved datasets
* Evaluating alternative compatible base models
* Replacing the current fine-tuned model if evaluation results are insufficient
* Comparing multiple fine-tuned model versions
* Improved model confidence calibration
* Model optimization for faster inference
* Alternative compatible classification architectures

These are improvements to the existing AI component rather than changes to the fundamental Hybrid Credibility Engine architecture.

### Narrative Activity

* Narrative clustering
* Trend visualization
* Temporal analysis
* Cross-language similarity

### Platform

* Notifications
* Public APIs
* Webhooks
* Export to PDF
* Export to CSV
* Multi-language support

---

## Model Evolution Principle

The fine-tuned classification model is expected to evolve independently from the rest of the application.

A future model change should follow:

```text
New / Retrained Model
        ↓
Model Adapter
        ↓
AI Analysis Service
        ↓
Standardized AI Analysis Result
        ↓
Hybrid Credibility Engine
```

The following should remain unchanged whenever the standardized contract remains compatible:

* Frontend
* Public API
* Authentication
* Claim management
* Fact-check Service
* Narrative Activity
* Rule Engine
* Hybrid Credibility Engine
* Dashboard
* Administrative functionality

---

## Future Review

Review deferred features after Version 1 is stable and the core project requirements have been completed.

Future work should be prioritized according to:

1. User value
2. Academic value
3. Technical feasibility
4. Development effort
5. Impact on existing architecture

Model changes should be driven by measured evaluation or deployment requirements rather than changing models simply because alternatives exist.

---

# ADR-019 — Decision Review Process

## Status

Accepted

---

## Impact

Low

---

## Context

Architectural decisions should not change without proper consideration.

Frequent changes introduce unnecessary instability.

This is particularly important for AI-related decisions because experimentation with models should not automatically cause changes to the overall system architecture.

---

## Decision

Every significant architectural change should answer the following questions.

### 1. Why is the change required?

Identify the business, technical, or academic reason.

---

### 2. What problem does it solve?

The change must address a measurable issue.

For model-related changes, measurable reasons may include:

* Better evaluation performance
* Lower inference latency
* Lower resource usage
* Improved deployment compatibility
* Better confidence calibration

---

### 3. What are the alternatives?

At least one alternative should be considered.

---

### 4. What are the trade-offs?

Evaluate:

* Complexity
* Maintainability
* Performance
* Security
* Scalability

For model changes, also consider:

* Evaluation performance
* Inference requirements
* Model size
* Integration compatibility

---

### 5. Does it align with project goals?

Changes should support:

* Simplicity
* Maintainability
* Educational value
* Professional quality

---

### 6. Is documentation updated?

Whenever a significant decision changes, update:

* PRD.md
* ARCHITECTURE.md
* API_SPEC.md
* TASK.md
* PROJECT_RULES.md
* DECISIONS.md

---

## Model Replacement Review

Replacing or retraining the classification model does not automatically constitute a major architectural change.

If a replacement model:

* Uses the existing AI Analysis Service boundary
* Produces the required standardized output
* Does not change public API contracts
* Does not change Hybrid Credibility Engine behavior
* Does not require changes to unrelated modules

then the change should primarily be treated as an AI implementation/model-version change.

A new ADR should be created when a model change materially affects:

* System architecture
* Public APIs
* Hybrid Credibility Engine contracts
* Deployment architecture
* Persistent data structures
* Major infrastructure requirements

---

# Rejected Architectural Decisions

The following options were considered but intentionally rejected.

---

## Microservices

**Reason**

Too much operational complexity for a single developer.

The AI Analysis Service remains a logical service boundary within the Modular Monolith for Version 1.

**Decision**

Rejected.

---

## GraphQL

**Reason**

REST satisfies current requirements with less complexity.

**Decision**

Rejected.

---

## Repository Pattern

**Reason**

Adds unnecessary abstraction on top of Django ORM.

**Decision**

Rejected.

---

## Event-Driven Architecture

**Reason**

No clear requirement for asynchronous distributed communication.

**Decision**

Rejected.

---

## Kubernetes

**Reason**

Operational complexity significantly outweighs benefits.

The presence of a fine-tuned classification model does not by itself justify container orchestration.

**Decision**

Rejected.

---

## MongoDB

**Reason**

Project data is strongly relational.

**Decision**

Rejected.

---

## Moderator Role

**Reason**

Administrative requirements are simple.

**Decision**

Rejected.

---

## URL and Image Claims in Version 1

**Reason**

Would increase implementation scope and testing effort.

**Decision**

Deferred.

---

## Single-Model Final Verdict

**Reason**

Allowing the classification model to independently determine the final credibility verdict would make the system overly dependent on one prediction and weaken the Hybrid Credibility Engine.

**Decision**

Rejected.

The fine-tuned model remains one signal within the Hybrid Credibility Engine.

---

## Direct Model Integration Across Application Modules

**Reason**

Directly importing or invoking the fine-tuned model throughout the backend would create unnecessary coupling and make future model replacement difficult.

**Decision**

Rejected.

All classification inference should remain behind the AI Analysis Service.

---

## Complex Model Registry for Version 1

**Reason**

A full model-registry platform would introduce unnecessary infrastructure for a single-model final-year project.

Lightweight model identification and version tracking are sufficient for Version 1.

**Decision**

Rejected.

---

# Lessons Learned

The design of InfoTrust is guided by several core lessons.

1. Simple systems are easier to build, explain, and maintain.

2. Architecture should solve today's problems while allowing reasonable future growth.

3. Not every modern technology improves a project. Technology should be adopted only when it provides measurable value.

4. Explainability is as important as prediction. Users should understand why the system reached a conclusion.

5. Modularity is more valuable than unnecessary distribution. A well-structured Modular Monolith is preferable to poorly designed microservices.

6. Security should be built into the design rather than added later.

7. Machine learning models should be treated as replaceable components rather than allowing the entire application to depend on one model implementation.

8. Model quality should be established through evaluation rather than assuming that fine-tuning automatically produces a better classifier.

9. Training infrastructure and production inference infrastructure serve different purposes and should not be unnecessarily coupled.

10. The Hybrid Credibility Engine should remain stable even when the underlying classification model evolves.

---

# Permanent Decision Principles

Every future architectural decision should follow these principles.

## Principle 1

Prefer simplicity over cleverness.

---

## Principle 2

Avoid premature optimization.

---

## Principle 3

Keep modules loosely coupled.

---

## Principle 4

Prefer composition over duplication.

---

## Principle 5

Protect user privacy by default.

---

## Principle 6

Design for maintainability before scalability.

---

## Principle 7

Configuration should replace hardcoded values whenever practical.

---

## Principle 8

Every feature should have a clear purpose.

Features that add complexity without meaningful user or academic value should be rejected.

---

## Principle 9

Treat the classification model as a replaceable implementation detail.

Application architecture must depend on the standardized AI Analysis Service contract rather than a particular:

* Base model
* Fine-tuned model artifact
* Tokenizer
* Model framework
* Model version

---

## Principle 10

Model changes must be evidence-driven.

A model should be retrained, upgraded, or replaced when evaluation or operational evidence justifies the change.

Model novelty alone is not sufficient justification.

---

## Principle 11

Preserve the Hybrid Credibility Engine boundary.

The AI classification model remains one credibility signal.

Changing the model must not silently change:

* Credibility weights
* Fact-check behavior
* Narrative Activity
* Rule Engine behavior
* Final score calculation

Those are separate decisions and must be reviewed independently.

---

# Version History

| Version | Date            | Description                                                                                                                                                                                                       |
| ------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.0.0   | Initial Release | Created architecture decision record document.                                                                                                                                                                    |
| 1.1.0   | July 2026       | Updated AI model decisions to use an InfoTrust-specific fine-tuned misinformation classification model while preserving the Hybrid Credibility Engine and making the classification model explicitly replaceable. |

---

# Document Relationships

This document complements the rest of the project documentation.

| Document         | Purpose                                        |
| ---------------- | ---------------------------------------------- |
| PROJECT_RULES.md | Permanent AI coding rules                      |
| PRD.md           | Defines what the system should build           |
| ARCHITECTURE.md  | Describes how the system is structured         |
| API_SPEC.md      | Defines external interfaces                    |
| TASK.md          | Implementation roadmap                         |
| DECISIONS.md     | Explains why architectural decisions were made |

Together, these documents form the architectural foundation of the InfoTrust project.

Model-related decisions documented here should remain synchronized with:

* PROJECT_RULES.md
* PRD.md
* ARCHITECTURE.md
* API_SPEC.md
* TASK.md

to prevent conflicting assumptions about the classification model.

---

# Final Review Checklist

Before implementation begins, verify that:

* ✓ Major architectural decisions are documented.
* ✓ Technology stack is finalized.
* ✓ Analysis engine strategy is finalized.
* ✓ Fine-tuned classification model strategy is documented.
* ✓ AI Analysis Service abstraction is documented.
* ✓ Model replaceability requirement is documented.
* ✓ Model version/configuration strategy is documented.
* ✓ Hybrid Credibility Engine remains independent of the underlying model implementation.
* ✓ Authentication strategy is finalized.
* ✓ Database choice is finalized.
* ✓ Deployment strategy is finalized.
* ✓ Deferred features are documented.
* ✓ Rejected alternatives are documented.
* ✓ Future review process is established.
* ✓ Model changes can occur without unnecessary changes to unrelated application components.
* ✓ Documentation is synchronized with the current model strategy.

---

# Final Decision Summary

The central AI architecture decision for InfoTrust is:

```text
User Claim
     ↓
AI Analysis Service
     ↓
Model Adapter
     ↓
InfoTrust Fine-tuned Classification Model
     ↓
Standardized AI Prediction + Confidence
     ↓
Hybrid Credibility Engine
```

The fine-tuned model is **not the final credibility authority**.

It supplies the AI Analysis signal to the existing Hybrid Credibility Engine.

The Hybrid Credibility Engine continues to combine:

* Fact-check Evidence — 40%
* AI Analysis — 35%
* Narrative Activity — 15%
* Rule Engine — 10%

These weights are not changed by the decision to fine-tune the model.

The classification model must remain replaceable.

If the model performs poorly, is retrained, uses a different base model, or is replaced with another compatible classifier, the change should remain primarily inside:

* Model configuration
* Model adapter
* Model loading
* Preprocessing/tokenization
* Inference
* Output mapping

The following should not require redesign solely because the model changes:

* Frontend
* Authentication
* Public REST APIs
* Claims
* Fact-check Service
* Narrative Activity
* Rule Engine
* Hybrid Credibility Engine
* Dashboard
* Administration

This separation is a permanent architectural requirement unless a future ADR explicitly changes it.

---

# End of DECISIONS.md

---

# ADR-020 — Final ML Model and Dataset Strategy

## Status

Accepted

## Impact

Medium

## Decision

Use `microsoft/deberta-v3-base` as the final selected base model.

Use cleaned WELFake + FEVER for the final production training workflow with approved binary label alignment, leakage prevention, balanced domain × class sampling, reproducible splits, validation-based checkpoint selection, and isolated held-out testing.

Keep LIAR untouched by production training and use it only as an external generalization evaluation dataset.

Experiments A–D remain preliminary feasibility/model-selection experiments. Their results support the decision but do not represent the final production model.

The final production model has completed training and evaluation; application integration remains a separate implementation task.

## Architectural Impact

This ADR refines the model-development decision only. It does not alter the Hybrid Credibility Engine weights, Fact-check Service, Narrative Activity, Rule Engine, public API contracts, authentication, frontend, database architecture, or other unrelated decisions.

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
