# PRD.md

> **Project:** InfoTrust
> **Version:** 1.1
> **Document Type:** Product Requirements Document (PRD)
> **Status:** Draft v1.1
> **Owner:** Product Management
> **Project Type:** Final Year B.Tech Project
> **Last Updated:** July 2026

---

# Table of Contents

1. Document Information
2. Executive Summary
3. Product Vision
4. Problem Statement
5. Existing Problems
6. Proposed Solution
7. Project Goals
8. Success Criteria

> **Note:** This document is maintained incrementally. Additional sections (Target Users, Functional Requirements, User Stories, Technical Requirements, etc.) will be added in subsequent parts.

---

# 1. Document Information

## Purpose

This Product Requirements Document (PRD) defines the vision, objectives, scope, and functional requirements of **InfoTrust**.

It serves as the primary reference for:

* Product planning
* Software architecture
* Feature prioritization
* Development roadmap
* AI-assisted implementation
* Testing
* Final-year project documentation

The PRD ensures that all implementation decisions remain aligned with the project's objectives while keeping the project scope controlled throughout development.

---

## Intended Audience

This document is intended for:

* Project Developer
* AI Coding Assistant (Antigravity CLI / Gemini CLI)
* Project Supervisor
* University Examiners
* Future Contributors

---

## Project Information

| Field             | Value                                            |
| ----------------- | ------------------------------------------------ |
| Project Name      | InfoTrust                                        |
| Project Type      | AI-Powered Claim Credibility Assessment Platform |
| Development Model | Solo Development                                 |
| Methodology       | Incremental / Milestone-Based Development        |
| Architecture      | Modular Monolith with Clean Architecture         |
| Deployment Target | Cloud                                            |
| Primary Platform  | Web Application                                  |

---

# 2. Executive Summary

## Overview

The rapid spread of misinformation across digital platforms has made it increasingly difficult for individuals to distinguish credible information from misleading or false claims.

Many users lack access to simple tools that provide transparent and explainable credibility assessments. Existing solutions often focus solely on binary fact-checking, rely entirely on AI predictions, or require users to manually search multiple sources, making the verification process time-consuming and inaccessible.

**InfoTrust** is an AI-powered web application designed to assist users in evaluating the credibility of textual claims through a **Hybrid Credibility Engine**.

Rather than depending on a single AI prediction, InfoTrust combines multiple independent credibility signals, including:

* AI-based claim classification using an InfoTrust-specific fine-tuned classification model
* External fact-check results from trusted fact-check providers
* Narrative Activity detection for identifying recurring or similar claims
* Rule-based heuristic analysis

These independent signals are processed by the **Hybrid Credibility Engine**, which generates:

* Credibility Score
* Credibility Category
* Confidence Level
* Explainable reasoning

The AI component is implemented as an **AI Analysis Service**, which uses an **InfoTrust-specific fine-tuned misinformation classification model** to classify submitted claims and produce an AI confidence score.

The target production model will be fine-tuned from the selected `microsoft/deberta-v3-base` base model using the approved cleaned WELFake + FEVER production training strategy. The final production model has completed training and evaluation; application integration remains a separate implementation task. Model training and experimentation may be performed separately using **Google Colab**.

The AI model is **not considered the final authority**. Its prediction represents only one credibility signal within the overall verification process.

The underlying AI model must remain **replaceable**. Retraining, upgrading, or replacing the model must not require changes to the Hybrid Credibility Engine or unrelated application components.

The platform emphasizes **transparency** through an Explainability Panel that clearly communicates how each verification module contributed to the final credibility assessment instead of presenting an opaque AI decision.

Additionally, the **Narrative Activity** feature identifies repeated or semantically similar claims submitted over time, enabling users to recognize recurring misinformation patterns and emerging narratives.

InfoTrust is designed as a professional, scalable, and modular web application that demonstrates modern software engineering practices while remaining achievable within the scope of a final-year B.Tech project.

---

## Product Vision Statement

> **Empower people to make informed decisions by providing transparent, explainable, and AI-assisted credibility assessment for textual claims through a hybrid verification approach.**

---

## Value Proposition

InfoTrust enables users to:

* Quickly evaluate textual claims.
* Understand how the final credibility assessment was produced.
* View AI-generated credibility analysis.
* Access supporting information from trusted fact-check sources.
* Identify recurring misinformation narratives.
* Track previously analyzed claims through a personal history dashboard.

Unlike many black-box AI systems, InfoTrust prioritizes transparency, explainability, and user trust by combining multiple credibility signals instead of relying solely on AI.

---

# 3. Product Vision

## Vision

To build a trustworthy AI-powered platform that helps users critically evaluate information by combining AI-assisted claim classification, external fact-check data, rule-based analysis, narrative detection, and explainable reasoning into a single, easy-to-use system.

Rather than determining whether a claim is absolutely true or false, InfoTrust aims to provide users with a transparent credibility assessment supported by multiple independent verification signals.

---

## Long-Term Vision

While the initial release focuses on textual claims, the architecture is intentionally designed to support future expansion, including:

* URL analysis
* Image-based misinformation detection
* Multiple fact-check providers
* Support for improved or alternative compatible AI classification models
* Multilingual support
* Browser extensions
* Public API access

These features are considered future enhancements and are outside the scope of the initial MVP.

---

## Design Principles

Every product decision should support one or more of the following principles.

### Transparency

Users should clearly understand why the system produced a particular credibility assessment.

The platform should avoid black-box AI decisions and instead explain how different verification modules contributed to the final result.

---

### Simplicity

The platform should remain intuitive and easy to use, even for non-technical users.

Users should be able to submit a claim and understand the resulting credibility assessment without requiring technical knowledge.

---

### Reliability

Results should combine multiple independent credibility signals rather than relying solely on an AI prediction.

The Hybrid Credibility Engine should ensure that no single verification module determines the final credibility assessment.

---

### Maintainability

The software should follow Clean Architecture principles with modular services that are easy to maintain, extend, and replace.

Individual components—such as the AI Analysis Service—should be replaceable without requiring changes to the rest of the application.

The underlying classification model must remain replaceable behind a stable AI Analysis Service interface.

---

### Scalability

The architecture should support future feature additions and increased user demand without requiring significant redesign.

---

# 4. Problem Statement

## Background

The internet has dramatically increased the speed at which information spreads.

Unfortunately, misinformation spreads just as quickly as accurate information, making it increasingly difficult for individuals to determine whether the information they encounter is trustworthy.

Users regularly encounter claims on:

* Social media platforms
* Messaging applications
* Blogs
* News websites
* Online discussion forums

These claims may be:

* False
* Misleading
* Presented without sufficient evidence
* Taken out of context
* Difficult to verify quickly

Verifying such claims manually often requires users to search multiple sources, compare conflicting information, and evaluate the credibility of different publishers.

This process is time-consuming, inconsistent, and often inaccessible to everyday users.

---

## Core Problem

There is currently no simple platform that combines:

* AI-assisted claim classification
* External fact-check information
* Narrative Activity detection
* Rule-based analysis
* Explainable credibility assessment

