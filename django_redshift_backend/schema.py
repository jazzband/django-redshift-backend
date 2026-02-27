import re

import psycopg2

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.ddl_references import Statement
from django.db.models import Index
from django.db.utils import NotSupportedError, ProgrammingError
from django.utils import timezone

from psycopg2.extensions import Binary

from .meta import DistKey, SortKey
from .psycopg2adapter import RedshiftBinary


def _get_type_default(field):
    internal_type = field.get_internal_type()
    if internal_type in ("CharField", "SlugField"):
        default = ""
    elif internal_type == "BinaryField":
        default = b""
    elif internal_type == "FloatField":
        default = 0.0
    elif internal_type in (
        "BigAutoField",
        "IntegerField",
        "BigIntegerField",
        "PositiveBigIntegerField",
        "PositiveIntegerField",
        "PositiveSmallIntegerField",
        "SmallAutoField",
        "SmallIntegerField",
        "DecimalField",
    ):
        default = 0
    elif internal_type == "BooleanField":
        default = False
    elif internal_type == "DateField":
        default = timezone.date()
    elif internal_type == "TimeField":
        default = timezone.time()
    elif internal_type == "DateTimeField":
        default = timezone.now()
    else:
        default = None
    return default


def _remove_length_from_type(column_type):
    return re.sub(r"\(.*", "", column_type)


def _is_relevant_relation(relation, altered_field):
    """
    When altering the given field, must constraints on its model from the given
    relation be temporarily dropped?
    """
    field = token = relation.field
    while field.is_relation:
        field = field.related_fields[0][1]
        if field is altered_field:
            return True
        if token is field:
            break
        token = field
    return False


