import sys

def replace_lines(filepath, start_line, end_line, new_content):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    start_idx = start_line - 1
    end_idx = end_line
    
    new_lines = new_content.splitlines(True)
    if not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'
        
    lines[start_idx:end_idx] = new_lines
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)

new_content = """# 56. High-Level ER Diagram

```mermaid
erDiagram

USER ||--o{ CLAIM : submits
CLAIM ||--|| ANALYSIS : has
USER ||--o{ CLAIM_FEEDBACK : gives
CLAIM ||--o{ CLAIM_FEEDBACK : receives
USER ||--o{ AUDIT_LOG : generates

USER {
    UUID id
    string full_name
    string email
    string password
    string role
    boolean is_active
    boolean is_superuser
    datetime created_at
    datetime updated_at
}

CLAIM {
    UUID id
    UUID user_id
    text text
    string status
    datetime submitted_at
    datetime updated_at
}

ANALYSIS {
    UUID claim_id
    float credibility_score
    string verdict
    json explainability_json
    string model_prediction
    float model_confidence
    text fact_check_summary
    int fact_check_match_count
    int narrative_match_count
    float highest_similarity_score
    json rule_based_flags
    float final_weighted_score
    datetime analysis_timestamp
}

CLAIM_FEEDBACK {
    UUID id
    UUID user_id
    UUID claim_id
    string feedback_type
}

AUDIT_LOG {
    UUID id
    UUID user_id
    string action
    string target
    json metadata
    datetime timestamp
}
```

---

# 57. Core Tables

## 1. Users

### Purpose
Store registered users.

### Columns
* `id` (UUIDField)
* `full_name` (CharField)
* `email` (EmailField)
* `password` (CharField, from AbstractBaseUser)
* `role` (CharField)
* `is_active` (BooleanField)
* `is_superuser` (BooleanField, from PermissionsMixin)
* `created_at` (DateTimeField)
* `updated_at` (DateTimeField)

### Constraints & Relationships
* **Choices**: `role` is limited to `USER` or `ADMIN`.
* **Unique Constraints**: `email` is unique.

### Indexes
* `db_index=True` on `email`.

---

## 2. Claims

### Purpose
Store user-submitted textual claims.

### Columns
* `id` (UUIDField)
* `user` (ForeignKey to User)
* `text` (TextField)
* `status` (CharField)
* `submitted_at` (DateTimeField)
* `updated_at` (DateTimeField)

### Constraints & Relationships
* **Foreign Key**: `user` references `User`, with `on_delete=CASCADE`.
* **Choices**: `status` is limited to `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`.
* **Field Validators**: `text` requires minimum length of 10 and maximum length of 2000.
* **Check Constraints**: `valid_claim_text_length` strictly enforces `text` length >= 10 at the database level.

### Indexes
* `models.Index` on `submitted_at` (`claim_submitted_at_idx`).

---

## 3. Analyses

### Purpose
Store the complete credibility analysis generated after processing a claim.

### Columns
* `claim` (OneToOneField to Claim)
* `credibility_score` (FloatField)
* `verdict` (CharField)
* `explainability_json` (JSONField)
* `model_prediction` (CharField)
* `model_confidence` (FloatField)
* `fact_check_summary` (TextField)
* `fact_check_match_count` (IntegerField)
* `narrative_match_count` (IntegerField)
* `highest_similarity_score` (FloatField)
* `rule_based_flags` (JSONField)
* `final_weighted_score` (FloatField)
* `analysis_timestamp` (DateTimeField)

### Nullability
* `credibility_score`, `verdict`, `model_prediction`, `model_confidence`, `fact_check_summary`, `fact_check_match_count`, `narrative_match_count`, `highest_similarity_score`, `final_weighted_score` are nullable.

### Constraints & Relationships
* **Primary Key**: `claim` serves as the primary key.
* **Foreign Key**: `claim` references `Claim`, with `on_delete=CASCADE`.
* **Choices**: `verdict` is limited to `CREDIBLE`, `UNCERTAIN`, `MISINFORMATION`.
* **Choices**: `model_prediction` is limited to `CREDIBLE`, `MISINFORMATION`.
* **Field Validators**: `credibility_score` and `final_weighted_score` enforce range 0.0 to 100.0.
* **Check Constraints**:
  * `valid_credibility_score_range` ensures `credibility_score` is 0.0 - 100.0 (or NULL).
  * `valid_final_weighted_score_range` ensures `final_weighted_score` is 0.0 - 100.0 (or NULL).
  * `valid_verdict_values` ensures `verdict` is a valid choice (or NULL).
  * `valid_model_confidence_range` ensures `model_confidence` is 0.0 - 1.0 (or NULL).

### Indexes
* `models.Index` on `analysis_timestamp` (`analysis_timestamp_idx`).

---

### Why Separate Analysis?
Each submitted claim has one analysis record in the MVP.
The Analysis table stores multiple signals from the Hybrid Credibility Engine, including explicit JSON fields for explanations and heuristic flags. The schema is intentionally designed to support future enhancements without requiring redesign.

---

## 4. Claim Feedback

### Purpose
Store user feedback.

### Columns
* `id` (UUIDField)
* `user` (ForeignKey to User)
* `claim` (ForeignKey to Claim)
* `feedback_type` (CharField)

### Constraints & Relationships
* **Foreign Key**: `user` references `User`, with `on_delete=CASCADE`.
* **Foreign Key**: `claim` references `Claim`, with `on_delete=CASCADE`.
* **Choices**: `feedback_type` is limited to `HELPFUL` or `NOT_HELPFUL`.
* **Unique Constraints**: `UniqueConstraint` on `(user, claim)` strictly enforcing one feedback per user per claim.

---

## 5. Audit Logs

### Purpose
Track important administrative actions (e.g., user disabled, claim deleted, profile update).

### Columns
* `id` (UUIDField)
* `user` (ForeignKey to User)
* `action` (CharField)
* `target` (CharField)
* `metadata` (JSONField)
* `timestamp` (DateTimeField)

### Nullability
* `user` is nullable (allowing for system actions or after user deletion).
* `target` is nullable.

### Constraints & Relationships
* **Foreign Key**: `user` references `User`, with `on_delete=SET_NULL`. Deleting the related User safely sets the AuditLog user reference to NULL, ensuring the AuditLog itself remains.

### Indexes
* `models.Index` on `timestamp` (`audit_timestamp_idx`).

"""

replace_lines('c:/Users/Dell/Desktop/InfoTrust/ARCHITECTURE.md', 2229, 2419, new_content)
print("Done.")