into a single user-friendly workflow.

Existing solutions typically focus on only one aspect of verification while neglecting transparency, contextual analysis, or explainability.

---

## Why This Problem Matters

Misinformation can contribute to:

* Public confusion
* Poor decision-making
* Reduced trust in reliable information
* Amplification of misleading narratives

Providing users with accessible credibility assessment tools can support more informed decision-making while remaining transparent about the limitations of AI-assisted analysis.

InfoTrust is designed to assist users—not replace their judgment.

---

# 5. Existing Problems

Current approaches to credibility verification face several limitations.

## Problem 1 — Manual Verification

Users often need to:

* Search multiple websites.
* Compare conflicting sources.
* Evaluate source credibility manually.

This process requires significant effort and time.

---

## Problem 2 — Black-Box AI

Many AI systems provide predictions without explaining how those predictions were generated.

This reduces user trust and makes it difficult for users to evaluate the reliability of the results.

---

## Problem 3 — Limited Context

Traditional fact-checking systems often evaluate claims independently.

They rarely identify recurring claims or misinformation narratives that appear repeatedly over time.

---

## Problem 4 — Fragmented Verification

Users frequently switch between:

* Search engines
* Fact-check websites
* AI assistants
* News articles

to build an overall understanding of a claim.

There is little integration between these verification methods.

---

## Problem 5 — Lack of Explainability

Many existing tools do not clearly communicate:

* Why a credibility assessment was produced.
* Which verification modules influenced the result.
* How confident the system is.
* Whether external fact-check evidence was available.

---

## Problem 6 — Poor User Experience

Many verification platforms are designed primarily for journalists or researchers rather than everyday users.

As a result, they can be difficult to navigate and understand.

---

# 6. Proposed Solution

## Overview

InfoTrust addresses these challenges by providing a unified platform that combines AI-assisted claim classification, external fact-check information, narrative analysis, and rule-based heuristics into a single verification workflow.

Instead of relying on a single AI prediction or external source, the platform aggregates multiple independent credibility signals through the **Hybrid Credibility Engine**.

This approach improves transparency, explainability, and overall reliability.

---

## Core Workflow

1. User submits a textual claim.
2. The system validates and preprocesses the input.
3. The claim is analyzed by:

   * AI Analysis Service
   * Fact-check Service
   * Rule Engine
   * Narrative Engine
4. Each service produces an independent credibility signal.
5. The Hybrid Credibility Engine combines these signals.
6. A final credibility score, credibility category, and confidence level are generated.
7. The Explainability Panel summarizes how each module contributed to the assessment.
8. Narrative Activity identifies previously submitted similar claims.
9. External fact-check information is displayed when available.
10. The completed analysis is stored in the user's history.

---

## Key Differentiators

InfoTrust distinguishes itself through:

* Hybrid Credibility Engine
* AI-assisted claim classification using an InfoTrust-specific fine-tuned model
* Explainable credibility assessments
* Narrative Activity detection
* Integration with trusted fact-check providers
* User-friendly dashboards
* Modular architecture
* Replaceable AI model integration
* Clean and scalable software design

---

# 7. Project Goals

## Primary Goals

### Goal 1

Provide users with an intuitive platform for evaluating textual claims.

---

### Goal 2

Increase user trust by combining AI predictions with external verification and explainable reasoning.

---

### Goal 3

Combine multiple independent credibility signals instead of relying on a single AI model or external source.

---

### Goal 4

Identify recurring or semantically similar misinformation narratives through Narrative Activity detection.

---

### Goal 5

Maintain a searchable history of previously analyzed claims for authenticated users.

---

### Goal 6

Provide administrators with tools to manage users, review submitted claims, and monitor platform activity.

---

### Goal 7

Demonstrate industry-standard software engineering practices suitable for a final-year B.Tech project.

---

### Goal 8

Fine-tune and integrate an InfoTrust-specific misinformation classification model while keeping the underlying model replaceable without affecting the rest of the application.

---

## Secondary Goals

* Clean Architecture
* Modular codebase
* RESTful APIs
* Secure authentication
* Responsive user interface
* Scalable system design
* Professional documentation
* Cloud deployment

---

# 8. Success Criteria

The project will be considered successful if it satisfies the following criteria.

## Functional Success

* Users can register and log in securely.
* Users can submit textual claims.
* Claims receive AI-assisted credibility analysis.
* The Hybrid Credibility Engine generates credibility scores.
* The Explainability Panel clearly explains the assessment.
* Narrative Activity identifies similar historical claims.
* External fact-check information is displayed when available.
* Claim history is maintained for registered users.
* Administrators can manage users and submitted claims.

---

## Technical Success

* Modular architecture.
* RESTful API design.
* Secure authentication.
* PostgreSQL database.
* Responsive frontend.
* Cloud deployment.
* Environment-variable-based configuration.
* AI integration through a dedicated AI Analysis Service.
* The fine-tuned InfoTrust model is integrated through a stable service interface.
* The underlying AI model can be replaced without requiring changes to the Hybrid Credibility Engine or unrelated application components.

---

## Academic Success

The project should demonstrate:

* AI model fine-tuning
* AI model evaluation
* AI integration
* Database design
* Web development
* Authentication
* REST API development
* Clean software architecture
* Hybrid credibility assessment
* Testing strategy
* Security considerations
* Professional documentation

---

## User Experience Success

Users should be able to:

* Submit a claim in under one minute.
* Understand the resulting credibility assessment without technical knowledge.
* Navigate the platform intuitively.
* Receive meaningful credibility assessments even when external fact-check data is unavailable through AI analysis, rule-based heuristics, and Narrative Activity.

---

## Future Readiness

The architecture should support future enhancements without requiring major redesign, including:

* URL analysis
* Image analysis
* Multilingual support
* Improved or alternative compatible AI models
* Advanced analytics
* Public APIs
* Browser extensions

---

**End of Part 1**

# 9. Target Users

## Primary Target Users

The primary audience for InfoTrust consists of individuals who want a quick, transparent, and explainable way to evaluate the credibility of textual claims.

The platform is designed to **assist users in making informed decisions** through AI-assisted credibility assessment and external verification. It is intended for educational and informational purposes and does not replace professional fact-checking organizations or human judgment.

---

## User Categories

### 1. General Internet Users

People who frequently encounter claims on:

* Social Media
* Messaging Apps
* Blogs
* Online Forums
* News Websites

These users want a quick and transparent credibility assessment before believing or sharing information.

---

### 2. Students

Students researching assignments or current affairs who need an easy way to evaluate online information.

Typical goals:

* Verify claims
* Understand how credibility assessments are generated
* Learn how misinformation spreads
* Explore supporting fact-check information
* Improve information literacy

---

### 3. Researchers *(Future)*

Researchers may use the platform to observe recurring misinformation narratives and claim trends.

Although the MVP is not research-focused, the Narrative Activity feature provides a strong foundation for future analytical capabilities.

---

### 4. Administrators

Administrators are responsible for maintaining the platform.

