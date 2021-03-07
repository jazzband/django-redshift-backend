CHANGES
=======

2.1.0 (Unreleased)
------------------

Bug Fixes:

* #74: set supports_aggregate_filter_clause=False (since Django-2.0) to disable FILTER WHERE syntax. Thanks to Michael Wheeler.

2.0.0 (2021/01/04)
-------------------

General:

* #70,#71,#72 Moved CI to GitHub Actions: https://github.com/jazzband/django-redshift-backend/actions
  Thkanks to Bruno Alla.

Features:

* Drop Python 2.7 and 3.5 support.
* Drop Django 1.11, 2.0 and 2.1 support.
* #68 Add Python 3.8 and 3.9 support.
* #68 Add Django 3.0 and 3.1 support.

Bug Fixes:

* #69 Let users choose between psycopg2 binary or source. Thkanks to Bruno Alla.
* #65,#66 Deprecation warning due to invalid escape sequences. Thanks to Karthikeyan Singaravelan.

Documentation:

* #67 Just a typo cleanup from refs.rst. Thanks to Kostja P.

1.1.0 (2019/08/02)
------------------

* #60 Change dependencies to support Python 3.7 Thanks to Asher Foa.

1.0.0 (2019/01/29)
------------------

General:

* The first release from Jazzband_ organization.
* Using `Development Status :: 5 - Production/Stable`.
* All GitHub/Travis/other URLs in this product has been migrated to `/jazzband/`.

New Features:

* #56 Support Django 2.1.
* #57 Support Python 3.7

Bug Fixes:

* #53,#54: UUIDField django model field will cause clash. Thanks to Corentin Dupret.

Development:

* Adopt setuptools_scm for versioning from git tag.

.. _Jazzband: https://jazzband.co/

0.9.1 (2018-09-29)
------------------

* fix trove classifier 'License' from BSD to Apache.
* Documentation: Add `Contribution Guideline`_

.. _Contribution Guideline: https://django-redshift-backend.readthedocs.io/en/master/dev.html#contribution-guideline

0.9 (2018-07-24)
----------------

* #35: Drop support for Django 1.8, 1.9 and 1.10.
* #40: Support Django 2.0.
* #42: Support DISTKEY. Thanks to Benjy Weinberger.
* Documentation: http://django-redshift-backend.rtfd.io/
* Change LICENSE from 'BSD License' to 'Apache Software License'

0.8.1 (2018-06-19)
------------------

* #38: Fix 0.8 doesn't compatible with Python 2. Thanks to Benjy Weinberger.

0.8 (2018-06-01)
----------------

Incompatible Changes:

* #23,#10: Redshift support time zones in time stamps for migration

  **IMPORTANT**:
  With this change, the newly created DateTimeField column will be timestamp
  with timezone (TIMESTAMPTZ) by migration. Therefore, the existing
  DateTimeField and the new DateTimeField will have different data types as a
  redshift schema column type.
  There are no migration feature by django-redshift-backend.
  see also: https://github.com/jazzband/django-redshift-backend/pull/23

New Features:

* #20,#26: Support for sortkey. Thanks to Maxime Vdb and Kosei Kitahara.
* #24: Add UUIDField support. Thanks to Sindri Guðmundsson.
* #14: More compat with redshift: not use SELECT DISTINCT ON.

Bug Fixes:

* #15,#21: More compat with redshift: not use CHECK. Thanks to Vasil Vangelovski.
* #18: Fix error on migration with django-1.9 or later that raises AttributeError
  of 'sql_create_table_unique'.
* #27: annotate() does not work on Django-1.9 and later. Thanks to Takayuki Hirai.


Documentation:

* Add documentation: http://django-redshift-backend.rtfd.io/


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

