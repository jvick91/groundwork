"""
Test data factories and helpers.

Provides helper functions for creating test entities. Per-phase factories
are added here as domain models are implemented.

- Phase 1: EAV entity/attribute factories
- Phase 2: Person, Organization, Role factories
- Phase 3: Appointment, AvailabilityBlock factories
- Phase 4: SessionNote, Invoice, ConsentRecord factories
"""

import uuid


def make_uuid() -> uuid.UUID:
    """Generate a random UUID for test data."""
    return uuid.uuid4()
