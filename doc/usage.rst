======
Usage
======

Support versions
================

This product is tested with:

* python-2.7, 3.5, 3.6
* django-1.11


Differences from postgres_psycopg2 backend
==========================================

Type mapping:

* 'integer identity(1, 1)' for AutoField
* 'bigint identity(1, 1)' for BigAutoField
* 'timestamp with time zone' for DateTimeField
* 'varchar(max)' for TextField
* 'varchar(32)' for UUIDField
* Possibility to multiply VARCHAR length to support utf-8 string, using
  `REDSHIFT_VARCHAR_LENGTH_MULTIPLIER` setting.

Stop using:

* RETURNING (single insert and bulk insert)
* SELECT FOR UPDATE
* SELECT DISTINCT ON
* SET CONSTRAINTS
* INDEX
* DEFERRABLE INITIALLY DEFERRED
* CONSTRAINT
* CHECK
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

Using sortkey
---------------------------------

There is built-in support for this option for Django >= 1.9. To use `sortkey`, simply define an `ordering` on the model meta as follow::

  class MyModel(models.Model):
      ...

      class Meta:
          ordering = ['col2']

N.B.: there is no validation of this option, instead we let Redshift validate it for you. Be sure to refer to the `documentation <http://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_TABLE_examples.html>`_.