Responsibilities include:

* Managing users
* Reviewing submitted claims
* Removing inappropriate content
* Monitoring platform analytics
* Maintaining overall system quality

Administrators manage the platform but do **not** manually determine credibility assessments.

---

# 10. User Personas

## Persona 1 — Curious Student

### Name

Aman

### Age

21

### Occupation

B.Tech Student

### Goals

* Verify information found online.
* Understand how the platform evaluates claim credibility.
* Complete academic work using reliable information.

### Pain Points

* Difficulty identifying trustworthy sources.
* Conflicting information online.
* Time-consuming manual verification.

### How InfoTrust Helps

* Simple claim submission.
* AI-assisted credibility assessment.
* Explainability Panel.
* Fact-check references.
* Narrative Activity detection.

---

## Persona 2 — Everyday Internet User

### Name

Priya

### Age

28

### Occupation

Software Professional

### Goals

* Quickly evaluate claims received through messaging applications.
* Avoid sharing misleading information.

### Pain Points

* Limited time.
* Uncertainty about information credibility.

### How InfoTrust Helps

* Fast credibility assessment.
* AI-assisted claim classification.
* Clear credibility score.
* Easy-to-understand explanation.

---

## Persona 3 — Administrator

### Name

System Administrator

### Goals

* Maintain platform quality.
* Prevent misuse.
* Review inappropriate submissions.
* Monitor platform activity.

### Pain Points

* Spam submissions.
* Fake accounts.
* Platform abuse.

### How InfoTrust Helps

* Admin Dashboard.
* User management.
* Claim moderation.
* Analytics.
* Activity logs.

---

# 11. User Roles

InfoTrust supports three user roles.

## 1. Guest

A visitor who has not created an account.

Purpose:

Allow users to explore the platform before registration.

Guests have read-only access to public pages and cannot submit claims.

---

## 2. Registered User

An authenticated user with a private account.

Registered users can:

* Submit claims
* View credibility assessments
* Access their claim history
* Manage their profile
* Provide feedback

---

## 3. Administrator

Responsible for platform management.

Administrators have elevated permissions to manage users, moderate claims, and monitor platform activity.

---

# 12. Permission Matrix

| Feature                               | Guest | Registered User | Admin |
| ------------------------------------- | :---: | :-------------: | :---: |
| View Landing Page                     |   ✅   |        ✅        |   ✅   |
| Register                              |   ✅   |        ❌        |   ❌   |
| Login                                 |   ✅   |        ✅        |   ✅   |
| Logout                                |   ❌   |        ✅        |   ✅   |
| Submit Claim                          |   ❌   |        ✅        |   ✅   |
| View Own Claim History                |   ❌   |        ✅        |   ✅   |
| View Claim Details                    |   ❌   |   ✅ (Own Only)  |   ✅   |
| View Explainability Panel             |   ❌   |        ✅        |   ✅   |
| View Narrative Activity               |   ❌   |        ✅        |   ✅   |
| Give Feedback (Helpful / Not Helpful) |   ❌   |        ✅        |   ✅   |
| Update Profile                        |   ❌   |        ✅        |   ✅   |
| Change Password                       |   ❌   |        ✅        |   ✅   |
| Delete Own Account *(Future)*         |   ❌   |        ❌        |   ❌   |
| Access Admin Dashboard                |   ❌   |        ❌        |   ✅   |
| View All Users                        |   ❌   |        ❌        |   ✅   |
| Disable User Accounts                 |   ❌   |        ❌        |   ✅   |
| Review Submitted Claims               |   ❌   |        ❌        |   ✅   |
| Delete Inappropriate Claims           |   ❌   |        ❌        |   ✅   |
| View Platform Analytics               |   ❌   |        ❌        |   ✅   |

---

## Permission Principles

InfoTrust follows the **Principle of Least Privilege**.

Users receive only the permissions required for their role.

Examples:

* Registered users cannot view other users' claims.
* Guests cannot submit claims.
* Only administrators can disable accounts.
* Only administrators can access platform analytics.

---

# 13. Authentication Strategy

## Authentication Method

The MVP supports:

* Email
* Password

Social authentication providers are intentionally excluded from the initial release.

---

## Authorization

Authorization is role-based.

Supported roles:

* Guest
* User
* Administrator

Permissions are enforced on the backend.

Frontend route protection exists only to improve user experience and must never replace backend authorization.

---

## Session Management

Authentication uses JWT (JSON Web Tokens).

Features include:

* Access Token
* Refresh Token
* Secure logout
* Protected API endpoints
* Token-based authentication for REST APIs

---

# 14. User Objectives

## Guest

### Primary Objective

Understand the purpose of InfoTrust and decide whether to create an account.

### Expected Actions

* Visit the landing page.
* Learn about the platform.
* Register.
* Login.

---

## Registered User

### Primary Objective

Evaluate the credibility of textual claims.

### Expected Actions

* Login.
* Submit a claim.
* Receive a credibility assessment.
* Review the Explainability Panel.
* Explore Narrative Activity.
* Access previous analyses.
* Provide feedback.

---

## Administrator

### Primary Objective

Maintain platform quality and ensure reliable operation.

### Expected Actions

* Login.
* Review analytics.
* Monitor claim submissions.
* Disable abusive accounts.
* Remove inappropriate claims.
* Review system activity.

---

# 15. User Needs

The product must satisfy the following user needs.

## Guests Need

* A clear explanation of the platform.
* A simple registration process.
* Confidence before creating an account.

---

## Registered Users Need

* Fast claim submission.
* Transparent credibility assessment.
* Reliable AI-assisted analysis.
* Easy navigation.
* Personal claim history.
* Privacy of submitted claims.
* Explainable results.

---

## Administrators Need

* Efficient moderation tools.
* Platform analytics.
* User management capabilities.
* Reliable audit logs.
* Monitoring tools.

---

# 16. Privacy Expectations

InfoTrust is designed with privacy as a core principle.

### Registered Users

* Claims remain private.
* Users can view only their own submissions.
* Personal information is protected.

---

### Administrators

Administrators may review submitted claims only for moderation, quality assurance, and platform maintenance.

Administrative actions should be logged for accountability.

---

### AI Processing

Claims are processed by the InfoTrust AI Analysis Service using the configured fine-tuned classification model.

If model inference is hosted through an external service in the final deployment architecture, only the information required to perform the analysis should be transmitted.

Claims may also be securely transmitted to external fact-check services where required.

No unnecessary personal information should ever be shared with third-party services.

---

# 17. Accessibility Goals

The platform should remain accessible to a broad range of users.

Minimum accessibility requirements include:

* Keyboard navigation
* Screen reader compatibility
* Responsive design
* High color contrast
* Clear typography
* Meaningful form labels
* Visible focus indicators

Accessibility is treated as a core quality attribute throughout the design and development process rather than an optional enhancement.

---

# End of Part 2

# 18. Functional Requirements

## Overview

Functional requirements define the capabilities that InfoTrust must provide.

Each requirement is assigned a unique identifier for traceability during development, testing, and future maintenance.

