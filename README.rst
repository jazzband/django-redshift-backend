====================================
Redshift database backend for Django
====================================

This product is tested with:

* python-2.7, 3.4, 3.5
* django-1.7, 1.8, 1.9


Differences from postgres_psycopg2 backend
==========================================

Type mapping:

* 'integer identity(1, 1)' for AutoField
* 'timestamp' for DateTimeField
* 'varchar(max)' for TextField
* Possibility to multiply VARCHAR length to support utf-8 string, using
  `REDSHIFT_VARCHAR_LENGTH_MULTIPLIER` setting.

Stop using:

* RETURNING.
* SELECT FOR UPDATE
* SET TIME ZONE
* SET CONSTRAINTS
* INDEX
* DEFERRABLE INITIALLY DEFERRED
* CONSTRAINT
* DROP DEFAULT

To support migration:

* To add column to existent table on Redshift, column must be nullable
* To support modify column, add new column -> data migration -> drop old column -> rename

Please note that the migration support for redshift is not perfect yet.


SETTINGS
========

REDSHIFT_VARCHAR_LENGTH_MULTIPLIER:
  Possibility to multiply VARCHAR length to support utf-8 string. Default is 1.

TESTING
=======

Testing this package requires:

* tox-1.8 or later
* virtualenv-15.0.1 or later
* pip-8.1.1 or later

and `wheelhouse` directory contains psycopg2 manylinux1 wheels for using in each tests.


LICENSE
=======
Apache Software License


CHANGES
=======

0.4
---

* Support Python-3.4 and 3.5
* #7: Restore support django-1.7. Version 0.3 doesn't support django-1.7.
* #4: More compat with redshift: not use SET CONSTRAINTS. Thanks to Maxime Vdb.
* #6: More compat with redshift: not use sequence reset query. Thanks to Maxime Vdb.
* #5: Add REDSHIFT_VARCHAR_LENGTH_MULTIPLIER settings. Thanks to Maxime Vdb.
* Support column type changing on migration.

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

