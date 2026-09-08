# InfoTrust

> **Misinformation Detection & Claim Analysis Platform**

InfoTrust is a full-stack web application that helps users evaluate the credibility of textual claims using a **Hybrid Credibility Engine**. Rather than relying on a single source of information, the platform combines multiple credibility signals—including an InfoTrust-specific fine-tuned misinformation classifier, external fact-check data, rule-based validation, and Narrative Activity Detection—to generate a credibility assessment with transparent, evidence-based explanations.

The project is being developed as a **Final-Year B.Tech Project** with a strong emphasis on software engineering best practices, clean architecture, maintainability, security, and real-world usability.

---

# Problem Statement

The rapid spread of misinformation across digital platforms makes it difficult for individuals to verify the credibility of information before sharing or acting upon it.

Existing solutions often:

- Depend on a single verification source or fact-check database.
- Provide limited explanations for their conclusions.
- Lack transparency in how credibility scores are calculated.
- Do not identify recurring misinformation narratives.
- Focus only on prediction rather than explainability.

As a result, users may receive a verdict without understanding **why** it was produced.

---

# Proposed Solution

InfoTrust provides a structured claim analysis workflow.

Users submit a textual claim, which is processed by the **Hybrid Credibility Engine**.

The engine combines evidence from multiple sources to produce:

- A credibility score
- A credibility verdict
- Supporting evidence
- Narrative Activity information
- Explainability Panel

Instead of functioning as a replacement for human judgment, InfoTrust is designed as a **decision-support system** that helps users better understand the credibility of submitted claims through transparent, evidence-based analysis.

---

# Key Features

## User Features

- Secure user authentication
- Submit text-based claims
- Credibility analysis
- Hybrid Credibility Engine
- Explainability Panel
- Narrative Activity Detection
- Claim history
- Personal dashboard
- Helpful / Not Helpful feedback system

---

## Admin Features

- Manage users
- Enable or disable user accounts
- Review submitted claims
- Soft delete inappropriate claims
- View platform analytics
- Monitor overall system activity
- View audit logs

---

# What Makes InfoTrust Different?

Unlike traditional claim verification systems, InfoTrust combines multiple independent evidence sources instead of relying on a single prediction.

Core differentiators include:

### Hybrid Credibility Engine

Combines:

- Fact-check Evidence — 40%
- AI Analysis from the fine-tuned classifier — 35%
- Narrative Activity — 15%
- Rule Engine — 10%

to generate a final credibility assessment.

The classification model provides only the AI Analysis signal. It does not independently determine the final verdict.

---

### Explainability Panel

Every completed analysis includes a transparent explanation showing:

- Final credibility verdict
- Credibility score
- Score breakdown
- Evidence summary
- Explanation based on available evidence

---

### Narrative Activity Detection

The system identifies similar claims previously analyzed within InfoTrust.

Users can view:

- Number of similar claims
- Activity level
- First occurrence
- Latest occurrence

This provides additional context without acting as the sole basis for a credibility decision.

---

# Project Objectives

The primary objectives of InfoTrust are:

- Detect potentially misleading textual claims.
- Improve transparency in credibility assessment.
- Promote evidence-based decision support.
- Apply modern software engineering practices.
- Build a scalable and maintainable full-stack application.
- Create an industry-quality academic project.

---

# Target Users

InfoTrust is intended for:

- Students
- Researchers
- Educators
- Journalists
- General internet users

---

# Current Scope (Version 1)

Included:

- Text claim analysis
- User authentication
- Hybrid Credibility Engine
- Explainability Panel
- Narrative Activity Detection
- User dashboard
- Admin dashboard
- Feedback collection

Not included:

- Image analysis
- URL analysis
- Video analysis
- Browser extensions
- Mobile applications
- Social media integrations

These features are intentionally deferred to future versions.

---

# Project Highlights

- Full-stack web application
- Modular Monolith architecture
- REST API design
- JWT authentication
- PostgreSQL database
- Hybrid Credibility Engine
- InfoTrust-specific fine-tuned misinformation classifier
- Replaceable AI model layer
- Clean Architecture principles
- SOLID design principles
- Docker-ready deployment
- Production-oriented documentation

---

# Screenshots

Project screenshots will be added after the user interface is completed.

Example sections:

- Landing Page
- Login
- Dashboard
- Claim Submission
- Analysis Results
- Explainability Panel
- Narrative Activity
- Admin Dashboard

---

# Live Demo

Coming Soon

---

# Documentation

Comprehensive project documentation is available in the `docs/` directory.

This includes:

- Product Requirements
- System Architecture
- API Specification
- Architecture Decisions
- Development Roadmap
- Coding Rules

Refer to the documentation for detailed technical information.

---

# Project Status

**Current Phase**

Planning & System Design

The project documentation, architecture, and implementation roadmap are being finalized before development begins.

Implementation will follow a milestone-based approach to ensure maintainability, testability, and high software quality.

---

# Version

