"""
Redshift database backend for Django based upon django PostgreSQL backend.

Requires psycopg 2: http://initd.org/projects/psycopg2
"""
from __future__ import absolute_import

from copy import deepcopy
import re
import logging

import django
from django.conf import settings
from django.db.backends.postgresql_psycopg2.base import (
    DatabaseFeatures as BasePGDatabaseFeatures,
    DatabaseWrapper as BasePGDatabaseWrapper,
    DatabaseOperations as BasePGDatabaseOperations,
    DatabaseSchemaEditor as BasePGDatabaseSchemaEditor,
    DatabaseClient,
    DatabaseCreation as BasePGDatabaseCreation,
    DatabaseIntrospection,
    BaseDatabaseValidation,
)

logger = logging.getLogger('django.db.backends')


class DatabaseFeatures(BasePGDatabaseFeatures):
    can_return_id_from_insert = False
    has_select_for_update = False


class DatabaseOperations(BasePGDatabaseOperations):

    def last_insert_id(self, cursor, table_name, pk_name):
        cursor.execute('SELECT MAX({pk}) from {table}'.format(
            pk=pk_name, table=self.quote_name(table_name)))
        return cursor.fetchone()[0]

    def for_update_sql(self, nowait=False):
        raise NotImplementedError(
            'SELECT FOR UPDATE is not implemented for this database backend')

    def deferrable_sql(self):
        # unused
        return ""

    def sequence_reset_sql(self, style, model_list):
        # impossible with Redshift to reset a sequence
        return []


def _related_non_m2m_objects(old_field, new_field):
    # Filters out m2m objects from reverse relations.
    # Returns (old_relation, new_relation) tuples.
    return zip(
        (obj
         for obj in old_field.model._meta.related_objects
         if not obj.field.many_to_many),
        (obj
         for obj in new_field.model._meta.related_objects
         if not obj.field.many_to_many)
    )


