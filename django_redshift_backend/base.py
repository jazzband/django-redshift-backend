"""
Redshift database backend for Django.

Requires psycopg2: https://www.psycopg.org/
"""

import asyncio
import threading
import warnings
from contextlib import contextmanager

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError as WrappedDatabaseError
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.utils import CursorDebugWrapper as BaseCursorDebugWrapper
from django.utils.asyncio import async_unsafe
from django.utils.functional import cached_property
from django.utils.safestring import SafeString
from django.utils.version import get_version_tuple

try:
    import psycopg2 as Database
    import psycopg2.extensions
    import psycopg2.extras
except ImportError:
    raise ImproperlyConfigured(
        "Error loading psycopg2 module. Please install as: "
        "`pip install django-redshift-backend[psycopg2]` or "
        "`pip install django-redshift-backend[psycopg2-binary]`. "
        "For more information, see "
        "https://django-redshift-backend.readthedocs.io/en/master/basic.html#installation"
    )


def psycopg2_version():
    version = psycopg2.__version__.split(" ", 1)[0]
    return get_version_tuple(version)


PSYCOPG2_VERSION = psycopg2_version()

if PSYCOPG2_VERSION < (2, 8, 4):
    raise ImproperlyConfigured(
        "psycopg2 version 2.8.4 or newer is required; you have %s"
        % psycopg2.__version__
    )

from .client import DatabaseClient  # noqa: E402
from .creation import DatabaseCreation  # noqa: E402
from .features import DatabaseFeatures  # noqa: E402
from .introspection import DatabaseIntrospection  # noqa: E402
from .operations import DatabaseOperations  # noqa: E402
from .schema import DatabaseSchemaEditor  # noqa: E402
from .schema import _remove_length_from_type  # noqa: E402, F401 - backward compat
from .meta import DistKey, SortKey  # noqa: E402, F401 - backward compat