Current Version:

**v1.0 (Planning Phase)**

---

# End of Part 1
# Features

InfoTrust is designed around three user roles:

- Guest
- Registered User
- Administrator

Each role has a clearly defined set of capabilities.

---

# Guest Features

Guests can explore the platform before creating an account.

### Landing Page

- View project overview
- Learn how InfoTrust works
- Read feature highlights

---

### Authentication

- Register a new account
- Login using email and password

---

# Registered User Features

Registered users have access to the complete claim analysis workflow.

---

## User Dashboard

The dashboard provides a summary of user activity.

Displays:

- Total claims submitted
- Completed analyses
- Pending analyses
- Average credibility score
- Recent claims
- Credibility trend
- Recent activity

---

## Claim Management

Users can:

- Submit text claims
- View claim history
- Search claims
- Filter claims
- Sort claims
- View claim details
- Edit pending claims
- Delete pending claims

---

## Claim Analysis

Analysis is automatically triggered after a valid claim is submitted.

Each completed analysis includes:

- Final verdict
- Credibility score
- Analysis timestamp
- Processing status

---

## Hybrid Credibility Engine

The Hybrid Credibility Engine combines multiple evidence sources to produce a credibility assessment.

Current credibility signals include:

- External Fact-check Evidence — 40%
- AI Analysis from the InfoTrust fine-tuned classifier — 35%
- Narrative Activity Detection — 15%
- Rule Engine — 10%

Each component contributes to the overall credibility assessment. The classification model remains one signal within the engine rather than the final credibility authority.

---

## Explainability Panel

Every completed analysis provides a transparent explanation.

Displays:

- Final verdict
- Credibility score
- Score breakdown
- Evidence summary
- Explanation based on available evidence

The goal is to help users understand **why** a conclusion was reached.

---

## Narrative Activity Detection

The platform identifies similar claims previously analyzed within InfoTrust.

Information displayed includes:

- Number of similar claims
- Highest similarity score
- First occurrence
- Latest occurrence
- Activity level

Narrative Activity provides contextual information and is not treated as standalone proof of misinformation.

---

## Personal Profile

Users can:

- View profile
- Update profile information
- Deactivate account

---

## Feedback System

Users can rate completed analyses as:

- Helpful
- Not Helpful

Collected feedback helps evaluate the usefulness of analysis results and supports future improvements.

---

# Administrator Features

Administrators manage the platform rather than participating in claim analysis.

---

## Admin Dashboard

Displays platform-wide statistics.

Includes:

- Total users
- Active users
- Disabled users
- Total claims
- Completed analyses
- Pending analyses
- Average credibility score
- Verdict distribution

---

## User Management

Administrators can:

- View users
- Search users
- Disable accounts
- Re-enable accounts

Administrators cannot modify user analyses.

---

## Claim Moderation

Administrators can:

- Review submitted claims
- View complete analysis details
- Soft delete inappropriate claims

Deleted claims remain stored for audit purposes.

---

## Platform Analytics

Provides insights into:

- Claim submission trends
- Verdict distribution
- User growth
- Narrative Activity distribution
- Analysis completion statistics

---

## Audit Logs

Administrative actions are recorded for accountability.

Examples:

- User disabled
- User enabled
- Claim deleted
- Administrator login
- Administrator logout

---

# Planned Future Features

The following features are intentionally outside the scope of Version 1.

### Claim Types

- URL analysis
- Image analysis
- Video analysis
- Batch claim submission

---

### Credibility Engine & Model Enhancements

- Source reputation scoring
- Confidence calibration
- Additional evidence providers
- Improved rule engine
- Retraining the InfoTrust classifier with improved datasets
- Evaluating compatible replacement models
- Model inference optimization

---

### Narrative Activity

- Narrative clustering
- Trend visualization
- Temporal analysis
- Cross-language similarity

---

### Platform

- Browser extension
- Mobile application
- Public API
- Webhooks
- PDF export
- CSV export
- Notifications

---

### Internationalization

- Multi-language interface
- Multi-language claim analysis

---

# Feature Summary

| Category | Status |
|----------|--------|
| Authentication | ✅ |
| User Dashboard | ✅ |
| Claim Submission | ✅ |
| Claim Analysis | ✅ |
| Hybrid Credibility Engine | ✅ |
| Explainability Panel | ✅ |
| Narrative Activity Detection | ✅ |
| Feedback System | ✅ |
| Admin Dashboard | ✅ |
| User Management | ✅ |
| Platform Analytics | ✅ |
| Audit Logs | ✅ |
| URL Analysis | 🚧 Future |
| Image Analysis | 🚧 Future |
| Browser Extension | 🚧 Future |
| Mobile App | 🚧 Future |

---

# Design Philosophy

Every implemented feature must satisfy at least one of the following goals:

- Improve credibility assessment
- Increase transparency
- Enhance user experience
- Improve maintainability
- Strengthen security
- Demonstrate sound software engineering practices

