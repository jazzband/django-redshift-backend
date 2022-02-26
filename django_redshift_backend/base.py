"""
Redshift database backend for Django based upon django PostgreSQL backend.

Requires psycopg 2: http://initd.org/projects/psycopg2
"""
from __future__ import absolute_import

from copy import deepcopy
import re
import uuid
import logging

import django
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db.backends.base.introspection import FieldInfo, TableInfo
from django.db.backends.base.schema import _is_relevant_relation, _related_non_m2m_objects
from django.db.backends.base.validation import BaseDatabaseValidation
from django.db.backends.ddl_references import Statement
from django.db.backends.postgresql.base import (
    DatabaseFeatures as BasePGDatabaseFeatures,
    DatabaseWrapper as BasePGDatabaseWrapper,
    DatabaseOperations as BasePGDatabaseOperations,
    DatabaseSchemaEditor as BasePGDatabaseSchemaEditor,
    DatabaseClient,
    DatabaseCreation as BasePGDatabaseCreation,
    DatabaseIntrospection as BasePGDatabaseIntrospection,
)
from django.db.models import Index
from django.db.utils import NotSupportedError, ProgrammingError

from django_redshift_backend.meta import DistKey, SortKey


logger = logging.getLogger('django.db.backends')


class DatabaseFeatures(BasePGDatabaseFeatures):
    minimum_database_version = (8,)           # Redshift is postgres 8.0.2
    can_return_id_from_insert = False         # old name until django-2.x
    can_return_ids_from_bulk_insert = False   # old name until django-2.x
    can_return_columns_from_insert = False    # new name since django-3.0
    can_return_rows_from_bulk_insert = False  # new name since django-3.0
    has_select_for_update = False
    supports_column_check_constraints = False
    can_distinct_on_fields = False
    allows_group_by_selected_pks = False
    has_native_uuid_field = False
    supports_aggregate_filter_clause = False
    supports_combined_alters = False          # since django-1.8

    # If support atomic for ddl, we should implement non-atomic migration for on rename and change type(size)
    # refs django-redshift-backend #96
    # refs https://github.com/django/django/blob/3702819/django/db/backends/sqlite3/schema.py#L131-L144
    can_rollback_ddl = False


class DatabaseOperations(BasePGDatabaseOperations):

    def last_insert_id(self, cursor, table_name, pk_name):
        """
        Amazon Redshift doesn't support RETURNING, so this method
        retrieve MAX(pk) after insertion as a workaround.

        refs:
        * http://stackoverflow.com/q/19428860
        * http://stackoverflow.com/q/25638539

        How about ``return cursor.lastrowid`` that is implemented in
        django.db.backends.base.operations? Unfortunately, it doesn't
        work too.

        NOTE: in some case, MAX(pk) workaround does not work correctly.
        Bulk insertion makes non-contiguous IDs like: 1, 4, 7, 10, ...
        and single insertion after such bulk insertion generates strange
        id value like 2.
        """
        cursor.execute('SELECT MAX({pk}) from {table}'.format(
            pk=pk_name, table=self.quote_name(table_name)))
        return cursor.fetchone()[0]

    def for_update_sql(self, nowait=False):
        raise NotSupportedError(
            'SELECT FOR UPDATE is not implemented for this database backend')

    def deferrable_sql(self):
        # unused
        return ""

    def sequence_reset_sql(self, style, model_list):
        # impossible with Redshift to reset a sequence
        return []

    def get_db_converters(self, expression):
        converters = super(DatabaseOperations, self).get_db_converters(expression)
        internal_type = expression.output_field.get_internal_type()
        if internal_type == 'UUIDField':
            converters.append(self.convert_uuidfield_value)
        return converters

    def convert_uuidfield_value(self, value, expression, connection):
        if value is not None:
            value = uuid.UUID(value)
        return value

    def distinct_sql(self, fields, *args):
        if fields:
            # https://github.com/jazzband/django-redshift-backend/issues/14
            # Redshift doesn't support DISTINCT ON
            raise NotSupportedError(
                'DISTINCT ON fields is not supported by this database backend'
            )
        return super(DatabaseOperations, self).distinct_sql(fields, *args)


def _get_type_default(field):
    internal_type = field.get_internal_type()
    if internal_type in ('CharField', 'SlugField'):
        default = ''
    elif internal_type == 'BinaryField':
        default = b''
    elif internal_type == 'FloatField':
        default = 0.0
    elif internal_type in (
            'BigAutoField', 'IntegerField', 'BigIntegerField', 'PositiveBigIntegerField', 'PositiveIntegerField',
            'PositiveSmallIntegerField', 'SmallAutoField', 'SmallIntegerField', 'DecimalField'):
        default = 0
    elif internal_type == 'BooleanField':
        default = False
    elif internal_type == 'DateField':
        default = timezone.date()
    elif internal_type == 'TimeField':
        default = timezone.time()
    elif internal_type == 'DateTimeField':
        default = timezone.now()
    else:
        default = None
    return default


