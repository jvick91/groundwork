"""
SQLAlchemy ORM models.

This module is intentionally empty in the scaffold. Models are added per phase:

- Phase 1 (EAV - SPEC-001): EntityType, AttributeDefinition, Entity, AttributeValue
- Phase 2 (Identity - SPEC-002): Organization, Person, PersonOrganization, Role,
  Permission, RolePermission, PersonRole, ExternalIdentity
- Phase 3 (Scheduling - SPEC-003): Appointment, RecurrenceRule, AvailabilityBlock
- Phase 4 (Clinical - SPEC-004): SessionNote, SessionBridge, Diagnosis
- Phase 4 (Billing - SPEC-005): Invoice, LineItem, Payment, InsuranceClaim
- Phase 4 (Compliance - SPEC-006): AuditLog, ConsentRecord, DataRetentionPolicy
- Phase 5 (API - SPEC-007): RateLimitRule, ApiKey

All models should inherit from app.core.database.Base.
"""