Features that increase complexity without delivering meaningful value are intentionally excluded from Version 1.

---

# End of Part 2
# Technology Stack

InfoTrust is built using a modern, production-oriented technology stack chosen for maintainability, scalability, security, and suitability for a misinformation detection and claim analysis platform.

---

# Frontend

| Technology | Purpose |
|------------|---------|
| React | Component-based user interface |
| TypeScript | Static typing and improved maintainability |
| Vite | Fast development server and build tool |
| Tailwind CSS | Utility-first CSS framework |
| React Router | Client-side routing |
| Axios | HTTP client for API communication |

---

# Backend

| Technology | Purpose |
|------------|---------|
| Django | Backend web framework |
| Django Ninja | Type-safe REST API framework |
| Python | Primary backend language |
| JWT | Stateless authentication |

---

# Database

| Technology | Purpose |
|------------|---------|
| PostgreSQL | Primary relational database |

---

# Machine Learning & Hybrid Credibility Engine

InfoTrust v1 uses an InfoTrust-specific fine-tuned transformer-based misinformation classification model.

The model is trained separately in Google Colab and integrated into the application through a dedicated AI Analysis Service and model adapter. The deployed model artifact, tokenizer, identifier, and version remain configurable so the classifier can be retrained or replaced without redesigning unrelated application components.

The Hybrid Credibility Engine combines:

- Fact-check Evidence — 40%
- AI Analysis — 35%
- Narrative Activity — 15%
- Rule Engine — 10%

The engine depends on a standardized AI analysis result rather than a specific model implementation.

---

# Machine Learning

| Technology / Tool | Purpose |
|-------------------|---------|
| Transformer-based classifier | Base architecture for misinformation classification |
| Google Colab | Fine-tuning and evaluation environment |
| Model Adapter | Isolates model-specific loading, preprocessing, inference, and output mapping |
| AI Analysis Service | Provides standardized classification output to the Hybrid Credibility Engine |

The approved base model is `microsoft/deberta-v3-base`; the approved production training datasets are cleaned WELFake + FEVER; LIAR is reserved for external evaluation. The trained artifact version will be documented after the final production training run is completed.

---

# Development Tools

| Tool | Purpose |
|------|---------|
| Git | Version control |
| GitHub | Source code hosting |
| Docker | Containerization |
| Docker Compose | Local development environment |
| Postman / Bruno | API testing |
| VS Code / Antigravity IDE | Development environment |

---

# Deployment

| Component | Platform |
|-----------|----------|
| Frontend | Vercel |
| Backend | Render |
| Database | Neon PostgreSQL |

---

# High-Level Project Structure

```text
InfoTrust/
│
├── backend/
│
├── frontend/
│
├── docs/
│
├── docker/
│
├── .github/
│
├── .env.example
│
├── docker-compose.yml
│
├── README.md
│
└── LICENSE
```

---

# Backend Structure

```text
backend/
│
├── apps/
│   ├── authentication/
│   ├── users/
│   ├── claims/
│   ├── analysis/
│   ├── dashboard/
│   ├── feedback/
│   └── admin_panel/
│
├── core/
│
├── config/
│
├── services/
│
├── api/
│
├── static/
│
├── media/
│
└── manage.py
```

Each module is responsible for its own:

- Models
- Schemas
- Services
- API routes
- Business logic

This follows a **Modular Monolith** architecture.

---

# Frontend Structure

```text
frontend/
│
├── src/
│   ├── components/
│   ├── pages/
│   ├── layouts/
│   ├── hooks/
│   ├── services/
│   ├── contexts/
│   ├── routes/
│   ├── utils/
│   ├── types/
│   ├── assets/
│   └── styles/
│
├── public/
│
└── package.json
```

The frontend follows a feature-oriented component structure with reusable UI components and shared utilities.

---

# Architectural Highlights

InfoTrust follows these architectural principles:

- Modular Monolith
- REST API
- Clean Architecture concepts
- SOLID principles
- Service Layer pattern
- Separation of Concerns
- Configuration over Hardcoding
- Replaceable Model Layer
- Secure by Default

---

# High-Level System Architecture

```text
                  +----------------------+
                  |      React App       |
                  +----------+-----------+
                             |
                             | HTTPS / REST
                             |
                  +----------v-----------+
                  |   Django Ninja API   |
                  +----------+-----------+
                             |
          +------------------+------------------+
          |                  |                  |
          |                  |                  |
+---------v--------+  +-------v--------+  +------v-------+
| Business         |  | Hybrid         |  | PostgreSQL   |
| Services         |  | Credibility    |  | Database     |
|                  |  | Engine         |  |              |
+------------------+  +-------+--------+  +--------------+
                             |
        +----------------+----------------+----------------+
        |                |                |                |
+-------v-------+ +------v-------+ +------v-------+ +------v-------+
| Fact-check    | | AI Analysis  | | Narrative    | | Rule Engine  |
| Evidence      | | Service      | | Activity     | |              |
+---------------+ +------+-------+ +--------------+ +--------------+
                         |
                  +------v-------+
                  | Model Adapter|
                  +------+-------+
                         |
                  +------v-------+
                  | Fine-tuned   |
                  | Classifier   |
                  +--------------+
```

