====================================
Redshift database backend for Django
====================================

This product is tested with:

* python-2.7.x
* django-1.7.6, 1.7.10, 1.8.8


Differences from postgres_psycopg2 backend
==========================================

* Use 'integer identity(1, 1)' for AutoField
* Use 'timestamp' for DateTimeField
* Use 'varchar(max)' for TextField
* Multiply 3 to VARCHAR length to support utf-8 string
* Not use RETURNING.
* Not use SELECT FOR UPDATE.
* Not use SET TIME ZONE.
* Not use Index
* Not use DEFERRABLE INITIALLY DEFERRED
* Not use CONSTRAINT
* Not use DROP DEFAULT
* To add column to existent table on Redshift, column must be nullable
* To support modify column, add new column -> data migration -> drop old column -> rename

LICENSE
=======
Apache Software License


CHANGES
=======

0.3
---

* #3: more compat with Redshift (AutoField, DateTimeField, Index). Thanks to Maxime Vdb.
* More compat with redshift: add TextField
* More compat with redshift: not use DEFERRABLE, CONSTRAINT, DROP DEFAULT
* More compat with redshift: support modify column


0.2.1
-----

* "SET TIME_ZONE" warning is changed as debug log for 'django.db.backend' logger.

0.2
---

* Disable "SET TIME_ZONE" SQL execution even if settings.TIME_ZONE is specified.

0.1.2
-----

* Support Django-1.8

0.1.1
-----
* Disable "SELECT FOR UPDATE" SQL execution.

0.1
---
* Support Django-1.7
* Support "INSERT INTO" SQL execution without "RETURNING" clause.

