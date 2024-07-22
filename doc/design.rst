===================
Design Overview
===================

Purpose
===========

`django-redshift-backend` provides a backend for integrating Amazon Redshift database with the Django framework. It allows Django applications to use Redshift as their database while maintaining compatibility with Django's ORM and database abstraction layer.

Background of the Changes to support Django 4.2
=====================================================

Amazon Redshift is forked from an older version of PostgreSQL. As a result, it is difficult to directly use Django's PostgreSQL database backend, especially with the newer versions of Django (4.2, 5.0) where compatibility issues arise.
So, the current changes are aimed at supporting Django 4.2 by including Django 4.0 code.

Main Changes
-----------------

1. **Inclusion of Django 4.0 Code**:

   - To ensure that the Redshift backend works with Django 4.2 and future versions (such as Django 5.0), we have included database-related code from Django 4.0 in the package.
   - This avoids the difficulties in implementing the Redshift backend with Django 4.2's codebase.
     Difficulties: https://github.com/jazzband/django-redshift-backend/pull/111

2. **Ensuring Code Compatibility**:

   - We have made necessary modifications and adjustments to ensure operation with Django 4.2 and later versions.
   - Specific changes can be viewed at the following link: https://github.com/jazzband/django-redshift-backend/pull/129

Key Components of django-redshift-backend
=============================================

1. **Custom Database Backend**

   - Extends Django's PostgreSQL backend
   - Implements Redshift-specific functionality
   - Handles differences between PostgreSQL and Redshift

2. **SQL Compiler**

   - Modifies SQL generation to be compatible with Redshift
   - Handles Redshift-specific SQL syntax and limitations

3. **Schema Editor**

   - Customizes schema migrations for Redshift
   - Manages Redshift-specific data types and constraints

Design Principles
====================

1. **Compatibility**: Maintain maximum compatibility with Django's existing PostgreSQL backend
2. **Transparency**: Allow developers to use Django's ORM without significant changes to their code
3. **Flexibility**: Support Redshift-specific features where possible

Key Challenges
====================

1. **Version Compatibility**: 
   Maintain compatibility with Redshift by using the database backend from Django 4.0, which is based on PostgreSQL 10 (no longer supported by Django). This ensures stable operation even with the latest Django versions.

2. **SQL Differences**: 
   Handle syntactical and functional differences between PostgreSQL and Redshift. Particularly, some PostgreSQL DDL (Data Definition Language) statements are not compatible with Redshift, requiring adjustments in areas such as table creation and constraint handling.

3. **Data Type Mapping**: 
   Map Django field types to appropriate Redshift data types. This is crucial as Redshift has different data types and limitations compared to standard PostgreSQL.

Implementation Strategy
============================

1. Use Django 4.0's PostgreSQL backend as the base for the custom Redshift backend
2. Override necessary methods to implement Redshift-specific behavior
3. Implement custom SQL compilation logic to generate Redshift-compatible SQL
4. Develop schema editing logic that accounts for Redshift's limitations

Testing and Validation
========================

1. Unit tests for Redshift-specific functionality and limitations
2. Integration tests with actual Redshift instances
3. Compatibility testing with supporting Django and Python versions
4. Operational verification in common Django application scenarios

Future Considerations
============================

1. Ongoing maintenance of the Django 4.0-based code to ensure continued compatibility with newer Django versions.

2. Exploration of a potential re-implementation from scratch based on Django 4.2 or later. This would involve:

   - Analyzing the feasibility of adapting to Django 4.2's database backend structure
   - Evaluating the benefits and drawbacks of a complete rewrite
