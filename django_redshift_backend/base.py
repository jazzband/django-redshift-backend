"""
Redshift database backend for Django based upon django PostgreSQL backend.

Requires psycopg 2: http://initd.org/projects/psycopg2
"""
from __future__ import absolute_import

try:
    from django.db.backends.base.validation import (
        BaseDatabaseValidation,
    )
except ImportError:
    # for django < 1.8
    from django.db.backends import BaseDatabaseValidation
from django.db.backends.postgresql_psycopg2.base import (
    DatabaseFeatures as BasePGDatabaseFeatures,
    DatabaseWrapper as BasePGDatabaseWrapper,
    DatabaseOperations as BasePGDatabaseOperations,
    DatabaseClient,
    DatabaseCreation,
    DatabaseIntrospection,
)


class DatabaseFeatures(BasePGDatabaseFeatures):
    can_return_id_from_insert = False
    has_select_for_update = False


class DatabaseOperations(BasePGDatabaseOperations):

    def last_insert_id(self, cursor, table_name, pk_name):
        cursor.execute('SELECT MAX({pk}) from {table}'.format(pk=pk_name, table=self.quote_name(table_name)))
        return cursor.fetchone()[0]

    def for_update_sql(self, nowait=False):
        raise NotImplementedError('SELECT FOR UPDATE is not implemented for this database backend')


class DatabaseWrapper(BasePGDatabaseWrapper):
    vendor = 'redshift'

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        self.features = DatabaseFeatures(self)
        self.ops = DatabaseOperations(self)
        self.client = DatabaseClient(self)
        self.creation = DatabaseCreation(self)
        self.introspection = DatabaseIntrospection(self)
        self.validation = BaseDatabaseValidation(self)