---

# Authentication Module

## FR-001 — User Registration

**Priority:** High

### Description

The system shall allow new users to register using:

* Full Name
* Email Address
* Password

### Requirements

* Email must be unique.
* Password must satisfy security requirements.
* Password must be securely hashed before storage.
* Every new account shall be assigned the **User** role.

### Acceptance Criteria

* Registration succeeds with valid data.
* Duplicate email addresses are rejected.
* Passwords are never stored in plain text.

---

## FR-002 — User Login

**Priority:** High

### Description

Users shall authenticate using email and password.

### Acceptance Criteria

* Valid credentials generate JWT access and refresh tokens.
* Invalid credentials return appropriate error messages.

---

## FR-003 — Logout

**Priority:** High

The system shall securely log users out by removing authentication tokens from the client.

---

## FR-004 — Profile Management

**Priority:** Medium

Users shall be able to:

* View profile
* Update profile information
* Change password

---

# Claim Management

## FR-005 — Submit Claim

**Priority:** High

Users shall submit textual claims.

### Requirements

* Claim cannot be empty.
* Character limit enforced.
* Input validated.
* Claim stored before analysis begins.

### Acceptance Criteria

* Claim successfully stored.
* AI Analysis Service is triggered.

---

## FR-006 — Claim History

**Priority:** High

Users shall access a private history of previously analyzed claims.

History displays:

* Claim
* Credibility Category
* Credibility Score
* Submission Date

---

## FR-007 — Claim Details

**Priority:** High

Selecting a claim opens a detailed analysis page.

The page displays:

* Original Claim
* Credibility Score
* Credibility Category
* Explainability Panel
* Narrative Activity
* Fact-check Results
* Analysis Timestamp

---

## FR-008 — Search Claim History

**Priority:** Medium

Users shall search previous analyses using keywords.

---

## FR-009 — Pagination

**Priority:** Medium

Claim history shall support pagination.

---

# Hybrid Credibility Engine

## FR-010 — AI Analysis Service

**Priority:** High

Each submitted claim shall be analyzed using the AI Analysis Service.

The AI Analysis Service uses the **InfoTrust-specific fine-tuned misinformation classification model** to generate:

* AI Prediction
* Confidence Score

The AI prediction is treated as one credibility signal and is not considered the final decision.

The underlying model must remain replaceable behind the AI Analysis Service. Retraining, upgrading, or replacing the model must not require changes to the Hybrid Credibility Engine or unrelated application components.

---

## FR-011 — Fact-check Service

**Priority:** High

The system shall query external fact-check providers.

Results should include:

* Matching fact-check results
* Source information
* Publisher
* Review date (when available)

If no matching fact-check exists, analysis shall continue normally.

---

## FR-012 — Narrative Activity

**Priority:** High

The system shall identify similar historical claims.

Display:

* Number of similar claims
* First occurrence
* Latest occurrence
* Narrative activity level

Similarity percentages may be included in future versions.

---

## FR-013 — Rule Engine

**Priority:** Medium

The system shall apply deterministic rules that contribute to the overall credibility assessment.

Examples include:

* Extremely short claims
* Excessive capitalization
* Sensational wording
* Duplicate punctuation
* Unsupported factual statements

---

## FR-014 — Hybrid Credibility Engine

**Priority:** High

The Hybrid Credibility Engine shall combine:

* AI Prediction
* AI Confidence Score
* Fact-check Results
* Narrative Activity
* Rule-based Analysis

to generate:

* Final Credibility Score
* Credibility Category
* Overall Confidence Level

No individual module may determine the final credibility assessment independently.

The Hybrid Credibility Engine must depend only on the standardized output of the AI Analysis Service and must not contain model-specific implementation logic.

---

## FR-015 — Credibility Category

**Priority:** High

The system shall classify the final result into one of the following categories:

* Likely Credible
* Likely Misinformation
* Uncertain

The categories should remain intentionally simple and easy for users to understand.

---

## FR-016 — Explainability Panel

**Priority:** High

The system shall clearly explain how the credibility assessment was produced.

Display:

* AI prediction
* AI confidence
* Fact-check summary
* Narrative Activity summary
* Rule-based observations
* Final credibility score
* Credibility category

Users should understand the assessment without requiring technical knowledge.

---

# Feedback Module

## FR-017 — Feedback

**Priority:** Medium

Users may mark an analysis as:

* Helpful
* Not Helpful

Feedback shall be stored for future evaluation and product improvement.

---

# Dashboard

## FR-018 — User Dashboard

**Priority:** High

Display:

* Total Claims
* Recent Analyses
* Average Credibility Score
* Credibility Trend
* Feedback Statistics

---

## FR-019 — Admin Dashboard

**Priority:** High

Display:

* Total Users
* Total Claims
* AI Requests
* Credibility Category Distribution
* Recent Platform Activity

---

# Administration

## FR-020 — User Management

**Priority:** High

Administrators shall:

* View users
* Disable accounts

---

## FR-021 — Claim Review

**Priority:** High

Administrators shall review submitted claims for moderation purposes.

---

## FR-022 — Claim Deletion

**Priority:** High

Administrators may remove inappropriate claims.

Deletion events shall be logged.

---

## FR-023 — Analytics

**Priority:** Medium

Administrators shall access platform statistics and usage analytics.

---

# Security

## FR-024 — Authentication

Protected endpoints require valid JWT authentication.

---

## FR-025 — Authorization

Users shall access only their own claims.

Administrators may access all submitted claims.

---

## FR-026 — Audit Logging

Administrative actions shall be logged.

Examples:

* User disabled
* Claim deleted

---

# Error Handling

## FR-027 — Graceful Failure

Failures from the AI Analysis Service or external fact-check services shall not crash the application.

Meaningful fallback messages should be displayed.

If AI model inference is temporarily unavailable, the system must report the AI signal as unavailable rather than generating or fabricating a prediction.

---

## FR-028 — Validation

The system shall validate all user input.

Validation occurs on:

* Frontend
* Backend
* Database

---

# General

## FR-029 — Responsive UI

The application shall function on:

* Desktop
* Tablet
* Mobile

---

## FR-030 — Dark Mode

The application shall support dark mode.

---

# 19. Non-Functional Requirements

Non-functional requirements describe how the system should behave.

---

## NFR-001 — Performance

The system should remain responsive.

Typical page navigation should complete within approximately **2 seconds** under normal conditions.

AI analysis may require additional time depending on model inference and external fact-check services, but users should always receive clear loading feedback.

---

## NFR-002 — Availability

The application should remain available whenever hosting infrastructure and required services are operational.

Temporary failures of external services should degrade gracefully rather than preventing the platform from functioning.

---

## NFR-003 — Scalability

The architecture shall support future enhancements including:

* Image analysis
* URL analysis
* Improved or alternative compatible AI models
* Browser extension
* Public API

---

## NFR-004 — Maintainability

The project shall follow:

* Clean Architecture
* SOLID Principles
* Modular Design
* Feature-based organization

New developers should be able to understand the project with minimal onboarding.

