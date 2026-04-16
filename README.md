# Groundwork

Multi-tenant mental health practice management platform.

## Overview

Groundwork provides practice management capabilities for mental health organizations, including:

- Entity-Attribute-Value (EAV) flexible data modeling
- Identity management and role-based access control
- Session scheduling and availability
- Clinical documentation and session notes
- Billing and insurance claims
- HIPAA compliance and audit logging

## Quick Start

```bash
# Start all services
docker compose up --build

# Run tests
docker compose exec backend pytest

# API docs (debug mode only)
open http://localhost:8000/api/v1/docs
```

## Architecture

See `specs/` for domain specifications and `adrs/` for architectural decision records.

## Development

This project uses a phased implementation approach. See `.cursorrules` for the two-mode
workflow (Architect/Coder) and phasing order.