---

# Design Goals

The selected technology stack supports the following goals:

- Maintainability
- Scalability
- Security
- Testability
- Modularity
- Evidence-based credibility assessment
- Ease of deployment
- Professional software engineering practices

---

# Why This Stack?

The chosen stack balances:

- Industry relevance
- Development speed
- Learning outcomes
- Long-term maintainability
- Ease of deployment

It is intentionally designed to remain achievable for a single developer while producing an industry-grade final-year project.

---

# End of Part 3
# Project Architecture

InfoTrust follows a **Modular Monolith** architecture with clear separation of concerns.

The system is divided into independent feature modules while remaining a single deployable application. This approach provides maintainability, simplicity, and scalability without introducing the operational complexity of microservices.

For detailed architectural decisions, refer to **docs/ARCHITECTURE.md**.

---

# High-Level Architecture

```text
                    +-----------------------+
                    |      React Client     |
                    +-----------+-----------+
                                |
                                | HTTPS / REST
                                |
                    +-----------v-----------+
                    |   Django Ninja API    |
                    +-----------+-----------+
                                |
                +---------------+---------------+
                |               |               |
                |               |               |
        +-------v------+ +-------v------+ +------v------+
        | Authentication| | Claim System | | Dashboard  |
        +--------------+ +--------------+ +-------------+
                                |
                                |
                    +-----------v-----------+
                    | Hybrid Credibility    |
                    | Engine                |
                    +-----------+-----------+
                                |
          +----------------+----------------+----------------+
          |                |                |                |
+---------v-------+ +------v-------+ +------v-------+ +------v-------+
| Fact-check      | | AI Analysis  | | Narrative    | | Rule Engine  |
| Evidence        | | Service      | | Activity     | |              |
+-----------------+ +------+-------+ +--------------+ +--------------+
                           |
                    +------v-------+
                    | Model Adapter|
                    +------+-------+
                           |
                    +------v-------+
                    | Fine-tuned   |
                    | Classifier   |
                    +--------------+
                                |
                    +-----------v-----------+
                    | PostgreSQL Database   |
                    +-----------------------+
```

---

# Request Flow

A typical claim analysis follows this sequence:

```text
User
 │
 ▼
Submit Claim
 │
 ▼
API Validation
 │
 ▼
Store Claim
 │
 ▼
Automatically Trigger Analysis
 │
 ▼
Run Analysis Components
 │
 ├──────────────┬──────────────┬──────────────┐
 ▼              ▼              ▼              ▼
Fact-check   AI Analysis    Narrative      Rule
Evidence     Service        Activity       Engine
                │
                ▼
          Model Adapter
                │
                ▼
        Fine-tuned Classifier
 │              │              │              │
 └──────────────┴───────┬──────┴──────────────┘
                        ▼
              Hybrid Credibility Engine
                        │
                        ▼
              Calculate Credibility Score
        │
        ▼
Generate Explainability Panel
        │
        ▼
Store Analysis
        │
        ▼
Return Results to User
```

---

# Hybrid Credibility Engine

The Hybrid Credibility Engine is the core of InfoTrust.

It evaluates claims using multiple independent evidence sources instead of relying on a single source.

Current credibility signals:

- Fact-check Evidence — 40%
- AI Analysis — 35%
- Narrative Activity — 15%
- Rule Engine — 10%

The AI Analysis signal is produced by the InfoTrust-specific fine-tuned misinformation classifier through the AI Analysis Service.

The model remains replaceable behind the model adapter. Retraining or replacing it with another compatible classifier should not require redesign of the Hybrid Credibility Engine, frontend, public API, authentication, claims, fact-check service, Narrative Activity, or Rule Engine.

---

# Explainability Pipeline

Every completed analysis includes a transparent explanation.

```text
Evidence Sources
       │
       ▼
Hybrid Credibility Engine
       │
       ▼
Score Breakdown
       │
       ▼
Evidence Summary
       │
       ▼
Explanation
       │
       ▼
Explainability Panel
```

The Explainability Panel is designed to help users understand the evidence behind the system's verdict rather than simply presenting a credibility score.

---

# Narrative Activity Flow

Narrative Activity identifies previously analyzed claims that are similar to the current submission.

```text
New Claim
    │
    ▼
Generate Similarity Representation
    │
    ▼
Compare with Stored Claims
    │
    ▼
Identify Similar Claims
    │
    ▼
Calculate Activity Metrics
    │
    ▼
Include Results in Analysis
```

Narrative Activity provides contextual information and is **not** treated as standalone proof of misinformation.

---

# Data Flow

