====================================
Redshift database backend for Django
====================================

This product is tested with:

* python-2.7, 3.5, 3.6
* django-1.8, 1.9, 1.10, 1.11


Differences from postgres_psycopg2 backend
==========================================

Type mapping:

* 'integer identity(1, 1)' for AutoField
* 'bigint identity(1, 1)' for BigAutoField
* 'timestamp' for DateTimeField
* 'varchar(max)' for TextField
* Possibility to multiply VARCHAR length to support utf-8 string, using
  `REDSHIFT_VARCHAR_LENGTH_MULTIPLIER` setting.

Stop using:

* RETURNING (single insert and bulk insert)
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

Note and Limitation
--------------------

Amazon Redshift doesn't support RETURNING, so ``last_insert_id`` method retrieve MAX(pk) after insertion as a workaround.

refs:

* http://stackoverflow.com/q/19428860
* http://stackoverflow.com/q/25638539

In some case, MAX(pk) workaround does not work correctly.
Bulk insertion makes non-contiguous IDs like: 1, 4, 7, 10, ...
and single insertion after such bulk insertion generates strange id value like 2 (smallest non-used id).


SETTINGS
========

ENGINE for DATABASES is 'django_redshift_backend'. You can set the name in your settings.py as::

   DATABASES = {
       'default': {
           'ENGINE': 'django_redshift_backend',
           'NAME': '<your database name>',
           'USER': '<your database username>',
           'PASSWORD': '<your database password>',
           'HOST': '<your database hostname>',
           'PORT': '5439',
       }
   }

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

0.7 (2017-06-08)
----------------

* Drop Python-3.4
* Drop Django-1.7
* Support Python-3.6
* Support Django-1.11

0.6 (2016-12-15)
----------------

* Fix crush problem when using bulk insert.

0.5 (2016-10-05)
----------------

* Support Django-1.10
* #9: Add support for BigAutoField. Thanks to Maxime Vdb.
* Fix crush problem on sqlmigrate when field modified.

0.4 (2016-05-17)
----------------

* Support Python-3.4 and 3.5
* #7: Restore support django-1.7. Version 0.3 doesn't support django-1.7.
* #4: More compat with redshift: not use SET CONSTRAINTS. Thanks to Maxime Vdb.
* #6: More compat with redshift: not use sequence reset query. Thanks to Maxime Vdb.
* #5: Add REDSHIFT_VARCHAR_LENGTH_MULTIPLIER settings. Thanks to Maxime Vdb.
* Support column type changing on migration.

0.3 (2016-05-14)
----------------

* #3: more compat with Redshift (AutoField, DateTimeField, Index). Thanks to Maxime Vdb.
* More compat with redshift: add TextField
* More compat with redshift: not use DEFERRABLE, CONSTRAINT, DROP DEFAULT
* More compat with redshift: support modify column


0.2.1 (2016-02-01)
------------------

* "SET TIME_ZONE" warning is changed as debug log for 'django.db.backend' logger.

0.2 (2016-01-08)
----------------

* Disable "SET TIME_ZONE" SQL execution even if settings.TIME_ZONE is specified.

0.1.2 (2015-06-5)
-----------------

* Support Django-1.8

0.1.1 (2015-03-27)
------------------
* Disable "SELECT FOR UPDATE" SQL execution.

0.1 (2015-03-24)
----------------
* Support Django-1.7
* Support "INSERT INTO" SQL execution without "RETURNING" clause.