def _related_non_m2m_objects(old_field, new_field):
    # Filter out m2m objects from related objects.
    # Return (old_relation, new_relation) tuples.
    return zip(
        (
            obj
            for obj in old_field.model._meta.related_objects
            if _is_relevant_relation(obj, old_field)
        ),
        (
            obj
            for obj in new_field.model._meta.related_objects
            if _is_relevant_relation(obj, new_field)
        ),
    )


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    sql_create_table = "CREATE TABLE %(table)s (%(definition)s) %(options)s"
    sql_delete_fk = "ALTER TABLE %(table)s DROP CONSTRAINT %(name)s"

    def quote_value(self, value):
        if isinstance(value, str):
            value = value.replace("%", "%%")
        adapted = psycopg2.extensions.adapt(value)
        if hasattr(adapted, "encoding"):
            adapted.encoding = "utf8"
        # getquoted() returns a quoted bytestring of the adapted value.
        return adapted.getquoted().decode()

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

    def column_sql(self, *args, **kwargs):
        definition, params = super().column_sql(*args, **kwargs)
        params = self._modify_params_for_redshift(params)
        return definition, params

    def _modify_params_for_redshift(self, params):
        """
        Convert psycopg2 Binary instances to RedshiftBinary instances so that
        binary columns use `to_varbyte('hex', 'hex')::varbyte` instead of `::bytea`.
        """
        new_params = [
            RedshiftBinary(p.adapted) if isinstance(p, Binary) else p for p in params
        ]
        return new_params

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
            m = re.match(r"varchar\((\d+?)\)", definition)
            if m:
                definition = re.sub(
                    r"varchar\((\d+?)\)",
                    "varchar({})".format(
                        str(int(m.group(1)) * self.multiply_varchar_length)
                    ),
                    definition,
                )

            field.db_parameters(connection=self.connection)
            # Autoincrement SQL (for backends with inline variant)
            col_type_suffix = field.db_type_suffix(connection=self.connection)
            if col_type_suffix:
                definition += " %s" % col_type_suffix
            params.extend(extra_params)
            # FK
            if field.remote_field and field.db_constraint:
                to_table = field.remote_field.model._meta.db_table
                to_column = field.remote_field.model._meta.get_field(
                    field.remote_field.field_name
                ).column
                if self.connection.features.supports_foreign_keys:
                    self.deferred_sql.append(
                        self._create_fk_sql(
                            model, field, "_fk_%(to_table)s_%(to_column)s"
                        )
                    )
                elif self.sql_create_inline_fk:
                    definition += " " + self.sql_create_inline_fk % {
                        "to_table": self.quote_name(to_table),
                        "to_column": self.quote_name(to_column),
                    }
            # Add the SQL to our big list
            column_sqls.append(
                "%s %s"
                % (
                    self.quote_name(field.column),
                    definition,
                )
            )
            # Autoincrement SQL (for backends with post table definition variant)
            if field.get_internal_type() in ("AutoField", "BigAutoField"):
                autoinc_sql = self.connection.ops.autoinc_sql(
                    model._meta.db_table, field.column
                )
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
            "options": self._get_create_options(model),
        }
        if model._meta.db_tablespace:
            tablespace_sql = self.connection.ops.tablespace_sql(
                model._meta.db_tablespace
            )
            if tablespace_sql:
                sql += " " + tablespace_sql
        # Prevent using [] as params, in the case a literal '%' is used in the definition
        self.execute(sql, params or None)

        # Add any field index and index_together's
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
        if field.unique:
            # temporarily remove UNIQUE constraint from sql
            # because Redshift can't add column with UNIQUE constraint.
            sql = sql.rstrip(" UNIQUE")

        # ## Redshift
        if not field.null and self.effective_default(field) is None:
            # Redshift Can't add NOT NULL column without DEFAULT.
            raise ProgrammingError(sql % params)
        self.execute(sql, params)

        # ## original BasePGDatabaseSchemaEditor.add_field drop default here
        # ## Redshift doesn't support DROP DEFAULT.

        # ## original BasePGDatabaseSchemaEditor.add_field has CREATE INDEX.
        # ## Redshift doesn't support INDEX.

        # Add UNIQUE constraints later
        if field.unique:
            self.deferred_sql.append(self._create_unique_sql(model, [field]))

        # Add any FK constraints later
        if (
            field.remote_field
            and self.connection.features.supports_foreign_keys
            and field.db_constraint
        ):
            self.deferred_sql.append(
                self._create_fk_sql(model, field, "_fk_%(to_table)s_%(to_column)s")
            )
        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    # BASED FROM https://github.com/django/django/blob/3.2.12/django/db/backends/base/schema.py#L611-L864
    def _alter_field(
        self,
        model,
        old_field,
        new_field,
        old_type,
        new_type,
        old_db_params,
        new_db_params,
        strict=False,
    ):
        """Perform a "physical" (non-ManyToMany) field update."""
        # Drop any FK constraints, we'll remake them later
        fks_dropped = set()
        if (
            self.connection.features.supports_foreign_keys
            and old_field.remote_field
            and old_field.db_constraint
        ):
            fk_names = self._constraint_names(
                model, [old_field.column], foreign_key=True
            )
            if strict and len(fk_names) != 1:
                raise ValueError(
                    "Found wrong number (%s) of foreign key constraints for %s.%s"
                    % (
                        len(fk_names),
                        model._meta.db_table,
                        old_field.column,
                    )
                )
            for fk_name in fk_names:
                fks_dropped.add((old_field.column,))
                self.execute(self._delete_fk_sql(model, fk_name))
        # Has unique been removed?
        if old_field.unique and (
            not new_field.unique or self._field_became_primary_key(old_field, new_field)
        ):
            # Find the unique constraint for this field
            meta_constraint_names = {
                constraint.name for constraint in model._meta.constraints
            }
            constraint_names = self._constraint_names(
                model,
                [old_field.column],
                unique=True,
                primary_key=False,
                exclude=meta_constraint_names,
            )
            if strict and len(constraint_names) != 1:
                raise ValueError(
                    "Found wrong number (%s) of unique constraints for %s.%s"
                    % (
                        len(constraint_names),
                        model._meta.db_table,
                        old_field.column,
                    )
                )
            for constraint_name in constraint_names:
                self.execute(self._delete_unique_sql(model, constraint_name))
        # Drop incoming FK constraints if the field is a primary key or unique,
        # which might be a to_field target, and things are going to change.
        drop_foreign_keys = (
            self.connection.features.supports_foreign_keys
            and (
                (old_field.primary_key and new_field.primary_key)
                or (old_field.unique and new_field.unique)
            )
            and old_type != new_type
        )
        if drop_foreign_keys:
            for _old_rel, new_rel in _related_non_m2m_objects(old_field, new_field):
                rel_fk_names = self._constraint_names(
                    new_rel.related_model, [new_rel.field.column], foreign_key=True
                )
                for fk_name in rel_fk_names:
                    self.execute(self._delete_fk_sql(new_rel.related_model, fk_name))
        # Removed an index?
        if (
            old_field.db_index
            and not old_field.unique
            and (not new_field.db_index or new_field.unique)
        ):
            meta_index_names = {index.name for index in model._meta.indexes}
            index_names = self._constraint_names(
                model,
                [old_field.column],
                index=True,
                type_=Index.suffix,
                exclude=meta_index_names,
            )
            for index_name in index_names:
                self.execute(self._delete_index_sql(model, index_name))
        # Change check constraints?
        if old_db_params["check"] != new_db_params["check"] and old_db_params["check"]:
            meta_constraint_names = {
                constraint.name for constraint in model._meta.constraints
            }
            constraint_names = self._constraint_names(
                model,
                [old_field.column],
                check=True,
                exclude=meta_constraint_names,
            )
            if strict and len(constraint_names) != 1:
                raise ValueError(
                    "Found wrong number (%s) of check constraints for %s.%s"
                    % (
                        len(constraint_names),
                        model._meta.db_table,
                        old_field.column,
                    )
                )
            for constraint_name in constraint_names:
                self.execute(self._delete_check_sql(model, constraint_name))
        # Have they renamed the column?
        if old_field.column != new_field.column:
            self.execute(
                self._rename_field_sql(
                    model._meta.db_table, old_field, new_field, new_type
                )
            )
            # Rename all references to the renamed column.
            for sql in self.deferred_sql:
                if isinstance(sql, Statement):
                    sql.rename_column_references(
                        model._meta.db_table, old_field.column, new_field.column
                    )
        # Next, start accumulating actions to do
        actions = []
        null_actions = []
        post_actions = []
        # Collation change?
        old_collation = getattr(old_field, "db_collation", None)
        new_collation = getattr(new_field, "db_collation", None)
        if old_collation != new_collation:
            # Collation change handles also a type change.
            fragment = self._alter_column_collation_sql(
                model, new_field, new_type, new_collation
            )
            actions.append(fragment)
        # Type change?
        elif old_type != new_type:
            fragment, other_actions = self._alter_column_type_sql(
                model, old_field, new_field, new_type, old_collation, new_collation
            )
            if fragment:  # ## Redshift: In some case, fragment will be empty.
                actions.append(fragment)
            post_actions.extend(other_actions)

        # Default change?
        # ## Redshift Can't ALTER COLUMN SET/DROP DEFAULT.
        # four_way_default_alteration is always False for Redshift
        four_way_default_alteration = False
        new_default = self.effective_default(new_field)  # not used, but for flake8

        # Nullability change?
        if old_field.null != new_field.null:
            # ## Redshift use 4 steps null alternation
            fragment, other_actions = self._alter_column_null_sqls(
                model, old_field, new_field
            )
            actions.append(fragment)
            null_actions.extend(other_actions)

        if actions or null_actions:
            if not four_way_default_alteration:
                actions = actions + null_actions
            # Combine actions together if we can (e.g. postgres)
            if self.connection.features.supports_combined_alters and actions:
                sql, params = tuple(zip(*actions))
                actions = [(", ".join(sql), sum(params, []))]
            # Apply those actions
            for sql, params in actions:
                # ## Redshift executes ADD and UPDATE on alter, so the sql is a complete sentence
                self.execute(sql, params)
            if four_way_default_alteration:
                # Update existing rows with default value
                self.execute(
                    self.sql_update_with_default
                    % {
                        "table": self.quote_name(model._meta.db_table),
                        "column": self.quote_name(new_field.column),
                        "default": "%s",
                    },
                    [new_default],
                )
                for sql, params in null_actions:
                    self.execute(
                        self.sql_alter_column
                        % {
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
        # Added an index?
        # ## Redshift doesn't support INDEX.

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
            rel_type = rel_db_params["type"]
            old_collation = getattr(old_rel.field, "db_collation", None)
            new_collation = getattr(new_rel.field, "db_collation", None)
            fragment, other_actions = self._alter_column_type_sql(
                new_rel.related_model,
                old_rel.field,
                new_rel.field,
                rel_type,
                old_collation,
                new_collation,
            )
            # ## Redshift executes ADD and UPDATE on alter, so the fragment[0] is a complete sentence
            self.execute(fragment[0], fragment[1])
            for sql, params in other_actions:
                self.execute(sql, params)
        # Does it have a foreign key?
        if (
            self.connection.features.supports_foreign_keys
            and new_field.remote_field
            and (
                fks_dropped or not old_field.remote_field or not old_field.db_constraint
            )
            and new_field.db_constraint
        ):
            self.execute(
                self._create_fk_sql(model, new_field, "_fk_%(to_table)s_%(to_column)s")
            )
        # Rebuild FKs that pointed to us if we previously had to drop them
        if drop_foreign_keys:
            for rel in new_field.model._meta.related_objects:
                if _is_relevant_relation(rel, new_field) and rel.field.db_constraint:
                    self.execute(
                        self._create_fk_sql(rel.related_model, rel.field, "_fk")
                    )
        # Does it have check constraints we need to add?
        if old_db_params["check"] != new_db_params["check"] and new_db_params["check"]:
            constraint_name = self._create_index_name(
                model._meta.db_table, [new_field.column], suffix="_check"
            )
            self.execute(
                self._create_check_sql(model, constraint_name, new_db_params["check"])
            )

        # ## Redshift doesn't support DROP DEFAULT.

        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    def _alter_column_with_recreate(self, model, old_field, new_field):
        """
        To change column type or default, We need this migration sequence:

        1. Add new column with temporary name
        2. Migrate values from original column to temporary column
        3. Drop old column
        4. Rename temporary column name to original column name
        """
        # Avoid circular import
        from .base import DatabaseWrapper

        fragment = ("", [])
        actions = []

        # ## ALTER TABLE <table> ADD COLUMN 'tmp' <type> DEFAULT <value>
        if not new_field.null and not new_field.has_default():
            default = _get_type_default(new_field)
            if default is None:
                raise ValueError(
                    "django-redshift-backend doesn't know default for the type: {}".format(
                        new_field.get_internal_type()
                    )
                )
            new_field.default = default

        definition, params = self.column_sql(model, new_field, include_default=True)
        fragment = (
            self.sql_create_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self.quote_name(new_field.column + "_tmp"),
                "definition": definition,
            },
            params,
        )

        type_cast = ""
        if new_field.get_internal_type() == "BinaryField":
            type_cast = "::" + _remove_length_from_type(
                DatabaseWrapper.data_types["BinaryField"]
            )
        elif (
            old_field.get_internal_type() == "BinaryField"
            and new_field.get_internal_type() == "CharField"
        ):
            type_cast = "::" + _remove_length_from_type(
                DatabaseWrapper.data_types["CharField"]
            )

        # ## UPDATE <table> SET 'tmp' = <orig column>
        actions.append(
            (
                "UPDATE %(table)s SET %(new_column)s = %(old_column)s%(cast)s WHERE %(old_column)s IS NOT NULL"
                % {
                    "table": model._meta.db_table,
                    "new_column": self.quote_name(new_field.column + "_tmp"),
                    "old_column": self.quote_name(new_field.column),
                    "cast": type_cast,
                },
                [],
            )
        )
        # ## ALTER TABLE <table> DROP COLUMN <orig column>
        actions.append(
            (
                self.sql_delete_column
                % {
                    "table": model._meta.db_table,
                    "column": self.quote_name(new_field.column),
                },
                [],
            )
        )
        # ## ALTER TABLE <table> RENAME COLUMN 'tmp' <orig column>
        actions.append(
            (
                self.sql_rename_column
                % {
                    "table": model._meta.db_table,
                    "old_column": self.quote_name(new_field.column + "_tmp"),
                    "new_column": self.quote_name(new_field.column),
                },
                [],
            )
        )

        return fragment, actions

    def _alter_column_null_sqls(self, model, old_field, new_field):
        """
        Hook to specialize column null alteration.
        Return a [(sql, params), ...] fragment to set a column to null or non-null.
        ## Redshift needs 4 step alter
        """
        return self._alter_column_with_recreate(model, old_field, new_field)

    def _get_constraint(
        self, model, field, unique=None, primary_key=None, foreign_key=None
    ):
        meta_constraint_names = {
            constraint.name for constraint in model._meta.constraints
        }
        constraint_names = self._constraint_names(
            model,
            [field.column],
            unique=unique,
            primary_key=primary_key,
            foreign_key=foreign_key,
            exclude=meta_constraint_names,
        )
        if not constraint_names:
            constraint_name = None
        elif len(constraint_names) == 1:
            constraint_name = constraint_names[0]
        else:
            raise ValueError(
                "Found wrong number (%s) of unique constraints for %s.%s"
                % (
                    len(constraint_names),
                    model._meta.db_table,
                    field.column,
                )
            )
        return constraint_name

    # override to avoid `USING %(column)s::%(type)s` on postgres/schema.py
    def _alter_column_type_sql(
        self, model, old_field, new_field, new_type, old_collation, new_collation
    ):
        fragment = None
        actions = []

        old_db_params = old_field.db_parameters(connection=self.connection)
        old_type = old_db_params["type"]

        # Default change?
        old_default = self.effective_default(old_field)
        new_default = self.effective_default(new_field)
        needs_database_default = (
            old_default != new_default
            and new_default is not None
            and not self.skip_default(new_field)
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
        decrease_size_with_default = old_default is not None and (
            old_max_length > new_max_length
        )

        # Size is changed
        if (
            type(old_field) is type(new_field)
            and old_max_length is not None
            and new_max_length is not None
            and old_max_length != new_max_length
            and not decrease_size_with_default
        ):
            # ## Redshift can't alter column size for primary key, unique, foreign key
            # another procedure to ALTER:
            #   1. once remove UNIQUE (, PKEY, FK)
            #   2. alter column
            #   3. add UNIQUE (, PKEY, FK) again

            # 0. Find the unique constraint for this field
            unique_constraint = pk_constraint = fk_constraint = None
            if (
                old_field.unique
                and new_field.unique
                and not (old_field.primary_key or new_field.primary_key)
            ):
                unique_constraint = self._get_constraint(
                    model, old_field, unique=True, primary_key=False
                )
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
            actions.append(
                (
                    self.sql_alter_column
                    % {
                        "table": self.quote_name(model._meta.db_table),
                        "changes": self.sql_alter_column_type
                        % {
                            "column": self.quote_name(new_field.column),
                            "type": new_type,
                            "collation": "",
                        },
                    },
                    [],
                )
            )
            # 3. add UNIQUE, PKEY, FK again
            if unique_constraint:
                actions.append(
                    (self._create_unique_sql(model, [new_field], unique_constraint), [])
                )
            elif pk_constraint:
                actions.append((self._create_primary_key_sql(model, new_field), []))
            elif fk_constraint:
                actions.append(
                    (self._create_fk_sql(model, new_field, fk_constraint), [])
                )
            fragment = actions.pop(0)

        # Type or default is changed?
        elif (
            (old_type != new_type)
            or needs_database_default
            or decrease_size_with_default
        ):
            fragment, actions = self._alter_column_with_recreate(
                model, old_field, new_field
            )

        # other case
        else:
            raise ValueError("django-redshift-backend doesnt support this alter case.")

        return fragment, actions

    def _get_create_options(self, model):
        """
        Provide options to create the table. Supports:
            - distkey
            - sortkey
        """

        def quoted_column_name(field_name):
            try:
                colname = model._meta.get_field(
                    field_name.strip("-")
                ).get_attname_column()[1]
            except FieldDoesNotExist:
                colname = field_name
            return self.connection.ops.quote_name(colname)

        create_options = []

        distkey = None
        for idx in model._meta.indexes:
            if isinstance(idx, DistKey):
                if distkey:
                    raise ValueError(
                        f"Model {model.__name__} has more than one DistKey."
                    )
                distkey = idx
        if distkey:
            if len(distkey.fields) != 1:
                raise ValueError(
                    "DistKey on model {} must have exactly one field.".format(
                        model.__name__
                    )
                )
            normalized_field = quoted_column_name(distkey.fields[0])
            create_options.append(f"DISTKEY({normalized_field})")
            # TODO: Support DISTSTYLE ALL.

        sortkeys = [
            quoted_column_name(field)
            for field in model._meta.ordering
            if isinstance(field, SortKey)
        ]
        if sortkeys:
            create_options.append(
                "SORTKEY({fields})".format(fields=", ".join(sortkeys))
            )

        return " ".join(create_options)

    def remove_field(self, model, field):
        """
        Drop the SORTKEY if the ProgrammingError exception with
        'cannot drop sortkey' is raised.
        """
        try:
            super().remove_field(model, field)
        except ProgrammingError as e:
            if "cannot drop sortkey" not in str(e):
                raise

            # Reset connection if required
            if self.connection.errors_occurred:
                self.connection.close()
                self.connection.connect()

            self.execute(
                "ALTER TABLE %(table)s ALTER SORTKEY NONE;"
                % {
                    "table": self.quote_name(model._meta.db_table),
                }
            )
            super().remove_field(model, field)