The AI model integration must remain isolated behind the AI Analysis Service so that the underlying model can be replaced without requiring changes to unrelated application components.

---

## NFR-005 — Security

The system shall:

* Hash passwords
* Use JWT authentication
* Validate all inputs
* Protect administrative routes
* Store secrets using environment variables
* Prevent unauthorized access

---

## NFR-006 — Reliability

Failures from the AI Analysis Service or external fact-check services shall not cause application failure.

Fallback responses should be provided whenever possible.

---

## NFR-007 — Usability

Users should be able to submit a claim and understand the resulting credibility assessment without prior training.

The interface should prioritize clarity over feature density.

---

## NFR-008 — Accessibility

The application should support:

* Keyboard navigation
* Semantic HTML
* Visible focus indicators
* Adequate color contrast
* Responsive layouts

---

## NFR-009 — Compatibility

The MVP should support the latest versions of:

* Google Chrome
* Microsoft Edge
* Mozilla Firefox

Mobile browsers should also provide a usable experience.

---

## NFR-010 — Privacy

User claims remain private.

Only:

* Claim Owner
* Administrator

may access submitted claims.

Claims shall never be publicly exposed.

---

## NFR-011 — Documentation

The project shall include:

* Product Requirements Document
* Architecture Documentation
* API Specification
* Development Tasks
* README
* Architecture Decision Records

Documentation shall remain synchronized with implementation.

---

## NFR-012 — Deployability

The application shall support deployment using containerization and cloud hosting with environment-based configuration.

The deployment architecture must support inference using the configured InfoTrust fine-tuned model without coupling the wider application to a specific model-hosting approach.

---

## NFR-013 — AI Model Replaceability

The underlying AI classification model shall remain replaceable.

Changing the model must not require architectural changes to:

* Hybrid Credibility Engine
* Fact-check Service
* Narrative Engine
* Rule Engine
* Frontend
* Claim management
* Database logic
* Public API contracts

Model-specific responsibilities such as model loading, tokenization, inference, label mapping, and output interpretation must remain isolated behind the AI Analysis Service.

---

# End of Part 3

# 20. Complete Feature List

The following table lists all planned features for InfoTrust and categorizes them based on implementation priority.

| Feature                        | Priority | MVP | Future |
| ------------------------------ | :------: | :-: | :----: |
| User Registration              |   High   |  ✅  |        |
| User Login                     |   High   |  ✅  |        |
| JWT Authentication             |   High   |  ✅  |        |
| Profile Management             |  Medium  |  ✅  |        |
| Submit Text Claim              |   High   |  ✅  |        |
| Claim History                  |   High   |  ✅  |        |
| Claim Details                  |   High   |  ✅  |        |
| Search Claim History           |  Medium  |  ✅  |        |
| Pagination                     |  Medium  |  ✅  |        |
| Hybrid Credibility Engine      |   High   |  ✅  |        |
| AI Analysis Service            |   High   |  ✅  |        |
| InfoTrust Fine-tuned AI Model  |   High   |  ✅  |        |
| Fact-check Integration         |   High   |  ✅  |        |
| Narrative Activity             |   High   |  ✅  |        |
| Rule Engine                    |  Medium  |  ✅  |        |
| Explainability Panel           |   High   |  ✅  |        |
| Credibility Score              |   High   |  ✅  |        |
| Credibility Category           |   High   |  ✅  |        |
| Helpful / Not Helpful Feedback |  Medium  |  ✅  |        |
| User Dashboard                 |   High   |  ✅  |        |
| Admin Dashboard                |   High   |  ✅  |        |
| User Management                |   High   |  ✅  |        |
| Disable Accounts               |   High   |  ✅  |        |
| Claim Review                   |   High   |  ✅  |        |
| Delete Claims                  |   High   |  ✅  |        |
| Analytics                      |  Medium  |  ✅  |        |
| Audit Logs                     |  Medium  |  ✅  |        |
| Responsive Design              |   High   |  ✅  |        |
| Dark Mode                      |  Medium  |  ✅  |        |
| URL Analysis                   |    Low   |     |    ✅   |
| Image Analysis                 |    Low   |     |    ✅   |
| Browser Extension              |    Low   |     |    ✅   |
| Public API                     |    Low   |     |    ✅   |
| Multi-language Support         |    Low   |     |    ✅   |
| Email Notifications            |    Low   |     |    ✅   |

---

# 21. MVP (Minimum Viable Product)

## Definition

The MVP represents the smallest complete version of InfoTrust that delivers meaningful value to users while remaining achievable within the project timeline.

The MVP must be fully functional, well-tested, and deployable.

---

## MVP Objectives

The MVP should enable a registered user to:

1. Register an account.
2. Log in securely.
3. Submit a textual claim.
4. Receive an AI-assisted credibility assessment.
5. View a credibility score.
6. Understand the credibility assessment through the Explainability Panel.
7. See similar claims via Narrative Activity.
8. View available fact-check results.
9. Access their personal claim history.
10. Provide feedback on the analysis.

Administrators should be able to:

* Manage users.
* Disable accounts.
* Review submitted claims.
* Delete inappropriate claims.
* Monitor platform analytics.

---

## MVP Feature List

### Authentication

* Register
* Login
* Logout
* JWT Authentication

---

### User Features

* Dashboard
* Profile
* Submit Claim
* Claim History
* Claim Details
* Search
* Feedback

---

### AI Features

* InfoTrust Fine-tuned AI Model
* AI Analysis Service
* Fact-check Integration
* Rule Engine
* Narrative Activity
* Hybrid Credibility Engine
* Explainability Panel
* Credibility Score
* Credibility Category

---

### Administration

* Admin Dashboard
* User Management
* Claim Review
* Claim Deletion
* Analytics

---

### Technical

* Responsive UI
* Dark Mode
* REST API
* PostgreSQL
* Docker Support
* Cloud Deployment

---

# 22. Advanced Features (Post-MVP)

These features are intentionally excluded from the initial release to keep the project achievable within the available timeline.

---

## URL Analysis

Analyze textual claims extracted from URLs.

Reason for exclusion:

Requires webpage content extraction, cleaning, and additional preprocessing.

---

## Image Analysis

Analyze misinformation contained within images.

Reason for exclusion:

Requires OCR, image preprocessing, and multimodal AI models, significantly increasing implementation complexity.

---

## Browser Extension

Allow users to analyze claims directly while browsing.

Reason for exclusion:

Requires browser-specific APIs and additional maintenance.

---

## Public REST API

Allow third-party systems to integrate with InfoTrust.

Reason for exclusion:

Introduces API versioning, authentication, rate limiting, documentation, and additional security considerations.

---

## Multi-language Support

Support credibility assessment in multiple languages.

Reason for exclusion:

Requires multilingual AI models and localization.

---

## Email Notifications

Notify users when analyses complete or account-related events occur.

Reason for exclusion:

Not essential to the primary verification workflow.

---

## Advanced AI Model Enhancements

Future improvements may include:

