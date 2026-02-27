===================
Design Overview
===================

Purpose
===========

``django-redshift-backend`` provides a backend for integrating Amazon Redshift database with the Django framework. It allows Django applications to use Redshift as their database while maintaining compatibility with Django's ORM and database abstraction layer.

Architecture
===============

The backend inherits directly from Django's **base** database backend classes (``django.db.backends.base.*``) rather than from the PostgreSQL backend. This is because:

- Amazon Redshift is forked from PostgreSQL 8.0.2, which is no longer supported by Django's PostgreSQL backend (Django 4.1+ requires PostgreSQL 12+).
- Inheriting from the base backend avoids version check failures and incompatible PostgreSQL-specific code paths.
- The backend uses **psycopg2** for database connectivity since Redshift uses the PostgreSQL wire protocol.

Module Structure
-------------------

The backend is organized into standard Django backend modules:

- ``base.py`` - ``DatabaseWrapper``: Connection management via psycopg2
- ``features.py`` - ``DatabaseFeatures``: Feature flags for Redshift limitations
- ``operations.py`` - ``DatabaseOperations``: SQL generation and type handling
- ``schema.py`` - ``DatabaseSchemaEditor``: DDL operations and migrations
- ``introspection.py`` - ``DatabaseIntrospection``: Database schema inspection
- ``creation.py`` - ``DatabaseCreation``: Test database management
- ``client.py`` - ``DatabaseClient``: Command-line client (psql)
- ``meta.py`` - ``DistKey``, ``SortKey``: Redshift-specific model meta classes
- ``psycopg2adapter.py`` - ``RedshiftBinary``: Binary field adapter for varbyte

Key Components
================

1. **DatabaseWrapper** (``base.py``)

   - Inherits from ``django.db.backends.base.base.BaseDatabaseWrapper``
   - Sets ``vendor = "redshift"``
   - Manages psycopg2 connections (encoding, timezone, isolation level)
   - Merges Redshift-specific data types directly into ``data_types``

2. **DatabaseFeatures** (``features.py``)

   - Disables features not supported by Redshift:
     ``RETURNING``, ``SELECT FOR UPDATE``, ``DISTINCT ON``,
     check constraints, native JSON/UUID, DDL rollback,
     ``ON CONFLICT``, aggregate ``FILTER``, etc.

3. **DatabaseOperations** (``operations.py``)

   - PostgreSQL-compatible SQL generation with psycopg2
   - Temporal methods use Django 4.2+ ``(sql, params)`` tuple API
   - ``last_insert_id()`` uses ``MAX(pk)`` workaround (no ``RETURNING``)
   - UUID fields stored as ``varchar(36)`` with custom converter

4. **DatabaseSchemaEditor** (``schema.py``)

   - 4-step column alteration: add temp column, copy data, drop old, rename
   - DISTKEY/SORTKEY support in ``CREATE TABLE``
   - VARCHAR length multiplier for UTF-8 byte counting
   - All index operations are no-ops (Redshift does not support indexes)
   - Binary field handling via ``RedshiftBinary`` adapter

5. **DatabaseIntrospection** (``introspection.py``)

   - Detects ``identity`` columns as AutoField (not ``nextval``)
   - Custom ``get_table_description()`` without collation support
   - Custom ``get_constraints()`` without ``unnest``/``array_agg``

Design Principles
====================

1. **Independence**: Inherit from Django's base backend, not PostgreSQL
2. **Compatibility**: Work across Django 4.2, 5.0, 5.1, and future versions
3. **Transparency**: Allow developers to use Django's ORM without changes
4. **Flexibility**: Support Redshift-specific features (DISTKEY, SORTKEY)

Key Challenges
====================

1. **SQL Differences**:
   Handle syntactical and functional differences between PostgreSQL and Redshift.
   Particularly, some PostgreSQL DDL statements are not compatible with Redshift,
   requiring adjustments in areas such as table creation and constraint handling.

2. **Data Type Mapping**:
   Map Django field types to appropriate Redshift data types. Redshift uses
   ``identity(1, 1)`` instead of ``serial``, ``varchar(max)`` instead of ``text``,
   ``varbyte`` instead of ``bytea``, and ``varchar(36)`` instead of ``uuid``.

3. **ALTER TABLE Limitations**:
   Redshift cannot directly alter column types, nullability, or defaults in many
   cases. The schema editor implements a 4-step recreation strategy to work around
   these limitations.

Testing and Validation
========================

1. Unit tests for Redshift-specific functionality and limitations
2. Integration tests with actual Redshift instances (``TEST_WITH_REDSHIFT=1``)
3. Local testing against PostgreSQL (``TEST_WITH_POSTGRES=1``)
4. Compatibility testing across Django 4.2, 5.0, and 5.1 via tox

History
=========

The backend was previously built on top of vendored Django 4.0 PostgreSQL backend
code (~5,700 lines). This was replaced with a standalone implementation inheriting
from Django's base backend classes, as tracked in
`issue #167 <https://github.com/jazzband/django-redshift-backend/issues/167>`_.
