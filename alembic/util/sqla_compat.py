import re
from sqlalchemy import __version__
from sqlalchemy.schema import ForeignKeyConstraint, CheckConstraint, Column
from sqlalchemy import types as sqltypes
from sqlalchemy import schema, sql
from sqlalchemy.sql.visitors import traverse
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import _BindParamClause
from . import compat


def _safe_int(value):
    try:
        return int(value)
    except:
        return value
_vers = tuple(
    [_safe_int(x) for x in re.findall(r'(\d+|[abc]\d)', __version__)])
sqla_07 = _vers > (0, 7, 2)
sqla_079 = _vers >= (0, 7, 9)
sqla_08 = _vers >= (0, 8, 0)
sqla_083 = _vers >= (0, 8, 3)
sqla_084 = _vers >= (0, 8, 4)
sqla_09 = _vers >= (0, 9, 0)
sqla_092 = _vers >= (0, 9, 2)
sqla_094 = _vers >= (0, 9, 4)
sqla_094 = _vers >= (0, 9, 4)
sqla_099 = _vers >= (0, 9, 9)
sqla_100 = _vers >= (1, 0, 0)
sqla_105 = _vers >= (1, 0, 5)

if sqla_08:
    from sqlalchemy.sql.expression import TextClause
else:
    from sqlalchemy.sql.expression import _TextClause as TextClause


def _table_for_constraint(constraint):
    if isinstance(constraint, ForeignKeyConstraint):
        return constraint.parent
    else:
        return constraint.table


def _columns_for_constraint(constraint):
    if isinstance(constraint, ForeignKeyConstraint):
        return [fk.parent for fk in constraint.elements]
    elif isinstance(constraint, CheckConstraint):
        return _find_columns(constraint.sqltext)
    else:
        return list(constraint.columns)


def _fk_spec(constraint):
    if sqla_100:
        source_columns = [
            constraint.columns[key].name for key in constraint.column_keys]
    else:
        source_columns = [
            element.parent.name for element in constraint.elements]

    source_table = constraint.parent.name
    source_schema = constraint.parent.schema
    target_schema = constraint.elements[0].column.table.schema
    target_table = constraint.elements[0].column.table.name
    target_columns = [element.column.name for element in constraint.elements]

    return (
        source_schema, source_table,
        source_columns, target_schema, target_table, target_columns)


def _is_type_bound(constraint):
    # this deals with SQLAlchemy #3260, don't copy CHECK constraints
    # that will be generated by the type.
    if sqla_100:
        # new feature added for #3260
        return constraint._type_bound
    else:
        # old way, look at what we know Boolean/Enum to use
        return (
            constraint._create_rule is not None and
            isinstance(
                getattr(constraint._create_rule, "target", None),
                sqltypes.SchemaType)
        )


def _find_columns(clause):
    """locate Column objects within the given expression."""

    cols = set()
    traverse(clause, {}, {'column': cols.add})
    return cols


def _textual_index_column(table, text_):
    """a workaround for the Index construct's severe lack of flexibility"""
    if isinstance(text_, compat.string_types):
        c = Column(text_, sqltypes.NULLTYPE)
        table.append_column(c)
        return c
    elif isinstance(text_, TextClause):
        return _textual_index_element(table, text_)
    elif isinstance(text_, sql.ColumnElement):
        return text_
    else:
        raise ValueError("String or text() construct expected")


class _textual_index_element(sql.ColumnElement):
    """Wrap around a sqlalchemy text() construct in such a way that
    we appear like a column-oriented SQL expression to an Index
    construct.

    The issue here is that currently the Postgresql dialect, the biggest
    recipient of functional indexes, keys all the index expressions to
    the corresponding column expressions when rendering CREATE INDEX,
    so the Index we create here needs to have a .columns collection that
    is the same length as the .expressions collection.  Ultimately
    SQLAlchemy should support text() expressions in indexes.

    See https://bitbucket.org/zzzeek/sqlalchemy/issue/3174/\
    support-text-sent-to-indexes

    """
    __visit_name__ = '_textual_idx_element'

    def __init__(self, table, text):
        self.table = table
        self.text = text
        self.key = text.text
        self.fake_column = schema.Column(self.text.text, sqltypes.NULLTYPE)
        table.append_column(self.fake_column)

    def get_children(self):
        return [self.fake_column]


@compiles(_textual_index_element)
def _render_textual_index_column(element, compiler, **kw):
    return compiler.process(element.text, **kw)


class _literal_bindparam(_BindParamClause):
    pass


@compiles(_literal_bindparam)
def _render_literal_bindparam(element, compiler, **kw):
    return compiler.render_literal_bindparam(element, **kw)


def _get_index_expressions(idx):
    if sqla_08:
        return list(idx.expressions)
    else:
        return list(idx.columns)


def _get_index_column_names(idx):
    return [getattr(exp, "name", None) for exp in _get_index_expressions(idx)]