```text
User
 │
 ▼
React Frontend
 │
 ▼
REST API
 │
 ▼
Business Services
 │
 ├──────────────┐
 ▼              ▼
Database   Hybrid Credibility Engine
 │              │
 └──────┬───────┘
        ▼
Analysis Results
        │
        ▼
Frontend Dashboard
```

---

# Security Overview

The application follows a secure-by-default philosophy.

Key security measures include:

- JWT Authentication
- Role-Based Access Control (RBAC)
- Password hashing
- Input validation
- Output sanitization
- Environment-based configuration
- HTTPS in production
- Protected API endpoints

---

# Architectural Principles

The project is guided by the following principles:

- Modular design
- Separation of concerns
- SOLID principles
- RESTful APIs
- Configuration over hardcoding
- Fail-fast validation
- Evidence-based credibility assessment
- Simplicity over unnecessary complexity

---

# Scalability Strategy

Although Version 1 is a Modular Monolith, the architecture allows future expansion.

Potential future improvements include:

- Background job processing
- Additional evidence sources
- Improved credibility scoring
- Retrained or compatible replacement classification models
- Additional claim types
- Public APIs

These enhancements can be introduced without major changes to the existing architecture.

---

# Documentation

For additional details, see:

- `docs/ARCHITECTURE.md`
- `docs/API_SPEC.md`
- `docs/DECISIONS.md`

These documents provide a deeper explanation of the system architecture, API design, and architectural decisions.

---

# End of Part 4
# Getting Started

This guide explains how to set up and run InfoTrust in a local development environment.

---

# Prerequisites

Ensure the following software is installed before starting.

| Software | Recommended Version |
|----------|---------------------|
| Git | Latest Stable |
| Python | 3.12+ |
| Node.js | 22 LTS or newer |
| PostgreSQL | 16+ |
| Docker | Latest Stable |
| Docker Compose | Latest Stable |

---

# Clone the Repository

```bash
git clone https://github.com/<your-username>/InfoTrust.git

cd InfoTrust
```

---

# Project Structure

```text
InfoTrust/
│
├── backend/
├── frontend/
├── docs/
├── docker/
├── README.md
├── docker-compose.yml
└── .env.example
```

---

# Environment Variables

Copy the example environment file.

Backend

```bash
cp backend/.env.example backend/.env
```

Frontend

```bash
cp frontend/.env.example frontend/.env
```

Update the required values before running the application.

Example backend variables:

```text
SECRET_KEY=

DEBUG=True

DATABASE_URL=

JWT_SECRET=

MODEL_ARTIFACT_PATH=

MODEL_VERSION=

FACT_CHECK_API_KEY=
```

Example frontend variables:

```text
VITE_API_BASE_URL=

VITE_APP_NAME=InfoTrust
```

**Important:**

- Never commit `.env` files.
- Commit only `.env.example`.
- Store secrets only in environment variables.

---

# Backend Setup

Navigate to the backend directory.

```bash
cd backend
```

Create a virtual environment.

```bash
python -m venv .venv
```

Activate the virtual environment.

Linux/macOS

```bash
source .venv/bin/activate
```

Windows

```bash
.venv\Scripts\activate
```

Install dependencies.

```bash
pip install -r requirements.txt
```

Apply database migrations.

```bash
python manage.py migrate
```

Create an administrator account.

```bash
python manage.py createsuperuser
```

Start the development server.

```bash
python manage.py runserver
```

The backend will be available at:

```text
http://localhost:8000
```

---

# Frontend Setup

Open a new terminal.

Navigate to the frontend directory.

```bash
cd frontend
```

Install dependencies.

```bash
npm install
```

Start the development server.

```bash
npm run dev
```

The frontend will be available at:

```text
http://localhost:5173
```

---

# Docker Setup

InfoTrust supports local development using Docker.

Start all services.

```bash
docker compose up --build
```

Run in detached mode.

```bash
docker compose up -d
```

Stop all services.

```bash
docker compose down
```

---

# Running the Application

After setup:

Frontend

```text
http://localhost:5173
```

Backend API

```text
http://localhost:8000
```

API Documentation

```text
http://localhost:8000/api/docs
```

OpenAPI Specification

```text
http://localhost:8000/api/openapi.json
```

---

# Running Tests

Backend

```bash
python manage.py test
```

Frontend

```bash
npm test
```

Run all tests before opening a pull request or merging changes.

---

# Development Workflow

Recommended implementation order:

1. Project setup
2. Database
3. Authentication
4. Backend APIs
5. Frontend foundation
6. Fine-tune and evaluate the misinformation classifier
7. Integrate the fine-tuned model through the AI Analysis Service
8. Hybrid Credibility Engine
9. Narrative Activity Detection
10. Dashboards
11. Testing
12. Deployment

Refer to `docs/TASK.md` for the detailed milestone plan.

---

# Troubleshooting

## Backend fails to start

Verify:

- Virtual environment is activated.
- Dependencies are installed.
- Database is running.
- Environment variables are configured.