* Retraining the InfoTrust model using improved datasets
* Evaluating alternative compatible base models
* Confidence calibration
* Additional model evaluation and optimization
* Multilingual model support

These enhancements should preserve the stable AI Analysis Service contract.

---

# 23. Stretch Goals

Stretch goals are optional enhancements that may be be implemented only after the MVP is fully completed.

---

## Stretch Goal 1 — Confidence Visualization

Provide graphical visualization of confidence levels using gauges, progress bars, or similar indicators.

Business Value:

Improves readability.

Complexity:

Low.

---

## Stretch Goal 2 — Improved Explainability

Provide richer explanations summarizing:

* AI prediction
* Fact-check findings
* Narrative Activity
* Rule-based observations

Business Value:

Improves transparency and user trust.

Complexity:

Medium.

---

## Stretch Goal 3 — Advanced Dashboard Charts

Add visualizations such as:

* Credibility category trends
* Claim activity over time
* Most common misinformation topics

Business Value:

Provides better insights.

Complexity:

Medium.

---

## Stretch Goal 4 — Search Filters

Allow filtering claim history by:

* Credibility Category
* Date
* Credibility Score

Business Value:

Improves usability.

Complexity:

Low.

---

## Stretch Goal 5 — Export Analysis

Allow users to export analyses as PDF.

Business Value:

Useful for reports, presentations, and academic work.

Complexity:

Medium.

---

## Stretch Goal 6 — Enhanced Explainability

Display the weighted contribution of each credibility signal:

* AI Analysis
* Fact-check Results
* Narrative Activity
* Rule Engine

Business Value:

Improves transparency of the Hybrid Credibility Engine.

Complexity:

Medium.

---

## Stretch Goal 7 — AI Model Comparison

Compare outputs from compatible misinformation classification models during experimentation and evaluation.

Business Value:

Provides valuable research and evaluation capabilities.

Complexity:

High.

---

# 24. Feature Prioritization

The following prioritization strategy will guide development.

## Must Have

These features are essential for successful project completion.

* Authentication
* Claim Submission
* InfoTrust Fine-tuned AI Model
* AI Analysis Service
* Hybrid Credibility Engine
* Explainability Panel
* Narrative Activity
* User Dashboard
* Admin Dashboard

Failure to implement any of these features significantly reduces the project's value.

---

## Should Have

Important but not essential.

* Search
* Pagination
* Feedback
* Analytics
* Dark Mode

These improve usability but are not critical to the primary workflow.

---

## Could Have

Implemented only if sufficient time remains.

* Export to PDF
* Advanced Dashboard Charts
* Search Filters
* Enhanced Explainability

---

## Won't Have (MVP)

The following features are intentionally excluded from the MVP:

* Image Analysis
* URL Analysis
* Browser Extension
* Public API
* Multi-language Support
* Email Notifications

These features add considerable complexity without proportionate academic value for the initial release.

---

# 25. Scope Control

To ensure timely project completion, the following principles will be followed throughout development.

## Rule 1

No new major features will be added until the MVP is fully completed.

---

## Rule 2

Every proposed feature must answer:

* Does it directly improve credibility assessment?
* Does it improve the user experience?
* Is it feasible within the remaining project timeline?

If the answer to any question is **No**, the feature will be deferred.

---

## Rule 3

Prioritize stability and quality over feature quantity.

A reliable, well-tested MVP is preferred over a feature-rich but unstable application.

---

# End of Part 4

# 26. User Stories

User Stories describe the product from the perspective of the end user.

Format:

> As a <role>, I want <goal>, so that <benefit>.

---

## Guest User Stories

### US-001

As a guest, I want to understand what InfoTrust does so that I can decide whether it is useful.

---

### US-002

As a guest, I want to create an account so that I can submit claims for credibility assessment.

---

### US-003

As a guest, I want to log in securely so that I can access my personal dashboard.

---

## Registered User Stories

### US-004

As a registered user, I want to submit a textual claim so that I can evaluate its credibility.

---

### US-005

As a user, I want to receive a credibility score so that I can quickly understand the likely reliability of a claim.

---

### US-006

As a user, I want to understand how the credibility assessment was generated so that I can trust the system's analysis.

---

### US-007

As a user, I want to see supporting fact-check information so that I can verify the assessment independently.

---

### US-008

As a user, I want to know whether similar claims have appeared before so that I can identify recurring misinformation narratives.

---

### US-009

As a user, I want to review my previous analyses so that I can revisit earlier submissions.

---

### US-010

As a user, I want to search my claim history so that I can quickly find previous analyses.

---

### US-011

As a user, I want to update my profile so that my account information remains accurate.

---

### US-012

As a user, I want to provide feedback on an analysis so that future improvements can be made.

---

## Administrator User Stories

### US-013

As an administrator, I want to view platform analytics so that I can monitor system usage.

---

### US-014

As an administrator, I want to review submitted claims so that inappropriate content can be removed.

---

### US-015

As an administrator, I want to disable abusive user accounts so that the platform remains safe.

---

### US-016

As an administrator, I want to delete inappropriate claims so that platform quality is maintained.

---

# 27. User Journey

## Guest Journey

```text
Landing Page
      ↓
Learn about InfoTrust
      ↓
Register
      ↓
Verify Account (Future)
      ↓
Login
      ↓
User Dashboard
```

---

## Registered User Journey

```text
Login
      ↓
Dashboard
      ↓
Submit Claim
      ↓
AI Analysis Service
      ↓
Fact-check Service
      ↓
Narrative Activity
      ↓
Rule Engine
      ↓
Hybrid Credibility Engine
      ↓
Credibility Assessment Generated
      ↓
View Analysis
      ↓
Review Explainability Panel
      ↓
Provide Feedback
      ↓
Analysis Saved in History
```

---

## Returning User Journey

```text
Login
      ↓
Dashboard
      ↓
Open Claim History
      ↓
Search Previous Claims
      ↓
Open Claim Details
      ↓
Review Previous Analysis
```

---

## Administrator Journey

```text
Login
      ↓
Admin Dashboard
      ↓
View Analytics
      ↓
Review Claims
      ↓
Manage Users
      ↓
Disable Account (if necessary)
      ↓
Delete Inappropriate Claims (if required)
      ↓
Logout
```

---

# 28. Navigation Flow

## Guest Navigation

```text
Landing Page
    │
    ├── Login
    │
    └── Register
```

---

## Registered User Navigation

```text
Dashboard
    │
    ├── Submit Claim
    │
    ├── Claim History
    │
    ├── Claim Details
    │
    ├── Profile
    │
    └── Logout
```

---

## Admin Navigation

```text
Admin Dashboard
    │
    ├── User Management
    │
    ├── Claim Management
    │
    ├── Analytics
    │
    ├── Profile
    │
    └── Logout
```

---

# 29. Information Architecture

## Public Area

* Landing Page
* Login
* Register

---

## User Area

Dashboard

↓

Claims

* Submit Claim
* Claim History
* Claim Details

↓

Profile

↓

Settings

---

## Admin Area

Dashboard

↓

User Management

↓