class DatabaseSchemaEditor(BasePGDatabaseSchemaEditor):

    sql_create_table = "CREATE TABLE %(table)s (%(definition)s) %(options)s"
    sql_delete_fk = "ALTER TABLE %(table)s DROP CONSTRAINT %(name)s"

    if django.VERSION < (3,):
        # to remove "USING %(column)s::%(type)s"
        sql_alter_column_type = "ALTER COLUMN %(column)s TYPE %(type)s"

    @property
    def multiply_varchar_length(self):
        return int(getattr(settings, "REDSHIFT_VARCHAR_LENGTH_MULTIPLIER", 1))

    def _model_indexes_sql(self, model):
        # Redshift doesn't support INDEX.
        return []

    def _create_like_index_sql(self, model, field):
        # Redshift doesn't support INDEX.
        return None

    def _create_index_sql(self, model, **kwargs):
        # _create_index_sql only called from _create_like_index_sql
        # on django/db/backends/postgresql/schema.py
        raise NotSupportedError("Redshift doesn't support INDEX")

    def alter_index_together(self, model, old_index_together, new_index_together):
        # Redshift doesn't support INDEX.
        return

    def add_index(self, model, index, concurrently=False):
        # Redshift doesn't support INDEX.
        pass

    def remove_index(self, model, index, concurrently=False):
        # Redshift doesn't support INDEX.
        pass

    def create_model(self, model):
        """
        Takes a model and creates a table for it in the database.
        Will also create any accompanying indexes or unique constraints.
        """
        # Create column SQL, add FK deferreds if needed
        column_sqls = []
        params = []
        for field in model._meta.local_fields:
            # SQL
            definition, extra_params = self.column_sql(model, field)
            if definition is None:
                continue

            # ## if 'definition' contains 'varchar', length must be 3 times
            # ## because Redshift requires bytes length for utf-8 chars.
            m = re.match(r'varchar\((\d+?)\)', definition)
            if m:
                definition = re.sub(
                    r"varchar\((\d+?)\)",
                    "varchar({0})".format(
                        str(int(m.group(1)) * self.multiply_varchar_length)),
                    definition)

            field.db_parameters(connection=self.connection)
            # Autoincrement SQL (for backends with inline variant)
            col_type_suffix = field.db_type_suffix(connection=self.connection)
            if col_type_suffix:
                definition += " %s" % col_type_suffix
            params.extend(extra_params)
            # FK
            if field.remote_field and field.db_constraint:
                to_table = field.remote_field.related_model._meta.db_table
                to_column = field.remote_field.related_model._meta.get_field(
                    field.remote_field.field_name).column
                if self.connection.features.supports_foreign_keys:
                    self.deferred_sql.append(self._create_fk_sql(
                        model, field, "_fk_%(to_table)s_%(to_column)s"))
                elif self.sql_create_inline_fk:
                    definition += " " + self.sql_create_inline_fk % {
                        "to_table": self.quote_name(to_table),
                        "to_column": self.quote_name(to_column),
                    }
            # Add the SQL to our big list
            column_sqls.append("%s %s" % (
                self.quote_name(field.column),
                definition,
            ))
            # Autoincrement SQL (for backends with post table definition variant)
            if field.get_internal_type() in ("AutoField", "BigAutoField"):
                autoinc_sql = self.connection.ops.autoinc_sql(
                    model._meta.db_table, field.column)
                if autoinc_sql:
                    self.deferred_sql.extend(autoinc_sql)

        # Add any unique_togethers (always deferred, as some fields might
        # be created afterwards, like geometry fields with some backends)
        for fields in model._meta.unique_together:
            fields = [model._meta.get_field(field) for field in fields]
            self.deferred_sql.append(self._create_unique_sql(model, fields))

        # Make the table
        sql = self.sql_create_table % {
            "table": self.quote_name(model._meta.db_table),
            "definition": ", ".join(column_sqls),
            "options": self._get_create_options(model)
        }
        if model._meta.db_tablespace:
            tablespace_sql = self.connection.ops.tablespace_sql(
                model._meta.db_tablespace)
            if tablespace_sql:
                sql += ' ' + tablespace_sql
        # Prevent using [] as params, in the case a literal '%' is used in the definition
        self.execute(sql, params or None)

        # Add any field index and index_together's
        # (deferred as SQLite3 _remake_table needs it)
        self.deferred_sql.extend(self._model_indexes_sql(model))

        # Make M2M tables
        for field in model._meta.local_many_to_many:
            if field.remote_field.through._meta.auto_created:
                self.create_model(field.remote_field.through)

    def add_field(self, model, field):
        """
        Creates a field on a model.
        Usually involves adding a column, but may involve adding a
        table instead (for M2M fields)
        """
        # Special-case implicit M2M tables
        if field.many_to_many and field.remote_field.through._meta.auto_created:
            return self.create_model(field.remote_field.through)

        # Get the column's definition
        definition, params = self.column_sql(model, field, include_default=True)
        # It might not actually have a column behind it
        if definition is None:
            return

        # ## original BasePGDatabaseSchemaEditor.add_field has check constraints here.
        # ## Redshift doesn't support it.

        # Build the SQL and run it
        sql = self.sql_create_column % {
            "table": self.quote_name(model._meta.db_table),
            "column": self.quote_name(field.column),
            "definition": definition,
        }
        # ## Redshift
        if not field.null and self.effective_default(field) is None:
            # Redshift Can't add NOT NULL column without DEFAULT.
            # https://github.com/jazzband/django-redshift-backend/issues/96
            # https://docs.aws.amazon.com/en_us/redshift/latest/dg/r_ALTER_TABLE.html
            raise ProgrammingError(sql % params)
        self.execute(sql, params)

        # ## original BasePGDatabaseSchemaEditor.add_field drop default here
        # ## Redshift doesn't support DROP DEFAULT.

        # ## original BasePGDatabaseSchemaEditor.add_field has CREATE INDEX.
        # ## Redshift doesn't support INDEX.

        # Add any FK constraints later
        if (field.remote_field and
                self.connection.features.supports_foreign_keys and
                field.db_constraint):
            self.deferred_sql.append(
                self._create_fk_sql(model, field, "_fk_%(to_table)s_%(to_column)s"))
        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    # BASED FROM https://github.com/django/django/blob/3.2.12/django/db/backends/base/schema.py#L611-L864
    def _alter_field(self, model, old_field, new_field, old_type, new_type,
                     old_db_params, new_db_params, strict=False):
        """Perform a "physical" (non-ManyToMany) field update."""
        # Drop any FK constraints, we'll remake them later
        fks_dropped = set()
        if (
            self.connection.features.supports_foreign_keys and
            old_field.remote_field and
            old_field.db_constraint
        ):
            fk_names = self._constraint_names(model, [old_field.column], foreign_key=True)
            if strict and len(fk_names) != 1:
                raise ValueError("Found wrong number (%s) of foreign key constraints for %s.%s" % (
                    len(fk_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for fk_name in fk_names:
                fks_dropped.add((old_field.column,))
                self.execute(self._delete_fk_sql(model, fk_name))
        # Has unique been removed?
        if old_field.unique and (not new_field.unique or self._field_became_primary_key(old_field, new_field)):
            # Find the unique constraint for this field
            meta_constraint_names = {constraint.name for constraint in model._meta.constraints}
            constraint_names = self._constraint_names(
                model, [old_field.column], unique=True, primary_key=False,
                exclude=meta_constraint_names,
            )
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of unique constraints for %s.%s" % (
                    len(constraint_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for constraint_name in constraint_names:
                self.execute(self._delete_unique_sql(model, constraint_name))
        # Drop incoming FK constraints if the field is a primary key or unique,
        # which might be a to_field target, and things are going to change.
        drop_foreign_keys = (
            self.connection.features.supports_foreign_keys and (
                (old_field.primary_key and new_field.primary_key) or
                (old_field.unique and new_field.unique)
            ) and old_type != new_type
        )
        if drop_foreign_keys:
            # '_meta.related_field' also contains M2M reverse fields, these
            # will be filtered out
            for _old_rel, new_rel in _related_non_m2m_objects(old_field, new_field):
                rel_fk_names = self._constraint_names(
                    new_rel.related_model, [new_rel.field.column], foreign_key=True
                )
                for fk_name in rel_fk_names:
                    self.execute(self._delete_fk_sql(new_rel.related_model, fk_name))
        # Removed an index? (no strict check, as multiple indexes are possible)
        # Remove indexes if db_index switched to False or a unique constraint
        # will now be used in lieu of an index. The following lines from the
        # truth table show all True cases; the rest are False:
        #
        # old_field.db_index | old_field.unique | new_field.db_index | new_field.unique
        # ------------------------------------------------------------------------------
        # True               | False            | False              | False
        # True               | False            | False              | True
        # True               | False            | True               | True
        if old_field.db_index and not old_field.unique and (not new_field.db_index or new_field.unique):
            # Find the index for this field
            meta_index_names = {index.name for index in model._meta.indexes}
            # Retrieve only BTREE indexes since this is what's created with
            # db_index=True.
            index_names = self._constraint_names(
                model, [old_field.column], index=True, type_=Index.suffix,
                exclude=meta_index_names,
            )
            for index_name in index_names:
                # The only way to check if an index was created with
                # db_index=True or with Index(['field'], name='foo')
                # is to look at its name (refs #28053).
                self.execute(self._delete_index_sql(model, index_name))
        # Change check constraints?
        if old_db_params['check'] != new_db_params['check'] and old_db_params['check']:
            meta_constraint_names = {constraint.name for constraint in model._meta.constraints}
            constraint_names = self._constraint_names(
                model, [old_field.column], check=True,
                exclude=meta_constraint_names,
            )
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of check constraints for %s.%s" % (
                    len(constraint_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for constraint_name in constraint_names:
                self.execute(self._delete_check_sql(model, constraint_name))
        # Have they renamed the column?
        if old_field.column != new_field.column:
            self.execute(self._rename_field_sql(model._meta.db_table, old_field, new_field, new_type))
            # Rename all references to the renamed column.
            for sql in self.deferred_sql:
                if isinstance(sql, Statement):
                    sql.rename_column_references(model._meta.db_table, old_field.column, new_field.column)
        # Next, start accumulating actions to do
        actions = []
        null_actions = []
        post_actions = []
        # Collation change?
        old_collation = getattr(old_field, 'db_collation', None)
        new_collation = getattr(new_field, 'db_collation', None)
        if old_collation != new_collation:
            # Collation change handles also a type change.
            fragment = self._alter_column_collation_sql(model, new_field, new_type, new_collation)
            actions.append(fragment)
        # Type change?
        elif old_type != new_type:
            fragment, other_actions = self._alter_column_type_sql(model, old_field, new_field, new_type)
            if fragment:  # ## Redshift: In some case, fragment will be empty.
                actions.append(fragment)
            post_actions.extend(other_actions)
        # When changing a column NULL constraint to NOT NULL with a given
        # default value, we need to perform 4 steps:
        #  1. Add a default for new incoming writes
        #  2. Update existing NULL rows with new default
        #  3. Replace NULL constraint with NOT NULL
        #  4. Drop the default again.
        # Default change?
        # ## original do alter ALTER COLUMN SET/DROP DEFAULT.
        # ## Redshift Can't: https://github.com/jazzband/django-redshift-backend/issues/96
        # needs_database_default = False
        # if old_field.null and not new_field.null:
        #     old_default = self.effective_default(old_field)
        #     new_default = self.effective_default(new_field)
        #     if (
        #         not self.skip_default_on_alter(new_field) and
        #         old_default != new_default and
        #         new_default is not None
        #     ):
        #         needs_database_default = True
        #         actions.append(self._alter_column_default_sql(model, old_field, new_field))

        # Nullability change?
        if old_field.null != new_field.null:
            # ## original BaseDatabaseSchemaEditor._alter_column_null_sql return only a fragment
            # fragment = self._alter_column_null_sql(model, old_field, new_field)
            # if fragment:
            #     null_actions.append(fragment)
            # ## Redshift use 4 steps null alternation
            fragment, other_actions = self._alter_column_null_sqls(model, old_field, new_field)
            actions.append(fragment)
            null_actions.extend(other_actions)

        # Only if we have a default and there is a change from NULL to NOT NULL
        # ## original BaseDatabaseSchemaEditor._alter_table four_way_default_alteration
        # four_way_default_alteration = (
        #     new_field.has_default() and
        #     (old_field.null and not new_field.null)
        # )
        # ## Redshift is always 4-way, this flag should be False because the null_actions handles it.
        four_way_default_alteration = False
        new_default = self.effective_default(new_field)  # not used, but for flake8

        if actions or null_actions:
            if not four_way_default_alteration:
                # If we don't have to do a 4-way default alteration we can
                # directly run a (NOT) NULL alteration
                actions = actions + null_actions
            # Combine actions together if we can (e.g. postgres)
            if self.connection.features.supports_combined_alters and actions:
                sql, params = tuple(zip(*actions))
                actions = [(", ".join(sql), sum(params, []))]
            # Apply those actions
            for sql, params in actions:
                self.execute(
                    # ## original assumes only alters, so adding an ALTER TABLE clause
                    # self.sql_alter_column % {
                    #     "table": self.quote_name(model._meta.db_table),
                    #     "changes": sql,
                    # },
                    # ## Redshift executes ADD and UPDATE on alter, so the sql is a complete sentence
                    sql,
                    params,
                )
            if four_way_default_alteration:
                # Update existing rows with default value
                self.execute(
                    self.sql_update_with_default % {
                        "table": self.quote_name(model._meta.db_table),
                        "column": self.quote_name(new_field.column),
                        "default": "%s",
                    },
                    [new_default],
                )
                # Since we didn't run a NOT NULL change before we need to do it
                # now
                for sql, params in null_actions:
                    self.execute(
                        self.sql_alter_column % {
                            "table": self.quote_name(model._meta.db_table),
                            "changes": sql,
                        },
                        params,
                    )
        if post_actions:
            for sql, params in post_actions:
                self.execute(sql, params)
        # If primary_key changed to False, delete the primary key constraint.
        if old_field.primary_key and not new_field.primary_key:
            self._delete_primary_key(model, strict)
        # Added a unique?
        if self._unique_should_be_added(old_field, new_field):
            self.execute(self._create_unique_sql(model, [new_field]))
        # Added an index? Add an index if db_index switched to True or a unique
        # constraint will no longer be used in lieu of an index. The following
        # lines from the truth table show all True cases; the rest are False:
        #
        # old_field.db_index | old_field.unique | new_field.db_index | new_field.unique
        # ------------------------------------------------------------------------------
        # False              | False            | True               | False
        # False              | True             | True               | False
        # True               | True             | True               | False

        # ## original BasePGDatabaseSchemaEditor._alter_field has CREATE INDEX
        # ## Redshift doesn't support it.
        # https://docs.aws.amazon.com/redshift/latest/dg/c_unsupported-postgresql-features.html
        # if (not old_field.db_index or old_field.unique) and new_field.db_index and not new_field.unique:
        #     self.execute(self._create_index_sql(model, fields=[new_field]))

        # Type alteration on primary key? Then we need to alter the column
        # referring to us.
        rels_to_update = []
        if drop_foreign_keys:
            rels_to_update.extend(_related_non_m2m_objects(old_field, new_field))
        # Changed to become primary key?
        if self._field_became_primary_key(old_field, new_field):
            # Make the new one
            self.execute(self._create_primary_key_sql(model, new_field))
            # Update all referencing columns
            rels_to_update.extend(_related_non_m2m_objects(old_field, new_field))
        # Handle our type alters on the other end of rels from the PK stuff above
        for old_rel, new_rel in rels_to_update:
            rel_db_params = new_rel.field.db_parameters(connection=self.connection)
            rel_type = rel_db_params['type']
            fragment, other_actions = self._alter_column_type_sql(
                new_rel.related_model, old_rel.field, new_rel.field, rel_type
            )
            # ## original assumes only alters, so adding an ALTER TABLE clause
            # self.execute(
            #     self.sql_alter_column % {
            #         "table": self.quote_name(new_rel.related_model._meta.db_table),
            #         "changes": fragment[0],
            #     },
            #     fragment[1],
            # )
            # ## Redshift executes ADD and UPDATE on alter, so the fragment[0] is a complete sentence
            self.execute(fragment[0], fragment[1])
            for sql, params in other_actions:
                self.execute(sql, params)
        # Does it have a foreign key?
        if (self.connection.features.supports_foreign_keys and new_field.remote_field and
                (fks_dropped or not old_field.remote_field or not old_field.db_constraint) and
                new_field.db_constraint):
            self.execute(self._create_fk_sql(model, new_field, "_fk_%(to_table)s_%(to_column)s"))
        # Rebuild FKs that pointed to us if we previously had to drop them
        if drop_foreign_keys:
            for rel in new_field.model._meta.related_objects:
                if _is_relevant_relation(rel, new_field) and rel.field.db_constraint:
                    self.execute(self._create_fk_sql(rel.related_model, rel.field, "_fk"))
        # Does it have check constraints we need to add?
        if old_db_params['check'] != new_db_params['check'] and new_db_params['check']:
            constraint_name = self._create_index_name(model._meta.db_table, [new_field.column], suffix='_check')
            self.execute(self._create_check_sql(model, constraint_name, new_db_params['check']))

        # ## original BasePGDatabaseSchemaEditor._alter_field drop default here
        # ## Redshift doesn't support DROP DEFAULT.
        # Drop the default if we need to
        # (Django usually does not use in-database defaults)
        # if needs_database_default:
        #     changes_sql, params = self._alter_column_default_sql(model, old_field, new_field, drop=True)
        #     sql = self.sql_alter_column % {
        #         "table": self.quote_name(model._meta.db_table),
        #         "changes": changes_sql,
        #     }
        #     self.execute(sql, params)

        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    def _alter_column_with_recreate(self, model, old_field, new_field):
        """
        To change column type or default, We need this migration sequence:

        1. Add new column with temporary name
        2. Migrate values from original column to temprary column
        3. Drop old column
        4. Rename temporary column name to original column name
        """
        fragment = ('', [])
        actions = []

        # ## ALTER TABLE <table> ADD COLUMN 'tmp' <type> DEFAULT <value>
        if not new_field.null and not new_field.has_default():
            # Redshift can't add NOT NULL or DROP NOT NULL, then DEFAULT value is needed.
            # Note that only backwards migration is in here.
            default = _get_type_default(new_field)
            if default is None:
                raise ValueError(
                    "django-redshift-backend doesn't know default for the type: {}".format(
                        new_field.get_internal_type()
                    ))
            new_field.default = default

        definition, params = self.column_sql(model, new_field, include_default=True)
        fragment = (
            self.sql_create_column % {
                "table": self.quote_name(model._meta.db_table),
                "column": self.quote_name(new_field.column + "_tmp"),
                "definition": definition,
            },
            params
        )
        # ## UPDATE <table> SET 'tmp' = <orig column>
        actions.append((
            "UPDATE %(table)s SET %(new_column)s = %(old_column)s WHERE %(old_column)s IS NOT NULL" % {
                "table": model._meta.db_table,
                "new_column": self.quote_name(new_field.column + "_tmp"),
                "old_column": self.quote_name(new_field.column),
            }, []
        ))
        # ## ALTER TABLE <table> DROP COLUMN <orig column>
        actions.append((
            self.sql_delete_column % {
                "table": model._meta.db_table,
                "column": self.quote_name(new_field.column),
            }, [],
        ))
        # ## ALTER TABLE <table> RENAME COLUMN 'tmp' <orig column>
        actions.append((
            self.sql_rename_column % {
                "table": model._meta.db_table,
                "old_column": self.quote_name(new_field.column + "_tmp"),
                "new_column": self.quote_name(new_field.column),
            }, []
        ))

        return fragment, actions

    # BASED FROM https://github.com/django/django/blob/3.2.12/django/db/backends/base/schema.py#L866-L886
    # postgres/schema.py doesn't have `_alter_column_null_sql` method.
    def _alter_column_null_sqls(self, model, old_field, new_field):
        """
        Hook to specialize column null alteration.

        Return a [(sql, params), ...] fragment to set a column to null or non-null
        as required by new_field, or None if no changes are required.
        """
        # ## original BaseDatabaseSchemaEditor._alter_column_null_sql return a sql fragment
        # ## Redshift needs 4 step alter
        return self._alter_column_with_recreate(model, old_field, new_field)

    def _get_constraint(self, model, field, unique=None, primary_key=None, foreign_key=None):
        meta_constraint_names = {constraint.name for constraint in model._meta.constraints}
        constraint_names = self._constraint_names(
            model, [field.column], unique=unique, primary_key=primary_key, foreign_key=foreign_key,
            exclude=meta_constraint_names,
        )
        if not constraint_names:
            constraint_name = None
        elif len(constraint_names) == 1:
            constraint_name = constraint_names[0]
        else:
            raise ValueError("Found wrong number (%s) of unique constraints for %s.%s" % (
                len(constraint_names),
                model._meta.db_table,
                field.column,
            ))
        return constraint_name

    # override to avoid `USING %(column)s::%(type)s` on postgres/schema.py
    def _alter_column_type_sql(self, model, old_field, new_field, new_type):
        # """
        # Hook to specialize column type alteration for different backends,
        # for cases when a creation type is different to an alteration type
        # (e.g. SERIAL in PostgreSQL, PostGIS fields).

        # Return a two-tuple of: an SQL fragment of (sql, params) to insert into
        # an ALTER TABLE statement and a list of extra (sql, params) tuples to
        # run once the field is altered.
        # """
        fragment = None  # ('', [])
        actions = []

        old_db_params = old_field.db_parameters(connection=self.connection)
        old_type = old_db_params['type']

        # Default change?
        old_default = self.effective_default(old_field)
        new_default = self.effective_default(new_field)
        needs_database_default = (
            old_default != new_default and
            new_default is not None and
            not self.skip_default(new_field)
        )

        # Size change?
        def _get_max_length(field):
            if field.is_relation:
                max_length = field.foreign_related_fields[0].max_length
            else:
                max_length = field.max_length
            return max_length
        old_max_length = _get_max_length(old_field)
        new_max_length = _get_max_length(new_field)

        # Size is changed
        if (type(old_field) == type(new_field) and
                old_max_length is not None and
                new_max_length is not None and
                old_max_length != new_max_length):
            # if shrink size as `old_field.max_length > new_field.max_length` and
            # larger data in database, this change will raise exception.

            # ## Redshift can't alter column size for primary key, unique, foreign key
            # https://github.com/jazzband/django-redshift-backend/issues/96
            # https://docs.aws.amazon.com/en_us/redshift/latest/dg/r_ALTER_TABLE.html
            # another procedure to ALTER:
            #   1. once remove UNIQUE (, PKEY, FK)
            #   2. alter column
            #   3. add UNIQUE (, PKEY, FK) again

            # 0. Find the unique constraint for this field

            unique_constraint = pk_constraint = fk_constraint = None
            if old_field.unique and new_field.unique and not(old_field.primary_key or new_field.primary_key):
                unique_constraint = self._get_constraint(model, old_field, unique=True, primary_key=False)
            elif old_field.primary_key and new_field.primary_key:
                pk_constraint = self._get_constraint(model, old_field, primary_key=True)
            elif old_field.is_relation and new_field.is_relation:
                fk_constraint = self._get_constraint(model, old_field, foreign_key=True)

            # 1. once remove UNIQUE, PKEY, FK
            if unique_constraint:
                actions.append((self._delete_unique_sql(model, unique_constraint), []))
            elif pk_constraint:
                actions.append((self._delete_primary_key_sql(model, pk_constraint), []))
            elif fk_constraint:
                actions.append((self._delete_fk_sql(model, fk_constraint), []))

            # 2. alter column
            actions.append((
                self.sql_alter_column % {
                    "table": self.quote_name(model._meta.db_table),
                    "changes": self.sql_alter_column_type % {
                        "column": self.quote_name(new_field.column),
                        "type": new_type,
                    }
                },
                []
            ))
            # 3. add UNIQUE, PKEY, FK again
            if unique_constraint:
                actions.append((self._create_unique_sql(model, [new_field], unique_constraint), []))
            elif pk_constraint:
                actions.append((self._create_primary_key_sql(model, new_field), []))
            elif fk_constraint:
                actions.append((self._create_fk_sql(model, new_field, fk_constraint), []))
            fragment = actions.pop(0)

        # Type or default is changed?
        elif (old_type != new_type) or needs_database_default:
            fragment, actions = self._alter_column_with_recreate(model, old_field, new_field)

        # other case
        else:
            raise ValueError('django-redshift-backend doesnt support this alter case.')

        return fragment, actions

    def _get_create_options(self, model):
        """
        Provide options to create the table. Supports:
            - distkey
            - sortkey

        N.B.: no validation is made on these options, we'll let the Database
              do the validation for us.
        """
        def quoted_column_name(field_name):
            # We strip the '-' that may precede the field name in an `ordering`
            # specification.
            try:
                colname = model._meta.get_field(
                    field_name.strip('-')).get_attname_column()[1]
            except FieldDoesNotExist:
                # Out of an abundance of caution - e.g., so that you get a more
                # appropriate error message higher up the stack.
                colname = field_name
            return self.connection.ops.quote_name(colname)

        create_options = []

        distkey = None
        for idx in model._meta.indexes:
            if isinstance(idx, DistKey):
                if distkey:
                    raise ValueError("Model {} has more than one DistKey.".format(
                        model.__name__))
                distkey = idx
        if distkey:
            # It would be nicer to enforce this by having DistKey's ctor accept exactly
            # one field. However overriding the superclass Index ctor causes problems
            # with migrations, so we validate here instead.
            if len(distkey.fields) != 1:
                raise ValueError('DistKey on model {} must have exactly '
                                 'one field.'.format(model.__name__))
            normalized_field = quoted_column_name(distkey.fields[0])
            create_options.append("DISTKEY({})".format(normalized_field))
            # TODO: Support DISTSTYLE ALL.

        sortkeys = [
            quoted_column_name(field)
            for field in model._meta.ordering
            if isinstance(field, SortKey)
        ]
        if sortkeys:
            create_options.append("SORTKEY({fields})".format(
                fields=', '.join(sortkeys)))

        return " ".join(create_options)

    def remove_field(self, model, field):
        """
        This customization will drop the SORTKEY if the `ProgrammingError` exception
        with 'cannot drop sortkey' is raised for the 'django_content_type' table
        migration.

        Especially, django's ContentType.name field was specified as ordering and was
        used for SORTKEY on Redshift. A columns used for SORTKEY could not be dropped,
        so the ProgrammingError exception was raised. This customization will allow us
        to drop Django's ContentType.name.

        This is not strictly correct, but since Django's migration does not keep track
        of ordering changes, there is no other way to unconditionally remove SORTKEY.
        """
        try:
            super().remove_field(model, field)
        except ProgrammingError as e:
            # https://github.com/jazzband/django-redshift-backend/issues/37
            if 'cannot drop sortkey' not in str(e):
                raise

            # Reset connection if required
            if self.connection.errors_occurred:
                self.connection.close()
                self.connection.connect()

            # https://docs.aws.amazon.com/en_us/redshift/latest/dg/r_ALTER_TABLE.html
            self.execute(
                'ALTER TABLE %(table)s ALTER SORTKEY NONE;' % {
                    "table": self.quote_name(model._meta.db_table),
                }
            )
            super().remove_field(model, field)

    # backwards compatiblity for django
    # refs: https://github.com/django/django/pull/14459/files
    def _create_unique_sql(
        self, model, fields, name=None, condition=None, deferrable=None,
        include=None, opclasses=None, expressions=None,
    ):
        if django.VERSION >= (4,):
            return super()._create_unique_sql(
                model, fields, name=name, condition=condition, deferrable=deferrable,
                include=include, opclasses=opclasses, expressions=expressions
            )
        elif django.VERSION >= (3,):  # dj32 support
            columns = [
                field.column if hasattr(field, 'column') else field
                for field in fields
            ]
            return super()._create_unique_sql(
                model, columns, name=name, condition=condition, deferrable=deferrable,
                include=include, opclasses=opclasses,
            )
        else:  # dj32, dj22 support
            columns = [
                field.column if hasattr(field, 'column') else field
                for field in fields
            ]
            return super()._create_unique_sql(
                model, columns, name=name, condition=condition)


redshift_data_types = {
    "AutoField": "integer identity(1, 1)",
    "BigAutoField": "bigint identity(1, 1)",
    "TextField": "varchar(max)",  # text must be varchar(max)
    "UUIDField": "varchar(32)",  # redshift doesn't support uuid fields
}


class DatabaseCreation(BasePGDatabaseCreation):
    pass


class DatabaseIntrospection(BasePGDatabaseIntrospection):

    def get_table_description(self, cursor, table_name):
        """
        Return a description of the table with the DB-API cursor.description
        interface.
        """
        # Query the pg_catalog tables as cursor.description does not reliably
        # return the nullable property and information_schema.columns does not
        # contain details of materialized views.

        # This function is based on the version from the Django postgres backend
        # from before support for collations were introduced in Django 3.2
        # https://github.com/django/django/blob/3.1.14/django/db/backends/
        # postgresql/introspection.py#L66-L94
        cursor.execute("""
            SELECT
                a.attname AS column_name,
                NOT (a.attnotnull OR (t.typtype = 'd' AND t.typnotnull)) AS is_nullable,
                pg_get_expr(ad.adbin, ad.adrelid) AS column_default
            FROM pg_attribute a
            LEFT JOIN pg_attrdef ad ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
            JOIN pg_type t ON a.atttypid = t.oid
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE c.relkind IN ('f', 'm', 'p', 'r', 'v')
                AND c.relname = %s
                AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
                AND pg_catalog.pg_table_is_visible(c.oid)
        """, [table_name])
        # https://github.com/django/django/blob/stable/3.2.x/django/db/backends/postgresql/introspection.py#L85
        # field_map = {line[0]: line[1:] for line in cursor.fetchall()}
        field_map = {}
        for column_name, is_nullable, column_default in cursor.fetchall():
            _field_map = {
                'null_ok': is_nullable,
                'default': column_default,
            }
            if django.VERSION >= (3, 2):
                # Redshift doesn't support user-defined collation
                # https://docs.aws.amazon.com/redshift/latest/dg/c_collation_sequences.html
                _field_map['collation'] = None
            field_map[column_name] = _field_map
        cursor.execute(
            "SELECT * FROM %s LIMIT 1" % self.connection.ops.quote_name(table_name)
        )
        return [
            FieldInfo(
                name=column.name,
                type_code=column.type_code,
                display_size=column.display_size,
                internal_size=column.internal_size,
                precision=column.precision,
                scale=column.scale,
                **field_map[column.name]
            )
            for column in cursor.description
        ]

    def get_constraints(self, cursor, table_name):
        """
        Retrieve any constraints or keys (unique, pk, fk, check, index) across
        one or more columns. Also retrieve the definition of expression-based
        indexes.
        """
        # Based on code from Django 3.2
        # https://github.com/django/django/blob/3.2.12/django/db/backends/
        # postgresql/introspection.py#L148-L182
        constraints = {}
        # Loop over the key table, collecting things as constraints. The column
        # array must return column names in the same order in which they were
        # created.
        cursor.execute("""
            SELECT
                c.conname,
                c.conkey::int[],
                c.conrelid,
                c.contype,
                (SELECT fkc.relname || '.' || fka.attname
                FROM pg_attribute AS fka
                JOIN pg_class AS fkc ON fka.attrelid = fkc.oid
                WHERE fka.attrelid = c.confrelid AND fka.attnum = c.confkey[1])
            FROM pg_constraint AS c
            JOIN pg_class AS cl ON c.conrelid = cl.oid
            WHERE cl.relname = %s AND pg_catalog.pg_table_is_visible(cl.oid)
        """, [table_name])
        constraint_records = [
            (conname, conkey, conrelid, contype, used_cols) for
            (conname, conkey, conrelid, contype, used_cols) in cursor.fetchall()
        ]
        table_oid = list(constraint_records)[0][2]  # Assuming at least one constraint
        attribute_num_to_name_map = self._get_attribute_number_to_name_map_for_table(
            cursor, table_oid)

        for constraint, conkey, conrelid, kind, used_cols in constraint_records:
            constraints[constraint] = {
                "columns": [
                    attribute_num_to_name_map[column_id_int] for column_id_int in conkey
                ],
                "primary_key": kind == "p",
                "unique": kind in ["p", "u"],
                "foreign_key": tuple(used_cols.split(".", 1)) if kind == "f" else None,
                "check": kind == "c",
                "index": False,
                "definition": None,
                "options": None,
            }

        # Now get indexes
        # Based on code from Django 1.7
        # https://github.com/django/django/blob/1.7.11/django/db/backends/
        # postgresql_psycopg2/introspection.py#L182-L207
        cursor.execute("""
            SELECT
                c2.relname,
                idx.indrelid,
                idx.indkey,  -- type "int2vector", returns space-separated string
                idx.indisunique,
                idx.indisprimary
            FROM
                pg_catalog.pg_class c,
                pg_catalog.pg_class c2,
                pg_catalog.pg_index idx
            WHERE c.oid = idx.indrelid
                AND idx.indexrelid = c2.oid
                AND c.relname = %s
        """, [table_name])
        index_records = [
            (index_name, indrelid, indkey, unique, primary) for
            (index_name, indrelid, indkey, unique, primary) in cursor.fetchall()
        ]
        for index_name, indrelid, indkey, unique, primary in index_records:
            if index_name not in constraints:
                constraints[index_name] = {
                    "columns": [
                        attribute_num_to_name_map[int(column_id_str)]
                        for column_id_str in indkey.split(' ')
                    ],
                    "orders": [],  # Not implemented
                    "primary_key": primary,
                    "unique": unique,
                    "foreign_key": None,
                    "check": False,
                    "index": True,
                    "type": Index.suffix,  # Not implemented - assume default type
                    "definition": None,  # Not implemented
                    "options": None,  # Not implemented
                }

        return constraints

    def _get_attribute_number_to_name_map_for_table(self, cursor, table_oid):
        cursor.execute("""
            SELECT
                attrelid,  -- table oid
                attnum,
                attname
            FROM pg_attribute
            WHERE pg_attribute.attrelid = %s
            ORDER BY attrelid, attnum;
        """, [table_oid])
        return {
            attnum: attname
            for _, attnum, attname in cursor.fetchall()
        }

    # BASED FROM https://github.com/django/django/blob/3.2.12/django/db/backends/postgresql/introspection.py#L47-L58
    # Django 4.0 drop old postgres support: https://github.com/django/django/commit/5371342
    def get_table_list(self, cursor):
        """Return a list of table and view names in the current database."""
        cursor.execute("""
            SELECT c.relname,
            CASE WHEN c.relkind IN ('m', 'v') THEN 'v' ELSE 't' END
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('f', 'm', 'p', 'r', 'v')
                AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
                AND pg_catalog.pg_table_is_visible(c.oid)
        """)
        return [TableInfo(*row) for row in cursor.fetchall() if row[0] not in self.ignored_tables]


class DatabaseWrapper(BasePGDatabaseWrapper):
    vendor = 'redshift'

    SchemaEditorClass = DatabaseSchemaEditor

    data_types = deepcopy(BasePGDatabaseWrapper.data_types)
    data_types.update(redshift_data_types)

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        self.features = DatabaseFeatures(self)
        self.ops = DatabaseOperations(self)
        self.client = DatabaseClient(self)
        self.creation = DatabaseCreation(self)
        self.introspection = DatabaseIntrospection(self)
        self.validation = BaseDatabaseValidation(self)

    def check_constraints(self, table_names=None):
        """
        No constraints to check in Redshift.
        """
        pass