---

## Database connection error

Check:

- PostgreSQL service is running.
- Database credentials are correct.
- `DATABASE_URL` is configured.

---

## Frontend cannot reach backend

Verify:

- Backend server is running.
- `VITE_API_BASE_URL` is correct.
- No firewall or proxy is blocking requests.

---

## Claim analysis fails

Verify:

- Internet connection is available.
- Fact-check API key is valid.
- The configured fine-tuned model artifact is available.
- The tokenizer/model configuration matches the deployed artifact.
- Required environment variables are configured.
- The backend services are running correctly.

---

# Contributing

InfoTrust is currently developed as a single-developer academic project.

External contributions are not accepted during Version 1 development.

Suggestions and feedback are welcome after the initial release.

---

# Next Steps

After successfully running the project:

1. Register a user account.
2. Submit a text claim.
3. Wait for the automatically triggered analysis to complete.
4. Review the Explainability Panel.
5. Explore the Narrative Activity section.
6. Test the user and admin dashboards.

---

# End of Part 5
# Project Documentation

InfoTrust follows a **documentation-first development approach**.

Major architectural, product, API, and implementation decisions are documented before development begins to maintain consistency and improve long-term maintainability.

Project documentation is available in the `docs/` directory.

---

# Documentation Structure

```text
docs/
│
├── PROJECT_RULES.md
├── PRD.md
├── ARCHITECTURE.md
├── API_SPEC.md
├── TASK.md
├── DECISIONS.md
├── PROMPTS.md
└── README.md
```

> The project currently uses exactly these eight Markdown documents. Do not create additional project-level documentation files unless an explicit architectural decision requires one.

---

# Documentation Guide

## PROJECT_RULES.md

Defines the permanent engineering standards and AI-assisted development rules for the project.

Includes:

- Coding standards
- Clean Architecture principles
- SOLID guidelines
- Security rules
- AI-assisted development guidelines
- Development conventions

Read this document before implementing any feature.

---

## PRD.md (Product Requirements Document)

Defines **what** the application should build.

Includes:

- Problem statement
- Project goals
- User roles
- Functional requirements
- Non-functional requirements
- MVP scope
- Future scope
- Success criteria

---

## ARCHITECTURE.md

Explains **how** the system is designed.

Includes:

- High-level architecture
- Module organization
- Hybrid Credibility Engine
- Authentication
- Data flow
- Security
- Deployment architecture
- Architecture diagrams

---

## API_SPEC.md

Defines every public REST API.

Includes:

- Endpoints
- Request schemas
- Response schemas
- Authentication
- Validation
- Error responses
- API conventions
- Versioning

---

## TASK.md

Acts as the implementation roadmap.

Includes:

- Development phases
- Milestones
- Dependencies
- Progress tracking
- Feature checklist
- Completion criteria

---

## DECISIONS.md

Records important architectural decisions.

Includes:

- Technology choices
- Trade-offs
- Alternatives considered
- Accepted decisions
- Rejected approaches
- Future review strategy

---

## PROMPTS.md

Defines reusable prompts for AI-assisted development.

Includes:

- Development prompts
- Backend and frontend prompts
- Model fine-tuning and integration prompts
- Testing and review prompts
- Documentation and release prompts
- AI collaboration rules

---

# Recommended Reading Order

For new contributors or reviewers:

1. README.md
2. PROJECT_RULES.md
3. PRD.md
4. ARCHITECTURE.md
5. DECISIONS.md
6. API_SPEC.md
7. TASK.md
8. PROMPTS.md

This order moves from high-level project understanding to implementation details.

---

# Documentation Principles

All documentation should follow these principles:

- Maintain a single source of truth.
- Keep documentation synchronized with implementation.
- Prefer diagrams where they improve clarity.
- Avoid duplicated information across documents.
- Update documentation whenever architectural or functional changes occur.

---

# Documentation Maintenance

Documentation must be updated whenever any of the following changes occur:

- New feature
- Database schema modification
- API change
- Authentication change
- Hybrid Credibility Engine workflow update
- Classification model training, retraining, integration, or replacement
- Deployment process update
- Architectural decision
- Security enhancement

Documentation updates are considered part of the implementation work and should not be postponed.

---

# Versioning

Documentation versions should align with project releases.

Example:

| Project Version | Documentation Version |
|-----------------|-----------------------|
| v1.0.0 | v1.0.0 |
| v1.1.0 | v1.1.0 |
| v2.0.0 | v2.0.0 |

Major project changes should include corresponding documentation updates.

---

# Documentation Philosophy

InfoTrust adopts a **documentation-first** development approach.

Planning, architecture, and major technical decisions are documented before implementation begins whenever practical.

This approach improves:

- Maintainability
- Collaboration
- Code quality
- Project evaluation
- Long-term scalability

Well-maintained documentation is considered a core project deliverable rather than an optional addition.

---

# End of Part 6
# Development Workflow

InfoTrust follows a structured, milestone-driven development process.