Claim Management

↓

Analytics

↓

Profile

---

# 30. Screen Inventory

The following screens constitute the MVP.

---

## Public Screens

### Landing Page

**Purpose**

Introduce InfoTrust.

**Components**

* Hero Section
* Features
* Workflow
* Call to Action
* Login Button
* Register Button
* Footer

**Priority**

High

---

### Login Page

**Purpose**

Authenticate users.

**Components**

* Email
* Password
* Login Button
* Validation Messages

**Priority**

High

---

### Register Page

**Purpose**

Create a new account.

**Components**

* Full Name
* Email
* Password
* Confirm Password

**Priority**

High

---

## User Screens

### Dashboard

**Purpose**

Provide an overview of user activity.

**Components**

* Total Claims
* Recent Analyses
* Average Credibility Score
* Credibility Trend
* Quick Actions

**Priority**

High

---

### Submit Claim

**Purpose**

Allow users to submit textual claims.

**Components**

* Text Area
* Character Counter
* Submit Button
* Validation Messages

**Priority**

High

---

### Analysis Result

**Purpose**

Display the complete credibility assessment.

**Components**

* Original Claim
* Credibility Category
* Credibility Score
* AI Prediction
* AI Confidence
* Explainability Panel
* Narrative Activity
* Fact-check Results
* Feedback Buttons

**Priority**

High

---

### Claim History

**Purpose**

Display previous analyses.

**Components**

* Search
* Pagination
* Claim Cards
* Filters *(Future)*

**Priority**

High

---

### Profile

**Purpose**

Allow users to manage account information.

**Components**

* Personal Information
* Change Password
* Save Button

**Priority**

Medium

---

## Admin Screens

### Admin Dashboard

**Purpose**

Provide an overview of platform activity.

**Components**

* User Count
* Claim Count
* Credibility Category Distribution
* AI Requests
* Recent Activity

**Priority**

High

---

### User Management

**Purpose**

Manage registered users.

**Components**

* User Table
* Search
* Disable Account
* Status Indicators

**Priority**

High

---

### Claim Management

**Purpose**

Review submitted claims.

**Components**

* Claim Table
* Delete Claim
* Search
* Filters *(Future)*

**Priority**

High

---

### Analytics

**Purpose**

Display platform statistics.

**Components**

* Charts
* Usage Metrics
* AI Requests
* Credibility Category Trends

**Priority**

Medium

---

# 31. Primary User Flow

The primary success flow for the application is:

```text
Register
      ↓
Login
      ↓
Dashboard
      ↓
Submit Claim
      ↓
AI Analysis Service
      ↓
Fact-check Service
      ↓
Narrative Activity
      ↓
Rule Engine
      ↓
Hybrid Credibility Engine
      ↓
Credibility Assessment Generated
      ↓
Explainability Panel
      ↓
Feedback
      ↓
Saved to Claim History
```

---

# 32. Future User Flows

The architecture should support future workflows such as:

* Analyze URL
* Analyze Image
* Compare Multiple Claims
* Export Analysis
* Browser Extension
* Public API Integration

These workflows are intentionally excluded from the MVP.

---

# End of Part 5

# 33. Project Scope

## In Scope (MVP)

The following capabilities are included in the initial release of InfoTrust.

### User Management

* User Registration
* User Login
* JWT Authentication
* Logout
* Profile Management

---

### Claim Analysis

* Submit Text Claims
* InfoTrust Fine-tuned AI Model
* AI Analysis Service
* Hybrid Credibility Engine
* Credibility Score
* Credibility Category Generation
* Explainability Panel
* Narrative Activity
* Fact-check Integration

---

### User Features

* Dashboard
* Claim History
* Claim Details
* Search History
* Helpful / Not Helpful Feedback

---

### Administration

* Admin Dashboard
* User Management
* Disable Accounts
* Claim Review
* Delete Claims
* Platform Analytics

---

### Technical

* Responsive Web Application
* REST API
* PostgreSQL Database
* Secure Authentication
* Docker Support
* Cloud Deployment
* Environment Variable Configuration

---

# 34. Out of Scope

The following features are intentionally excluded from the MVP.

## Media Analysis

* Image Analysis
* Video Analysis
* Audio Analysis

**Reason**

Requires multimodal AI models and significantly increases project complexity.

---

## URL Analysis

**Reason**

Requires webpage content extraction, preprocessing, and additional verification logic.

Planned as a future enhancement.

---

## Browser Extension

**Reason**

Independent browser extension development is outside the current project scope.

---

## Mobile Application

**Reason**

The project focuses exclusively on a responsive web application.

---

## Public API

**Reason**

Third-party integrations are unnecessary for the MVP.

---

## Multi-language Support

**Reason**

English-only support is sufficient for demonstrating the core system.

---

## Email Notifications

**Reason**

Not essential to the primary user workflow.

---

## Social Login

Examples:

* Google
* GitHub
* Microsoft

**Reason**

Email and password authentication is sufficient for the MVP.

---

## Real-time Notifications

**Reason**

No immediate value for the initial release.

---

## Training a Foundation Model From Scratch

**Reason**

InfoTrust fine-tunes an existing pretrained base model for its misinformation classification task.

Developing and training a new foundational model architecture from scratch would require substantially greater datasets, computational resources, experimentation, and development time and is outside the scope of the project.

---

# 35. Assumptions

The following assumptions are made during planning and development.

---

## Technical Assumptions

* Internet connectivity is available.
* Required ML libraries and the trained model artifact remain available.
* External fact-check services remain accessible.
* Cloud hosting services remain available.
* PostgreSQL is available.

---

## User Assumptions

Users:

* Can create an account.
* Can submit textual claims.
* Understand basic web navigation.

---

## Development Assumptions

* Single developer.
* Limited development timeline.
* Open-source technologies.
* Free or educational API tiers.
* Google Colab is available for model fine-tuning and experimentation.
* Incremental development.

---

## Academic Assumptions

The project should demonstrate:

* AI model fine-tuning
* AI model evaluation
* AI Integration
* Database Design
* REST API Development
* Authentication
* Modern Frontend Development
* Backend Development
* Software Engineering Best Practices

---

# 36. Constraints

## Time Constraint

Development should be completed within the available final-year project timeline.

---

## Budget Constraint

The project should rely primarily on:

* Free software
* Open-source libraries
* Free cloud services
* Free API tiers where practical

Paid services should remain optional rather than required.

---

## Team Constraint

The project is developed by a single individual.

Solutions should prioritize maintainability, modularity, and simplicity over unnecessary architectural complexity.

---

## Technical Constraint

The MVP supports:

* Text claims only.

Additional input types are intentionally deferred.

---

## AI Constraint

The selected fine-tuned model must remain practical to train, evaluate, and deploy within the computational resources available to the project.

The production application must access the model through the AI Analysis Service rather than coupling other application components directly to the model implementation.

External fact-check service availability, latency, and result coverage remain outside the project's control.

---

## Infrastructure Constraint

Hosting should remain within free-tier resource limits whenever practical.

---

# 37. Risks