psycopg2.extensions.register_adapter(SafeString, psycopg2.extensions.QuotedString)
psycopg2.extras.register_uuid()


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = "redshift"
    display_name = "Amazon Redshift"

    # Data type mappings - Redshift-specific types merged directly
    data_types = {
        "AutoField": "integer identity(1, 1)",
        "BigAutoField": "bigint identity(1, 1)",
        "BinaryField": "varbyte(%(max_length)s)",
        "BooleanField": "boolean",
        "CharField": "varchar(%(max_length)s)",
        "DateField": "date",
        "DateTimeField": "timestamp with time zone",
        "DecimalField": "numeric(%(max_digits)s, %(decimal_places)s)",
        "DurationField": "interval",
        "FileField": "varchar(%(max_length)s)",
        "FilePathField": "varchar(%(max_length)s)",
        "FloatField": "double precision",
        "IntegerField": "integer",
        "BigIntegerField": "bigint",
        "IPAddressField": "varchar(15)",
        "GenericIPAddressField": "varchar(39)",
        "JSONField": "varchar",  # Redshift doesn't support native JSON
        "OneToOneField": "integer",
        "PositiveBigIntegerField": "bigint",
        "PositiveIntegerField": "integer",
        "PositiveSmallIntegerField": "smallint",
        "SlugField": "varchar(%(max_length)s)",
        "SmallAutoField": "smallint identity(1, 1)",
        "SmallIntegerField": "smallint",
        "TextField": "varchar(max)",  # text must be varchar(max) on Redshift
        "TimeField": "time",
        "UUIDField": "varchar(36)",  # Redshift doesn't support native UUID
    }
    data_type_check_constraints = {
        "PositiveBigIntegerField": '"%(column)s" >= 0',
        "PositiveIntegerField": '"%(column)s" >= 0',
        "PositiveSmallIntegerField": '"%(column)s" >= 0',
    }
    operators = {
        "exact": "= %s",
        "iexact": "= UPPER(%s)",
        "contains": "LIKE %s",
        "icontains": "LIKE UPPER(%s)",
        "regex": "~ %s",
        "iregex": "~* %s",
        "gt": "> %s",
        "gte": ">= %s",
        "lt": "< %s",
        "lte": "<= %s",
        "startswith": "LIKE %s",
        "endswith": "LIKE %s",
        "istartswith": "LIKE UPPER(%s)",
        "iendswith": "LIKE UPPER(%s)",
    }

    pattern_esc = (
        r"REPLACE(REPLACE(REPLACE({}, E'\\', E'\\\\'), E'%%', E'\\%%'), E'_', E'\\_')"
    )
    pattern_ops = {
        "contains": "LIKE '%%' || {} || '%%'",
        "icontains": "LIKE '%%' || UPPER({}) || '%%'",
        "startswith": "LIKE {} || '%%'",
        "istartswith": "LIKE UPPER({}) || '%%'",
        "endswith": "LIKE '%%' || {}",
        "iendswith": "LIKE '%%' || UPPER({})",
    }

    Database = Database
    SchemaEditorClass = DatabaseSchemaEditor
    # Classes instantiated in __init__().
    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations
    # Redshift backend-specific attributes.
    _named_cursor_idx = 0

    def get_database_version(self):
        """
        Return the Redshift version as a tuple (e.g., (8, 0, 2)).
        Redshift reports as PostgreSQL 8.0.2 on Amazon Redshift X.Y.Z.
        """
        with self.temporary_connection() as cursor:
            cursor.execute("SELECT version()")
            version_str = cursor.fetchone()[0]
        # Parse something like "PostgreSQL 8.0.2 on ..."
        import re

        match = re.search(r"PostgreSQL (\d+)\.(\d+)\.(\d+)", version_str)
        if match:
            return tuple(int(x) for x in match.groups())
        return (8, 0, 2)  # fallback

    def get_connection_params(self):
        settings_dict = self.settings_dict
        if settings_dict["NAME"] == "" and not settings_dict.get("OPTIONS", {}).get(
            "service"
        ):
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. "
                "Please supply the NAME or OPTIONS['service'] value."
            )
        if len(settings_dict["NAME"] or "") > self.ops.max_name_length():
            raise ImproperlyConfigured(
                "The database name '%s' (%d characters) is longer than "
                "the limit of %d characters. Supply a shorter NAME "
                "in settings.DATABASES."
                % (
                    settings_dict["NAME"],
                    len(settings_dict["NAME"]),
                    self.ops.max_name_length(),
                )
            )
        conn_params = {}
        if settings_dict["NAME"]:
            conn_params = {
                "database": settings_dict["NAME"],
                **settings_dict["OPTIONS"],
            }
        elif settings_dict["NAME"] is None:
            settings_dict.get("OPTIONS", {}).pop("service", None)
            conn_params = {"database": "postgres", **settings_dict["OPTIONS"]}
        else:
            conn_params = {**settings_dict["OPTIONS"]}

        conn_params.pop("isolation_level", None)
        if settings_dict["USER"]:
            conn_params["user"] = settings_dict["USER"]
        if settings_dict["PASSWORD"]:
            conn_params["password"] = settings_dict["PASSWORD"]
        if settings_dict["HOST"]:
            conn_params["host"] = settings_dict["HOST"]
        if settings_dict["PORT"]:
            conn_params["port"] = settings_dict["PORT"]
        return conn_params

    @async_unsafe
    def get_new_connection(self, conn_params):
        connection = Database.connect(**conn_params)

        # self.isolation_level must be set:
        # - after connecting to the database in order to obtain the database's
        #   default when no value is explicitly specified in options.
        # - before calling _set_autocommit() because if autocommit is on, that
        #   will set connection.isolation_level to ISOLATION_LEVEL_AUTOCOMMIT.
        options = self.settings_dict["OPTIONS"]
        try:
            self.isolation_level = options["isolation_level"]
        except KeyError:
            self.isolation_level = connection.isolation_level
        else:
            # Set the isolation level to the value from OPTIONS.
            if self.isolation_level != connection.isolation_level:
                connection.set_session(isolation_level=self.isolation_level)
        # Register dummy loads() to avoid a round trip from psycopg2's decode
        # to json.dumps() to json.loads(), when using a custom decoder in
        # JSONField.
        psycopg2.extras.register_default_jsonb(
            conn_or_curs=connection, loads=lambda x: x
        )
        return connection

    def ensure_timezone(self):
        if self.connection is None:
            return False
        conn_timezone_name = self.connection.get_parameter_status("TimeZone")
        timezone_name = self.timezone_name
        if timezone_name and conn_timezone_name != timezone_name:
            with self.connection.cursor() as cursor:
                cursor.execute(self.ops.set_time_zone_sql(), [timezone_name])
            return True
        return False

    def init_connection_state(self):
        super().init_connection_state()
        self.connection.set_client_encoding("UTF8")

        timezone_changed = self.ensure_timezone()
        if timezone_changed:
            # Commit after setting the time zone (see #17062)
            if not self.get_autocommit():
                self.connection.commit()

    @async_unsafe
    def create_cursor(self, name=None):
        if name:
            cursor = self.connection.cursor(
                name, scrollable=False, withhold=self.connection.autocommit
            )
        else:
            cursor = self.connection.cursor()
        cursor.tzinfo_factory = self.tzinfo_factory if settings.USE_TZ else None
        return cursor

    def tzinfo_factory(self, offset):
        return self.timezone

    @async_unsafe
    def chunked_cursor(self):
        self._named_cursor_idx += 1
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if current_task:
            task_ident = str(id(current_task))
        else:
            task_ident = "sync"
        return self._cursor(
            name="_django_curs_%d_%s_%d"
            % (
                threading.current_thread().ident,
                task_ident,
                self._named_cursor_idx,
            )
        )

    def _set_autocommit(self, autocommit):
        with self.wrap_database_errors:
            self.connection.autocommit = autocommit

    def check_constraints(self, table_names=None):
        """
        No constraints to check in Redshift.
        """
        pass

    def is_usable(self):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Database.Error:
            return False
        else:
            return True

    @contextmanager
    def _nodb_cursor(self):
        cursor = None
        try:
            with super()._nodb_cursor() as cursor:
                yield cursor
        except (Database.DatabaseError, WrappedDatabaseError):
            if cursor is not None:
                raise
            warnings.warn(
                "Normally Django will use a connection to the 'postgres' database "
                "to avoid running initialization queries against the production "
                "database when it's not needed (for example, when running tests). "
                "Django was unable to create a connection to the 'postgres' database "
                "and will use the first database instead.",
                RuntimeWarning,
            )
            for connection in connections.all():
                if (
                    connection.vendor == "redshift"
                    and connection.settings_dict["NAME"] != "postgres"
                ):
                    conn = self.__class__(
                        {
                            **self.settings_dict,
                            "NAME": connection.settings_dict["NAME"],
                        },
                        alias=self.alias,
                    )
                    try:
                        with conn.cursor() as cursor:
                            yield cursor
                    finally:
                        conn.close()
                    break
            else:
                raise

    @cached_property
    def pg_version(self):
        with self.temporary_connection():
            return self.connection.server_version

    def make_debug_cursor(self, cursor):
        return CursorDebugWrapper(cursor, self)


class CursorDebugWrapper(BaseCursorDebugWrapper):
    def copy_expert(self, sql, file, *args):
        with self.debug_sql(sql):
            return self.cursor.copy_expert(sql, file, *args)

    def copy_to(self, file, table, *args, **kwargs):
        with self.debug_sql(sql="COPY %s TO STDOUT" % table):
            return self.cursor.copy_to(file, table, *args, **kwargs)