class DatabaseSchemaEditor(BasePGDatabaseSchemaEditor):

    @property
    def multiply_varchar_length(self):
        return int(getattr(settings, "REDSHIFT_VARCHAR_LENGTH_MULTIPLIER", 1))

    def _model_indexes_sql(self, model):
        # Redshift doesn't support INDEX.
        return []

    def _create_like_index_sql(self, model, field):
        # Redshift doesn't support INDEX.
        return None

    def alter_index_together(self, model, old_index_together, new_index_together):
        # Redshift doesn't support INDEX.
        return

    def _create_index_sql(self, model, fields, suffix="", sql=None):
        raise NotImplementedError("Redshift doesn't support INDEX")

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
            m = re.match('varchar\((\d+?)\)', definition)
            if m:
                definition = re.sub(
                    'varchar\((\d+?)\)',
                    "varchar({0})".format(
                        str(int(m.group(1)) * self.multiply_varchar_length)),
                    definition)

            # Check constraints can go on the column SQL here
            db_params = field.db_parameters(connection=self.connection)
            if db_params['check']:
                definition += " CHECK (%s)" % db_params['check']
            # Autoincrement SQL (for backends with inline variant)
            col_type_suffix = field.db_type_suffix(connection=self.connection)
            if col_type_suffix:
                definition += " %s" % col_type_suffix
            params.extend(extra_params)
            # FK
            if field.rel and field.db_constraint:
                to_table = field.rel.to._meta.db_table
                to_column = field.rel.to._meta.get_field(field.rel.field_name).column
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
            if field.get_internal_type() == "AutoField":
                autoinc_sql = self.connection.ops.autoinc_sql(
                    model._meta.db_table, field.column)
                if autoinc_sql:
                    self.deferred_sql.extend(autoinc_sql)

        # Add any unique_togethers
        for fields in model._meta.unique_together:
            columns = [model._meta.get_field(field).column for field in fields]
            column_sqls.append(self.sql_create_table_unique % {
                "columns": ", ".join(self.quote_name(column) for column in columns),
            })
        # Make the table
        sql = self.sql_create_table % {
            "table": self.quote_name(model._meta.db_table),
            "definition": ", ".join(column_sqls)
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
            if field.rel.through._meta.auto_created:
                self.create_model(field.rel.through)

    def add_field(self, model, field):
        """
        Creates a field on a model.
        Usually involves adding a column, but may involve adding a
        table instead (for M2M fields)
        """
        # Special-case implicit M2M tables
        if field.many_to_many and field.rel.through._meta.auto_created:
            return self.create_model(field.rel.through)

        # Get the column's definition
        # ## To add column to existent table on Redshift, field.null must be allowed
        field.null = True
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
        self.execute(sql, params)

        # ## original BasePGDatabaseSchemaEditor.add_field drop default here
        # ## Redshift doesn't support DROP DEFAULT.

        # ## original BasePGDatabaseSchemaEditor.add_field has CREATE INDEX.
        # ## Redshift doesn't support INDEX.

        # Add any FK constraints later
        if (field.rel and
                self.connection.features.supports_foreign_keys and
                field.db_constraint):
            self.deferred_sql.append(
                self._create_fk_sql(model, field, "_fk_%(to_table)s_%(to_column)s"))
        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    def _alter_field(self, model, old_field, new_field, old_type, new_type,
                     old_db_params, new_db_params, strict=False):
        """Actually perform a "physical" (non-ManyToMany) field update."""

        # Drop any FK constraints, we'll remake them later
        fks_dropped = set()
        if old_field.rel and old_field.db_constraint:
            fk_names = self._constraint_names(model, [old_field.column], foreign_key=True)
            if strict and len(fk_names) != 1:
                raise ValueError(
                    "Found wrong number (%s) of foreign key constraints for %s.%s" %
                    (len(fk_names), model._meta.db_table, old_field.column))
            for fk_name in fk_names:
                fks_dropped.add((old_field.column,))
                self.execute(self._delete_constraint_sql(
                    self.sql_delete_fk, model, fk_name))
        # Has unique been removed?
        if (old_field.unique and
                (not new_field.unique or
                 (not old_field.primary_key and new_field.primary_key))):
            # Find the unique constraint for this field
            constraint_names = self._constraint_names(
                model, [old_field.column], unique=True)
            if strict and len(constraint_names) != 1:
                raise ValueError(
                    "Found wrong number (%s) of unique constraints for %s.%s" %
                    (len(constraint_names), model._meta.db_table, old_field.column))
            for constraint_name in constraint_names:
                self.execute(self._delete_constraint_sql(
                    self.sql_delete_unique, model, constraint_name))
        # Drop incoming FK constraints if we're a primary key and things are going
        # to change.
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            # '_meta.related_field' also contains M2M reverse fields, these
            # will be filtered out
            for _old_rel, new_rel in _related_non_m2m_objects(old_field, new_field):
                rel_fk_names = self._constraint_names(
                    new_rel.related_model, [new_rel.field.column], foreign_key=True
                )
                for fk_name in rel_fk_names:
                    self.execute(self._delete_constraint_sql(
                        self.sql_delete_fk, new_rel.related_model, fk_name))
        # Removed an index? (no strict check, as multiple indexes are possible)
        if (old_field.db_index and
                not new_field.db_index and
                not old_field.unique and
                not (not new_field.unique and old_field.unique)):
            # Find the index for this field
            index_names = self._constraint_names(model, [old_field.column], index=True)
            for index_name in index_names:
                self.execute(self._delete_constraint_sql(
                    self.sql_delete_index, model, index_name))
        # Change check constraints?
        if old_db_params['check'] != new_db_params['check'] and old_db_params['check']:
            constraint_names = self._constraint_names(
                model, [old_field.column], check=True)
            if strict and len(constraint_names) != 1:
                raise ValueError(
                    "Found wrong number (%s) of check constraints for %s.%s" %
                    (len(constraint_names), model._meta.db_table, old_field.column))
            for constraint_name in constraint_names:
                self.execute(self._delete_constraint_sql(
                    self.sql_delete_check, model, constraint_name))
        # Have they renamed the column?
        if old_field.column != new_field.column:
            self.execute(self._rename_field_sql(
                model._meta.db_table, old_field, new_field, new_type))
        # Next, start accumulating actions to do
        actions = []
        post_actions = []

        # When changing a column NULL constraint to NOT NULL with a given
        # default value, we need to perform 4 steps:
        #  1. Add a default for new incoming writes
        #  2. Update existing NULL rows with new default
        #  3. Replace NULL constraint with NOT NULL
        #  4. Drop the default again.
        # Default change?
        old_default = self.effective_default(old_field)
        new_default = self.effective_default(new_field)
        needs_database_default = (
            old_default != new_default and
            new_default is not None and
            not self.skip_default(new_field)
        )
        # Type or default is changed?
        if (old_type != new_type) or needs_database_default:
            # ## To change column type or default, We need this migration sequence:
            # ##
            # ## 1. Add new column with temporary name
            # ## 2. Migrate values from original column to temprary column
            # ## 3. Drop old column
            # ## 4. Rename temporary column name to original column name

            # ## ALTER TABLE <table> ADD COLUMN 'tmp' <type> DEFAULT <value>
            definition, params = self.column_sql(model, new_field, include_default=True)
            actions.append((
                self.sql_create_column % {
                    "table": self.quote_name(model._meta.db_table),
                    "column": self.quote_name(new_field.column + "_tmp"),
                    "definition": definition,
                },
                [new_default]
            ))
            # ## UPDATE <table> SET 'tmp' = <orig column>
            actions.append((
                "UPDATE %(table)s SET %(new_column)s = %(old_column)s" % {
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

        # Apply those actions
        for sql, params in actions:
            self.execute(sql, params)
        if post_actions:
            for sql, params in post_actions:
                self.execute(sql, params)
        # Added a unique?
        if ((not old_field.unique and new_field.unique) or
           (old_field.primary_key and not new_field.primary_key and new_field.unique)):
            self.execute(self._create_unique_sql(model, [new_field.column]))

        # ## original BasePGDatabaseSchemaEditor._alter_field has CREATE INDEX
        # ## Redshift doesn't support it.

        # Type alteration on primary key? Then we need to alter the column
        # referring to us.
        rels_to_update = []
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            rels_to_update.extend(_related_non_m2m_objects(old_field, new_field))
        # Changed to become primary key?
        # Note that we don't detect unsetting of a PK, as we assume another field
        # will always come along and replace it.
        if not old_field.primary_key and new_field.primary_key:
            # First, drop the old PK
            constraint_names = self._constraint_names(model, primary_key=True)
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of PK constraints for %s" % (
                    len(constraint_names),
                    model._meta.db_table,
                ))
            for constraint_name in constraint_names:
                self.execute(self._delete_constraint_sql(
                    self.sql_delete_pk, model, constraint_name))
            # Make the new one
            self.execute(
                self.sql_create_pk % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self.quote_name(self._create_index_name(
                        model, [new_field.column], suffix="_pk")),
                    "columns": self.quote_name(new_field.column),
                }
            )
            # Update all referencing columns
            rels_to_update.extend(_related_non_m2m_objects(old_field, new_field))
        # Handle our type alters on the other end of rels from the PK stuff above
        for old_rel, new_rel in rels_to_update:
            rel_db_params = new_rel.field.db_parameters(connection=self.connection)
            rel_type = rel_db_params['type']
            fragment, other_actions = self._alter_column_type_sql(
                new_rel.related_model._meta.db_table, old_rel.field, new_rel.field,
                rel_type
            )
            self.execute(
                self.sql_alter_column % {
                    "table": self.quote_name(new_rel.related_model._meta.db_table),
                    "changes": fragment[0],
                },
                fragment[1],
                )
            for sql, params in other_actions:
                self.execute(sql, params)
        # Does it have a foreign key?
        if (new_field.rel and
                (fks_dropped or not old_field.rel or not old_field.db_constraint) and
                new_field.db_constraint):
            self.execute(self._create_fk_sql(
                model, new_field, "_fk_%(to_table)s_%(to_column)s"))
        # Rebuild FKs that pointed to us if we previously had to drop them
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            for rel in new_field.model._meta.related_objects:
                if not rel.many_to_many:
                    self.execute(self._create_fk_sql(
                        rel.related_model, rel.field, "_fk"))
        # Does it have check constraints we need to add?
        if old_db_params['check'] != new_db_params['check'] and new_db_params['check']:
            self.execute(
                self.sql_create_check % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self.quote_name(self._create_index_name(
                        model, [new_field.column], suffix="_check")),
                    "column": self.quote_name(new_field.column),
                    "check": new_db_params['check'],
                }
            )

        # ## original BasePGDatabaseSchemaEditor._alter_field drop default here
        # ## Redshift doesn't support DROP DEFAULT.

        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()


redshift_data_types = {
    "AutoField": "integer identity(1, 1)",
    "DateTimeField": "timestamp",
    "TextField": "varchar(max)",  # text must be varchar(max)
}


class DatabaseCreation(BasePGDatabaseCreation):

    if django.VERSION < (1, 8):
        data_types = deepcopy(BasePGDatabaseCreation.data_types)
        data_types.update(redshift_data_types)


class DatabaseWrapper(BasePGDatabaseWrapper):
    vendor = 'redshift'

    SchemaEditorClass = DatabaseSchemaEditor

    if django.VERSION >= (1, 8):
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

    def check_constraints(self, table_names=None):
        """
        No constraints to check in Redsfhift.
        """
        pass