## Risk 1 — AI Model Training or Integration Issues

**Impact**

High

**Mitigation**

Maintain reproducible training and evaluation procedures.

Keep the model isolated behind the AI Analysis Service so that a different compatible model can replace it without redesigning the rest of InfoTrust.

---

## Risk 2 — Fact-check Service Limitations

**Impact**

Medium

**Mitigation**

Continue credibility assessment even when external fact-check information is unavailable.

---

## Risk 3 — API Rate Limits

**Impact**

Medium

**Mitigation**

Optimize requests and implement caching where appropriate.

---

## Risk 4 — Timeline Overrun

**Impact**

High

**Mitigation**

Strictly prioritize MVP functionality before advanced enhancements.

Avoid unnecessary model experimentation once an acceptable model has been selected.

---

## Risk 5 — Scope Creep

**Impact**

High

**Mitigation**

No major features may be added until the MVP is fully completed.

---

## Risk 6 — Incorrect AI Classification

**Impact**

Medium

**Mitigation**

Present results as AI-assisted credibility assessments rather than definitive factual judgments.

Combine AI predictions with fact-check information, Narrative Activity, and rule-based analysis through the Hybrid Credibility Engine.

---

## Risk 7 — Security Vulnerabilities

**Impact**

High

**Mitigation**

Follow secure authentication practices, validate all user input, protect administrative endpoints, and store secrets using environment variables.

---

## Risk 8 — Performance Issues

**Impact**

Medium

**Mitigation**

Use pagination, database indexing, efficient API design, and asynchronous processing where appropriate.

Optimize model loading and inference where necessary.

---

# 38. Future Scope

The following enhancements may be be considered after successful completion of the MVP.

## AI Enhancements

* Retraining the InfoTrust model using improved datasets
* Alternative compatible classification models
* AI Model Comparison
* Confidence Calibration
* Improved Explainability

---

## Input Types

* URL Analysis
* Image Analysis
* PDF Analysis

---

## Platform Expansion

* Browser Extension
* Public API
* Mobile Application

---

## User Experience

* Saved Collections
* Advanced Search Filters
* Export Analysis (PDF)
* Advanced Dashboard Visualizations

---

## Internationalization

* Multi-language Interface
* Multilingual Claim Analysis

---

## Advanced Analytics

* Narrative Trend Analysis
* Misinformation Categories
* User Behavior Insights

---

# 39. Acceptance Criteria

The project will be considered complete when all of the following conditions are satisfied.

## Functional

* Users can register and authenticate.
* Users can submit textual claims.
* Claims receive AI-assisted credibility assessment.
* Credibility scores are generated.
* Credibility categories are generated.
* Explainability Panel is available.
* Narrative Activity identifies similar claims.
* Fact-check information is displayed when available.
* Claim history functions correctly.
* Feedback can be submitted.
* Administrators can manage users and claims.

---

## AI Model

* An InfoTrust-specific misinformation classification model has been successfully fine-tuned.
* The selected model has been evaluated using appropriate classification metrics.
* The trained model can generate predictions and confidence scores for submitted claims.
* The model is integrated through the AI Analysis Service.
* Model-specific implementation remains isolated from the Hybrid Credibility Engine.
* The underlying model can be replaced without requiring architectural changes to unrelated application components.

---

## Technical

* REST APIs implemented.
* PostgreSQL integrated.
* JWT Authentication implemented.
* Responsive UI completed.
* Secure deployment completed.
* Environment variables configured.
* Docker support available.

---

## Quality

* No critical bugs.
* Consistent UI.
* Proper error handling.
* Input validation.
* Documentation completed.
* Code follows the defined project architecture.

---

## Academic

The project demonstrates:

* AI Model Fine-tuning
* AI Model Evaluation
* AI Integration
* Full-Stack Development
* Database Design
* Authentication
* REST API Development
* Software Engineering Principles
* Testing Strategy
* Professional Documentation

---

# 40. Glossary

| Term                          | Definition                                                                                                                                                                        |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Claim                         | A textual statement submitted by a user for credibility assessment.                                                                                                               |
| Credibility Score             | Numerical assessment generated by the Hybrid Credibility Engine indicating the likely reliability of a claim.                                                                     |
| Credibility Category          | Final classification presented to the user (Likely Credible, Likely Misinformation, Uncertain).                                                                                   |
| AI Analysis Service           | Service that uses the currently configured InfoTrust fine-tuned classification model to classify submitted claims and generate an AI confidence score through a stable interface. |
| InfoTrust Fine-tuned AI Model | Misinformation classification model fine-tuned for InfoTrust from a suitable pretrained base model using selected misinformation/claim-classification dataset(s).                 |
| Base Model                    | Pretrained model used as the starting point for fine-tuning the InfoTrust classification model.                                                                                   |
| Explainability Panel          | Interface explaining how the Hybrid Credibility Engine produced the final credibility assessment.                                                                                 |
| Narrative Activity            | Detection of similar historical claims to identify recurring narratives.                                                                                                          |
| Fact-check Results            | Information retrieved from trusted external fact-check providers that contributes to credibility assessment.                                                                      |
| Rule Engine                   | Component that applies deterministic heuristics to strengthen credibility assessment.                                                                                             |
| Hybrid Credibility Engine     | Core service that combines AI prediction, fact-check results, Narrative Activity, and rule-based analysis into a single credibility assessment.                                   |
| JWT                           | JSON Web Token used for secure authentication and authorization.                                                                                                                  |
| MVP                           | Minimum Viable Product containing the essential features required for the initial release.                                                                                        |
| Administrator                 | User role responsible for managing users, reviewing claims, and monitoring the platform.                                                                                          |
| Registered User               | Authenticated user who can submit claims and access personal analyses.                                                                                                            |
| Guest                         | Unauthenticated visitor with access only to public pages.                                                                                                                         |

---

# Document Revision History

| Version | Date      | Changes                                                                                                                                                                                                                                                                     |
| ------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.0     | July 2026 | Initial Product Requirements Document created and aligned with the finalized Hybrid Credibility Engine architecture using a pretrained Hugging Face misinformation classification model.                                                                                    |
| 1.1     | July 2026 | Replaced the pretrained-model MVP strategy with an InfoTrust-specific fine-tuned classification model; moved model fine-tuning into MVP scope; added model evaluation and replaceability requirements while preserving the existing Hybrid Credibility Engine architecture. |

---

# PRD Approval

| Role               | Status     |
| ------------------ | ---------- |
| Product Manager    | ✅ Approved |
| Developer          | Pending    |
| Project Supervisor | Pending    |

---

# End of PRD.md

---

# Final ML Product Requirement Clarification

The product requirement is now specific: the Version 1 production classifier is to be fine-tuned from `microsoft/deberta-v3-base` using the approved cleaned WELFake + FEVER training strategy. LIAR is reserved for external evaluation.

Final fine-tuning and evaluation are complete. The frozen model artifact is `final_model_corrected`. Integration of that artifact through the Model Adapter and AI Analysis Service remains an application implementation task.

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
