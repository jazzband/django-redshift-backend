import warnings

from django.db import NotSupportedError
from django.db.models.sql.compiler import (
    SQLAggregateCompiler,
    SQLCompiler,
    SQLDeleteCompiler,
    SQLInsertCompiler,
    SQLUpdateCompiler,
)
from django.db.transaction import TransactionManagementError
from django.db.utils import NotSupportedError
from django.utils.deprecation import RemovedInDjango31Warning


class SQLCompiler(SQLCompiler):
    def as_sql(self, with_limits=True, with_col_aliases=False):
        """
        Create the SQL for this query. Return the SQL string and list of
        parameters.
        If 'with_limits' is False, any limit/offset information is not included
        in the query.
        """
        refcounts_before = self.query.alias_refcount.copy()
        try:
            extra_select, order_by, group_by = self.pre_sql_setup()
            for_update_part = None
            # Is a LIMIT/OFFSET clause needed?
            with_limit_offset = with_limits and (
                self.query.high_mark is not None or self.query.low_mark
            )
            combinator = self.query.combinator
            features = self.connection.features
            if combinator:
                if not getattr(
                    features, 'supports_select_{}'.format(combinator)
                ):
                    raise NotSupportedError(
                        '{} is not supported on this database backend.'.format(
                            combinator
                        )
                    )
                result, params = self.get_combinator_sql(
                    combinator, self.query.combinator_all
                )
            else:
                distinct_fields, distinct_params = self.get_distinct()
                # This must come after 'select', 'ordering', and 'distinct'
                # (see docstring of get_from_clause() for details).
                from_, f_params = self.get_from_clause()
                where, w_params = (
                    self.compile(self.where)
                    if self.where is not None
                    else ("", [])
                )
                having, h_params = (
                    self.compile(self.having)
                    if self.having is not None
                    else ("", [])
                )
                result = ['SELECT']
                params = []

                if self.query.distinct:
                    (
                        distinct_result,
                        distinct_params,
                    ) = self.connection.ops.distinct_sql(
                        distinct_fields,
                        distinct_params,
                        order_by,
                    )
                    result += distinct_result
                    params += distinct_params

                out_cols = []
                col_idx = 1
                for _, (s_sql, s_params), alias in self.select + extra_select:
                    if alias:
                        s_sql = '%s AS %s' % (
                            s_sql,
                            self.connection.ops.quote_name(alias),
                        )
                    elif with_col_aliases:
                        s_sql = '%s AS %s' % (s_sql, 'Col%d' % col_idx)
                        col_idx += 1
                    params.extend(s_params)
                    out_cols.append(s_sql)

                result += [', '.join(out_cols), 'FROM', *from_]
                params.extend(f_params)

                if (
                    self.query.select_for_update
                    and features.has_select_for_update
                ):
                    if self.connection.get_autocommit():
                        raise TransactionManagementError(
                            'select_for_update cannot be used outside of a transaction.'
                        )

                    if (
                        with_limit_offset
                        and not features.supports_select_for_update_with_limit
                    ):
                        raise NotSupportedError(
                            'LIMIT/OFFSET is not supported with '
                            'select_for_update on this database backend.'
                        )
                    nowait = self.query.select_for_update_nowait
                    skip_locked = self.query.select_for_update_skip_locked
                    of = self.query.select_for_update_of
                    # If it's a NOWAIT/SKIP LOCKED/OF query but the backend
                    # doesn't support it, raise NotSupportedError to prevent a
                    # possible deadlock.
                    if nowait and not features.has_select_for_update_nowait:
                        raise NotSupportedError(
                            'NOWAIT is not supported on this database backend.'
                        )
                    elif (
                        skip_locked
                        and not features.has_select_for_update_skip_locked
                    ):
                        raise NotSupportedError(
                            'SKIP LOCKED is not supported on this database backend.'
                        )
                    elif of and not features.has_select_for_update_of:
                        raise NotSupportedError(
                            'FOR UPDATE OF is not supported on this database backend.'
                        )
                    for_update_part = self.connection.ops.for_update_sql(
                        nowait=nowait,
                        skip_locked=skip_locked,
                        of=self.get_select_for_update_of_arguments(),
                    )

                if for_update_part and features.for_update_after_from:
                    result.append(for_update_part)

                if where:
                    result.append('WHERE %s' % where)
                    params.extend(w_params)

                grouping = []
                for g_sql, g_params in group_by:
                    grouping.append(g_sql)
                    params.extend(g_params)
                if grouping:
                    if distinct_fields:
                        raise NotImplementedError(
                            'annotate() + distinct(fields) is not implemented.'
                        )
                    order_by = (
                        order_by or self.connection.ops.force_no_ordering()
                    )
                    result.append('GROUP BY %s' % ', '.join(grouping))
                    if self._meta_ordering:
                        # When the deprecation ends, replace with:
                        # order_by = None
                        warnings.warn(
                            "%s QuerySet won't use Meta.ordering in Django 3.1. "
                            "Add .order_by(%s) to retain the current query."
                            % (
                                self.query.model.__name__,
                                ', '.join(
                                    repr(f) for f in self._meta_ordering
                                ),
                            ),
                            RemovedInDjango31Warning,
                            stacklevel=4,
                        )
                if having:
                    result.append('HAVING %s' % having)
                    params.extend(h_params)

            if self.query.explain_query:
                result.insert(
                    0,
                    self.connection.ops.explain_query_prefix(
                        self.query.explain_format, **self.query.explain_options
                    ),
                )

            if order_by:
                ordering = []
                for _, (o_sql, o_params, _) in order_by:
                    ordering.append(o_sql)
                    params.extend(o_params)
                result.append('ORDER BY %s' % ', '.join(ordering))

            if with_limit_offset:
                result.append(
                    self.connection.ops.limit_offset_sql(
                        self.query.low_mark, self.query.high_mark
                    )
                )

            if for_update_part and not features.for_update_after_from:
                result.append(for_update_part)

            if self.query.distinct_fields:
                pre_result = " ".join(result)
                sql = f"SELECT * FROM ({pre_result}) where row_number = 1"
                return sql, tuple(params)

            if self.query.subquery and extra_select:
                # If the query is used as a subquery, the extra selects would
                # result in more columns than the left-hand side expression is
                # expecting. This can happen when a subquery uses a combination
                # of order_by() and distinct(), forcing the ordering expressions
                # to be selected as well. Wrap the query in another subquery
                # to exclude extraneous selects.
                sub_selects = []
                sub_params = []
                for index, (select, _, alias) in enumerate(
                    self.select, start=1
                ):
                    if not alias and with_col_aliases:
                        alias = 'col%d' % index
                    if alias:
                        sub_selects.append(
                            "%s.%s"
                            % (
                                self.connection.ops.quote_name('subquery'),
                                self.connection.ops.quote_name(alias),
                            )
                        )
                    else:
                        select_clone = select.relabeled_clone(
                            {select.alias: 'subquery'}
                        )
                        subselect, subparams = select_clone.as_sql(
                            self, self.connection
                        )
                        sub_selects.append(subselect)
                        sub_params.extend(subparams)
                return 'SELECT %s FROM (%s) subquery' % (
                    ', '.join(sub_selects),
                    ' '.join(result),
                ), tuple(sub_params + params)

            return ' '.join(result), tuple(params)
        finally:
            # Finally do cleanup - get rid of the joins we created above.
            self.query.reset_refcounts(refcounts_before)