The objective is to produce maintainable, well-tested, and well-documented software while remaining achievable for a single developer.

---

# Development Philosophy

Every feature should follow the same lifecycle:

```text
Plan
   │
   ▼
Design
   │
   ▼
Implement
   │
   ▼
Test
   │
   ▼
Review
   │
   ▼
Document
   │
   ▼
Merge
```

No feature should skip any stage.

---

# Development Order

Implementation follows this order:

1. Project Initialization
2. Folder Structure
3. Environment Setup
4. Database Design
5. Authentication
6. Backend Foundation
7. REST API Development
8. Fine-tuned Model Training & Evaluation
9. AI Analysis Service / Model Integration
10. Hybrid Credibility Engine
11. Narrative Activity Detection
12. Frontend Foundation
13. Individual Pages
14. Dashboard
15. API Integration
16. Validation
17. Error Handling
18. Testing
19. Performance Optimization
20. Security Review
21. Deployment

This order minimizes rework and ensures foundational components are completed before dependent features.

---

# Branching Strategy

Repository structure:

```text
main
```

The `main` branch always contains stable, working code.

New work should be developed in short-lived feature branches.

Example:

```text
feature/authentication

feature/claims

feature/analysis

feature/dashboard

feature/admin

feature/testing
```

After verification, feature branches should be merged into `main`.

---

# Commit Convention

Use clear, descriptive commit messages.

Recommended format:

```text
type(scope): short description
```

Examples:

```text
feat(auth): implement JWT authentication

feat(claims): add claim submission API

feat(analysis): implement Hybrid Credibility Engine

fix(api): validate empty claim submission

docs(readme): update setup instructions

refactor(dashboard): simplify statistics service

test(auth): add login API tests

chore(deps): update backend dependencies
```

Commit types:

- feat
- fix
- docs
- refactor
- test
- chore
- style
- ci

---

# Definition of Done

A task is considered complete only when:

- Requirements are implemented.
- Code builds successfully.
- Tests pass.
- Documentation is updated.
- No critical warnings remain.
- Code follows project standards.
- Feature has been manually verified.

---

# Code Review Checklist

Before merging any feature:

- Business logic is correct.
- Code is readable.
- No duplicated logic.
- Validation is implemented.
- Error handling exists.
- Security has been considered.
- Environment variables are used where required.
- No secrets are committed.
- Documentation is updated.

---

# Testing Workflow

Every completed milestone should include:

- Unit tests (where appropriate)
- API testing
- Manual UI testing
- Regression testing for affected features

Testing is performed continuously rather than postponed until the end of development.

---

# Documentation Workflow

Whenever a significant change is introduced, update the relevant documentation:

- PROJECT_RULES.md
- PRD.md
- ARCHITECTURE.md
- API_SPEC.md
- TASK.md
- DECISIONS.md
- README.md

Documentation should evolve alongside the codebase.

---

# AI-Assisted Development Workflow

InfoTrust is developed using AI-assisted coding tools.

Guidelines:

- AI generates code only after planning is complete.
- Generated code must be reviewed before acceptance.
- Large features should be implemented incrementally.
- Refactoring should occur regularly.
- AI-generated code must follow PROJECT_RULES.md.
- AI must not introduce an LLM into InfoTrust unless the project is explicitly changed.
- AI must preserve the replaceable classification-model boundary and must not silently change Hybrid Credibility Engine weights.

AI is treated as a development assistant rather than an authoritative source.

---

# Dependency Management

When adding a new dependency:

1. Verify that it solves a real problem.
2. Prefer well-maintained libraries.
3. Avoid duplicate functionality.
4. Record major dependencies in the documentation.
5. Remove unused dependencies promptly.

---

# Versioning Strategy

Semantic Versioning (SemVer) will be used.

Format:

```text
MAJOR.MINOR.PATCH
```

Examples:

```text
v1.0.0
```

Initial release.

```text
v1.1.0
```

New feature added without breaking compatibility.

```text
v1.1.1
```

Bug fixes only.

```text
v2.0.0
```

Breaking changes.

---

# Issue Tracking

Development tasks should be tracked using GitHub Issues or the project task list.

Each issue should include:

- Description
- Priority
- Dependencies
- Acceptance criteria
- Current status

---

# Milestone Reviews

At the end of each milestone, verify:

- Objectives completed
- Tests passed
- Documentation updated
- No blocking issues remain
- Next milestone identified

This ensures steady progress and reduces technical debt.

---

# Development Principles

The project follows these principles:

- Simplicity over unnecessary complexity
- Maintainability over cleverness
- Readability over brevity
- Security by default
- Documentation-first development
- Modular design
- Continuous testing
- Incremental delivery

---

# End of Part 7
# Roadmap

The following roadmap outlines the planned evolution of InfoTrust beyond Version 1.

---

## Version 1.0 (Current Goal)

Core platform functionality.

Features:

- User authentication
- Text claim submission
- InfoTrust-specific fine-tuned misinformation classifier
- Replaceable AI model layer
- Hybrid Credibility Engine
- Explainability Panel
- Narrative Activity
- User dashboard
- Admin dashboard
- Feedback system
- REST API
- Docker support

---

## Version 1.1

Quality improvements.

Potential additions:

- Improved UI and user experience
- Enhanced dashboard analytics
- Performance optimization
- Expanded test coverage
- Improved logging and monitoring

---

## Version 2.0

Platform expansion.

Potential additions:

- URL claim analysis
- Image claim analysis
- Retrained or compatible replacement misinformation classification models
- Export reports (PDF/CSV)
- Background job processing
- Multi-language support

---

## Future Vision

Possible long-term enhancements:

- Browser extension
- Mobile application
- Public API
- Organization accounts
- Advanced narrative trend analysis
- Real-time monitoring dashboards

These features are intentionally outside the scope of the current final-year project.

---

# License

This project is licensed under the **MIT License**.

See the `LICENSE` file for the complete license text.

---

# Third-Party Services

InfoTrust integrates with external services where appropriate.

Examples include:

- External Fact-check API
- Deployment platforms

Each service is used according to its respective terms of service.

---

# Acknowledgements

This project builds upon the work of the open-source community.

Special thanks to the maintainers of:

- React
- TypeScript
- Vite
- Tailwind CSS
- Django
- Django Ninja
- PostgreSQL
- Docker
- Hugging Face Transformers ecosystem

Their tools make this project possible.

---

# Academic Context

InfoTrust is developed as a **Final-Year B.Tech Project**.

Primary objectives include:

- Applying software engineering principles
- Building a production-oriented web application
- Exploring machine learning-assisted misinformation detection
- Demonstrating clean architecture and maintainable design

The project emphasizes engineering quality, transparency, and evidence-based claim analysis rather than implementing every possible feature.

---

# Repository Standards

The repository follows these standards:

- Documentation-first development
- Modular architecture
- Version-controlled database migrations
- Environment-based configuration
- Consistent coding conventions
- REST API design
- Security best practices

---

# Support

For questions, suggestions, or feedback:

- Open a GitHub Issue
- Review the project documentation in the `docs/` directory

---

# Project Status

**Current Status**

🟡 Development & Integration

Architecture, requirements, and the final ML training/evaluation workflow are complete. Application implementation and integration are now proceeding incrementally according to the milestones defined in `docs/TASK.md`.

---

# Repository Checklist

Before each release, verify:

- Documentation is up to date.
- All tests pass.
- Database migrations are committed.
- Environment variables are documented.
- API changes are reflected in `API_SPEC.md`.
- Architecture changes are reflected in `ARCHITECTURE.md`.
- README.md is updated.
- Version number is incremented appropriately.

---

# Contact

**Developer**

Harshpreet Singh

GitHub:

https://github.com/<your-username>

LinkedIn:

https://www.linkedin.com/in/<your-profile>

Replace the placeholder links with your actual profiles before publishing the repository.

---

# README Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0 | Initial | Initial project overview and repository documentation. |
| 1.1 | July 2026 | Aligned README with the InfoTrust-specific fine-tuned misinformation classifier, Google Colab training workflow, automatic analysis triggering, non-LLM architecture, and replaceable model-layer requirement. |

---

# Final Notes

InfoTrust is designed to demonstrate that modern misinformation detection systems can be built with transparency, modularity, and maintainability.

The platform combines multiple evidence sources—including a machine learning classifier, external fact-check data, rule-based validation, and narrative activity detection—to help users evaluate the credibility of textual claims.

InfoTrust is **not** intended to replace professional fact-checking or human judgment. Instead, it serves as a decision-support platform that presents evidence and explanations to support informed decision-making.

---

# Repository Summary

| Category | Details |
|----------|---------|
| Project | InfoTrust |
| Type | Full-Stack Web Application |
| Domain | Misinformation Detection & Claim Analysis |
| Architecture | Modular Monolith |
| Frontend | React + TypeScript |
| Backend | Django + Django Ninja |
| Database | PostgreSQL |
| Authentication | JWT |
| ML Strategy | InfoTrust-specific fine-tuned misinformation classifier |
| Model Architecture | Replaceable behind AI Analysis Service + Model Adapter |
| Analysis Strategy | Hybrid Credibility Engine |
| Primary Goal | Transparent and evidence-based claim analysis |
| Documentation | Documentation-first |
| License | MIT |

---

# End of README.md

---

## ML Status Clarification

The approved base model and datasets are no longer undecided. InfoTrust will use `microsoft/deberta-v3-base` with cleaned WELFake + FEVER for the final production fine-tuning workflow, while LIAR remains external-evaluation-only.

Any earlier README wording that treats the base model or dataset as still awaiting selection is superseded by the Final ML / Dataset Decision section below. The final trained artifact/version is still pending because production training has not yet been performed.

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
