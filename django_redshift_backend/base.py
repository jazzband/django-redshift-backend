"""
Redshift database backend for Django based upon django PostgreSQL backend.

Requires psycopg 2: http://initd.org/projects/psycopg2
"""
from __future__ import absolute_import

from copy import deepcopy
import logging

from django.db.backends.postgresql_psycopg2.base import (
    DatabaseFeatures as BasePGDatabaseFeatures,
    DatabaseWrapper as BasePGDatabaseWrapper,
    DatabaseOperations as BasePGDatabaseOperations,
    DatabaseClient,
    DatabaseCreation,
    DatabaseIntrospection,
    BaseDatabaseValidation,
)

logger = logging.getLogger('django.db.backends')


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

    data_types = deepcopy(BasePGDatabaseWrapper.data_types)
    data_types["DateTimeField"] = "timestamp"

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        self.features = DatabaseFeatures(self)
        self.ops = DatabaseOperations(self)
        self.client = DatabaseClient(self)
        self.creation = DatabaseCreation(self)
        self.introspection = DatabaseIntrospection(self)
        self.validation = BaseDatabaseValidation(self)

    def init_connection_state(self):
        self.connection.set_client_encoding('UTF8')

        tz = self.settings_dict['TIME_ZONE']
        conn_tz = self.connection.get_parameter_status('TimeZone')

        if tz and conn_tz != tz:
            logger.debug("TIME_ZONE `%s` is specified and redshift is using `%s`. "
                         "However, Redshift doesn't support `SET TIME ZONE` command, "
                         "so redshift backend do nothing.", tz, conn_tz)
            cursor = self.connection.cursor()
            try:
                cursor.execute('SELECT version()')
            finally:
                cursor.close()
            # Commit after setting the time zone (see #17062)
            if not self.get_autocommit():
                self.connection.commit()
