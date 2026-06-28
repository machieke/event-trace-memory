# Event Trace Memory Schemas

This directory contains versioned JSON Schema artifacts for the canonical DA
bodies, snapshot component maps, and compact contract pointers emitted by the
reference implementation.

The schemas intentionally keep `additionalProperties` open so later workers can
add metadata without changing existing IDs or contract-facing required fields.
They pin the stable `kind`, `schema`, identity, CID, and provenance fields used
by the tests and Rholang contracts where those fields are embedded in the
artifact. Map-shaped snapshot components are versioned by filename and manifest
role.
