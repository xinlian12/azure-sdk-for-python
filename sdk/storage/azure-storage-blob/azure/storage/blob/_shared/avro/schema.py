# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
# pylint: disable=docstring-missing-return, docstring-missing-rtype, too-many-lines

"""Representation of Avro schemas.

A schema may be one of:
 - A record, mapping field names to field value data;
 - An error, equivalent to a record;
 - An enum, containing one of a small set of symbols;
 - An array of values, all of the same schema;
 - A map containing string/value pairs, each of a declared schema;
 - A union of other schemas;
 - A fixed sized binary object;
 - A unicode string;
 - A sequence of bytes;
 - A 32-bit signed int;
 - A 64-bit signed long;
 - A 32-bit floating-point float;
 - A 64-bit floating-point double;
 - A boolean;
 - Null.
"""

import abc
import json
import logging
import re

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Constants

# Log level more verbose than DEBUG=10, INFO=20, etc.
DEBUG_VERBOSE = 5

NULL = "null"
BOOLEAN = "boolean"
STRING = "string"
BYTES = "bytes"
INT = "int"
LONG = "long"
FLOAT = "float"
DOUBLE = "double"
FIXED = "fixed"
ENUM = "enum"
RECORD = "record"
ERROR = "error"
ARRAY = "array"
MAP = "map"
UNION = "union"

# Request and error unions are part of Avro protocols:
REQUEST = "request"
ERROR_UNION = "error_union"

PRIMITIVE_TYPES = frozenset(
    [
        NULL,
        BOOLEAN,
        STRING,
        BYTES,
        INT,
        LONG,
        FLOAT,
        DOUBLE,
    ]
)

NAMED_TYPES = frozenset(
    [
        FIXED,
        ENUM,
        RECORD,
        ERROR,
    ]
)

VALID_TYPES = frozenset.union(
    PRIMITIVE_TYPES,
    NAMED_TYPES,
    [
        ARRAY,
        MAP,
        UNION,
        REQUEST,
        ERROR_UNION,
    ],
)

SCHEMA_RESERVED_PROPS = frozenset(
    [
        "type",
        "name",
        "namespace",
        "fields",  # Record
        "items",  # Array
        "size",  # Fixed
        "symbols",  # Enum
        "values",  # Map
        "doc",
    ]
)

FIELD_RESERVED_PROPS = frozenset(
    [
        "default",
        "name",
        "doc",
        "order",
        "type",
    ]
)

VALID_FIELD_SORT_ORDERS = frozenset(
    [
        "ascending",
        "descending",
        "ignore",
    ]
)


# ------------------------------------------------------------------------------
# Exceptions


class Error(Exception):
    """Base class for errors in this module."""


class AvroException(Error):
    """Generic Avro schema error."""


class SchemaParseException(AvroException):
    """Error while parsing a JSON schema descriptor."""


class Schema(metaclass=abc.ABCMeta):
    """Abstract base class for all Schema classes."""

    def __init__(self, data_type, other_props=None):
        """Initializes a new schema object.

        Args:
          data_type: Type of the schema to initialize.
          other_props: Optional dictionary of additional properties.
        """
        if data_type not in VALID_TYPES:
            raise SchemaParseException(f"{data_type!r} is not a valid Avro type.")

        # All properties of this schema, as a map: property name -> property value
        self._props = {}

        self._props["type"] = data_type
        self._type = data_type

        if other_props:
            self._props.update(other_props)

    @property
    def namespace(self):
        """Returns: the namespace this schema belongs to, if any, or None."""
        return self._props.get("namespace", None)

    @property
    def type(self):
        """Returns: the type of this schema."""
        return self._type

    @property
    def doc(self):
        """Returns: the documentation associated to this schema, if any, or None."""
        return self._props.get("doc", None)

    @property
    def props(self):
        """Reports all the properties of this schema.

        Includes all properties, reserved and non reserved.
        JSON properties of this schema are directly generated from this dict.

        Returns:
          A dictionary of properties associated to this schema.
        """
        return self._props

    @property
    def other_props(self):
        """Returns: the dictionary of non-reserved properties."""
        return dict(filter_keys_out(items=self._props, keys=SCHEMA_RESERVED_PROPS))

    def __str__(self):
        """Returns: the JSON representation of this schema."""
        return json.dumps(self.to_json(names=None))

    # Converts the schema object into its AVRO specification representation.

    # Schema types that have names (records, enums, and fixed) must be aware of not
    # re-defining schemas that are already listed in the parameter names.
    @abc.abstractmethod
    def to_json(self, names): ...


# ------------------------------------------------------------------------------


_RE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_RE_FULL_NAME = re.compile(
    r"^"
    r"[.]?(?:[A-Za-z_][A-Za-z0-9_]*[.])*"  # optional namespace
    r"([A-Za-z_][A-Za-z0-9_]*)"  # name
    r"$"
)


class Name(object):
    """Representation of an Avro name."""

    def __init__(self, name, namespace=None):
        """Parses an Avro name.

        Args:
          name: Avro name to parse (relative or absolute).
          namespace: Optional explicit namespace if the name is relative.
        """
        # Normalize: namespace is always defined as a string, possibly empty.
        if namespace is None:
            namespace = ""

        if "." in name:
            # name is absolute, namespace is ignored:
            self._fullname = name

            match = _RE_FULL_NAME.match(self._fullname)
            if match is None:
                raise SchemaParseException(f"Invalid absolute schema name: {self._fullname!r}.")

            self._name = match.group(1)
            self._namespace = self._fullname[: -(len(self._name) + 1)]

        else:
            # name is relative, combine with explicit namespace:
            self._name = name
            self._namespace = namespace
            self._fullname = self._name if (not self._namespace) else f"{self._namespace}.{self._name}"

            # Validate the fullname:
            if _RE_FULL_NAME.match(self._fullname) is None:
                raise SchemaParseException(
                    f"Invalid schema name {self._fullname!r} inferred from "
                    f"name {self._name!r} and namespace {self._namespace!r}."
                )

    def __eq__(self, other):
        if not isinstance(other, Name):
            return NotImplemented
        return self.fullname == other.fullname

    @property
    def simple_name(self):
        """Returns: the simple name part of this name."""
        return self._name

    @property
    def namespace(self):
        """Returns: this name's namespace, possible the empty string."""
        return self._namespace

    @property
    def fullname(self):
        """Returns: the full name."""
        return self._fullname


# ------------------------------------------------------------------------------


class Names(object):
    """Tracks Avro named schemas and default namespace during parsing."""

    def __init__(self, default_namespace=None, names=None):
        """Initializes a new name tracker.

        Args:
          default_namespace: Optional default namespace.
          names: Optional initial mapping of known named schemas.
        """
        if names is None:
            names = {}
        self._names = names
        self._default_namespace = default_namespace

    @property
    def names(self):
        """Returns: the mapping of known named schemas."""
        return self._names

    @property
    def default_namespace(self):
        """Returns: the default namespace, if any, or None."""
        return self._default_namespace

    def new_with_default_namespace(self, namespace):
        """Creates a new name tracker from this tracker, but with a new default ns.

        :param Any namespace: New default namespace to use.
        :return: New name tracker with the specified default namespace.
        :rtype: Names
        """
        return Names(names=self._names, default_namespace=namespace)

    def get_name(self, name, namespace=None):
        """Resolves the Avro name according to this name tracker's state.

        :param Any name: Name to resolve (absolute or relative).
        :param Optional[Any] namespace: Optional explicit namespace.
        :return: The specified name, resolved according to this tracker.
        :rtype: Name
        """
        if namespace is None:
            namespace = self._default_namespace
        return Name(name=name, namespace=namespace)

    def get_schema(self, name, namespace=None):
        """Resolves an Avro schema by name.

        :param Any name: Name (absolute or relative) of the Avro schema to look up.
        :param Optional[Any] namespace: Optional explicit namespace.
        :return: The schema with the specified name, if any, or None
        :rtype: Union[Any, None]
        """
        avro_name = self.get_name(name=name, namespace=namespace)
        return self._names.get(avro_name.fullname, None)

    # Given a properties, return properties with namespace removed if it matches the own default namespace
    def prune_namespace(self, properties):
        if self.default_namespace is None:
            # I have no default -- no change
            return properties
        if "namespace" not in properties:
            # he has no namespace - no change
            return properties
        if properties["namespace"] != self.default_namespace:
            # we're different - leave his stuff alone
            return properties
        # we each have a namespace and it's redundant. delete his.
        prunable = properties.copy()
        del prunable["namespace"]
        return prunable

    def register(self, schema):
        """Registers a new named schema in this tracker.

        :param Any schema: Named Avro schema to register in this tracker.
        """
        if schema.fullname in VALID_TYPES:
            raise SchemaParseException(f"{schema.fullname} is a reserved type name.")
        if schema.fullname in self.names:
            raise SchemaParseException(f"Avro name {schema.fullname!r} already exists.")

        logger.log(DEBUG_VERBOSE, "Register new name for %r", schema.fullname)
        self._names[schema.fullname] = schema


# ------------------------------------------------------------------------------


class NamedSchema(Schema):
    """Abstract base class for named schemas.

    Named schemas are enumerated in NAMED_TYPES.
    """

    def __init__(
        self,
        data_type,
        name=None,
        namespace=None,
        names=None,
        other_props=None,
    ):
        """Initializes a new named schema object.

        Args:
          data_type: Type of the named schema.
          name: Name (absolute or relative) of the schema.
          namespace: Optional explicit namespace if name is relative.
          names: Tracker to resolve and register Avro names.
          other_props: Optional map of additional properties of the schema.
        """
        assert data_type in NAMED_TYPES, f"Invalid named type: {data_type!r}"
        self._avro_name = names.get_name(name=name, namespace=namespace)

        super(NamedSchema, self).__init__(data_type, other_props)

        names.register(self)

        self._props["name"] = self.name
        if self.namespace:
            self._props["namespace"] = self.namespace

    @property
    def avro_name(self):
        """Returns: the Name object describing this schema's name."""
        return self._avro_name

    @property
    def name(self):
        return self._avro_name.simple_name

    @property
    def namespace(self):
        return self._avro_name.namespace

    @property
    def fullname(self):
        return self._avro_name.fullname

    def name_ref(self, names):
        """Reports this schema name relative to the specified name tracker.

        :param Any names: Avro name tracker to relativize this schema name against.
        :return: This schema name, relativized against the specified name tracker.
        :rtype: Any
        """
        if self.namespace == names.default_namespace:
            return self.name
        return self.fullname

    # Converts the schema object into its AVRO specification representation.

    # Schema types that have names (records, enums, and fixed) must be aware
    # of not re-defining schemas that are already listed in the parameter names.
    @abc.abstractmethod
    def to_json(self, names): ...


# ------------------------------------------------------------------------------


_NO_DEFAULT = object()


class Field(object):
    """Representation of the schema of a field in a record."""

    def __init__(
        self, data_type, name, index, has_default, default=_NO_DEFAULT, order=None, doc=None, other_props=None
    ):
        """Initializes a new Field object.

        Args:
          data_type: Avro schema of the field.
          name: Name of the field.
          index: 0-based position of the field.
          has_default:
          default:
          order:
          doc:
          other_props:
        """
        if (not isinstance(name, str)) or (not name):
            raise SchemaParseException(f"Invalid record field name: {name!r}.")
        if (order is not None) and (order not in VALID_FIELD_SORT_ORDERS):
            raise SchemaParseException(f"Invalid record field order: {order!r}.")

        # All properties of this record field:
        self._props = {}

        self._has_default = has_default
        if other_props:
            self._props.update(other_props)

        self._index = index
        self._type = self._props["type"] = data_type
        self._name = self._props["name"] = name

        if has_default:
            self._props["default"] = default

        if order is not None:
            self._props["order"] = order

        if doc is not None:
            self._props["doc"] = doc

    @property
    def type(self):
        """Returns: the schema of this field."""
        return self._type

    @property
    def name(self):
        """Returns: this field name."""
        return self._name

    @property
    def index(self):
        """Returns: the 0-based index of this field in the record."""
        return self._index

    @property
    def default(self):
        return self._props["default"]

    @property
    def has_default(self):
        return self._has_default

    @property
    def order(self):
        return self._props.get("order", None)

    @property
    def doc(self):
        return self._props.get("doc", None)

    @property
    def props(self):
        return self._props

    @property
    def other_props(self):
        return filter_keys_out(items=self._props, keys=FIELD_RESERVED_PROPS)

    def __str__(self):
        return json.dumps(self.to_json())

    def to_json(self, names=None):
        if names is None:
            names = Names()
        to_dump = self.props.copy()
        to_dump["type"] = self.type.to_json(names)
        return to_dump

    def __eq__(self, that):
        to_cmp = json.loads(str(self))
        return to_cmp == json.loads(str(that))


# ------------------------------------------------------------------------------
# Primitive Types


class PrimitiveSchema(Schema):
    """Schema of a primitive Avro type.

    Valid primitive types are defined in PRIMITIVE_TYPES.
    """

    def __init__(self, data_type, other_props=None):
        """Initializes a new schema object for the specified primitive type.

        Args:
          data_type: Type of the schema to construct. Must be primitive.
        """
        if data_type not in PRIMITIVE_TYPES:
            raise AvroException(f"{data_type!r} is not a valid primitive type.")
        super(PrimitiveSchema, self).__init__(data_type, other_props=other_props)

    @property
    def name(self):
        """Returns: the simple name of this schema."""
        # The name of a primitive type is the type itself.
        return self.type

    @property
    def fullname(self):
        """Returns: the fully qualified name of this schema."""
        # The full name is the simple name for primitive schema.
        return self.name

    def to_json(self, names=None):
        if len(self.props) == 1:
            return self.fullname
        return self.props

    def __eq__(self, that):
        return self.props == that.props


# ------------------------------------------------------------------------------
# Complex Types (non-recursive)


class FixedSchema(NamedSchema):
    def __init__(
        self,
        name,
        namespace,
        size,
        names=None,
        other_props=None,
    ):
        # Ensure valid ctor args
        if not isinstance(size, int):
            fail_msg = "Fixed Schema requires a valid integer for size property."
            raise AvroException(fail_msg)

        super(FixedSchema, self).__init__(
            data_type=FIXED,
            name=name,
            namespace=namespace,
            names=names,
            other_props=other_props,
        )
        self._props["size"] = size

    @property
    def size(self):
        """Returns: the size of this fixed schema, in bytes."""
        return self._props["size"]

    def to_json(self, names=None):
        if names is None:
            names = Names()
        if self.fullname in names.names:
            return self.name_ref(names)
        names.names[self.fullname] = self
        return names.prune_namespace(self.props)

    def __eq__(self, that):
        return self.props == that.props


# ------------------------------------------------------------------------------


class EnumSchema(NamedSchema):
    def __init__(
        self,
        name,
        namespace,
        symbols,
        names=None,
        doc=None,
        other_props=None,
    ):
        """Initializes a new enumeration schema object.

        Args:
          name: Simple name of this enumeration.
          namespace: Optional namespace.
          symbols: Ordered list of symbols defined in this enumeration.
          names:
          doc:
          other_props:
        """
        symbols = tuple(symbols)
        symbol_set = frozenset(symbols)
        if len(symbol_set) != len(symbols) or not all(map(lambda symbol: isinstance(symbol, str), symbols)):
            raise AvroException(f"Invalid symbols for enum schema: {symbols!r}.")

        super(EnumSchema, self).__init__(
            data_type=ENUM,
            name=name,
            namespace=namespace,
            names=names,
            other_props=other_props,
        )

        self._props["symbols"] = symbols
        if doc is not None:
            self._props["doc"] = doc

    @property
    def symbols(self):
        """Returns: the symbols defined in this enum."""
        return self._props["symbols"]

    def to_json(self, names=None):
        if names is None:
            names = Names()
        if self.fullname in names.names:
            return self.name_ref(names)
        names.names[self.fullname] = self
        return names.prune_namespace(self.props)

    def __eq__(self, that):
        return self.props == that.props


# ------------------------------------------------------------------------------
# Complex Types (recursive)


class ArraySchema(Schema):
    """Schema of an array."""

    def __init__(self, items, other_props=None):
        """Initializes a new array schema object.

        Args:
          items: Avro schema of the array items.
          other_props:
        """
        super(ArraySchema, self).__init__(
            data_type=ARRAY,
            other_props=other_props,
        )
        self._items_schema = items
        self._props["items"] = items

    @property
    def items(self):
        """Returns: the schema of the items in this array."""
        return self._items_schema

    def to_json(self, names=None):
        if names is None:
            names = Names()
        to_dump = self.props.copy()
        item_schema = self.items
        to_dump["items"] = item_schema.to_json(names)
        return to_dump

    def __eq__(self, that):
        to_cmp = json.loads(str(self))
        return to_cmp == json.loads(str(that))


# ------------------------------------------------------------------------------


class MapSchema(Schema):
    """Schema of a map."""

    def __init__(self, values, other_props=None):
        """Initializes a new map schema object.

        Args:
          values: Avro schema of the map values.
          other_props:
        """
        super(MapSchema, self).__init__(
            data_type=MAP,
            other_props=other_props,
        )
        self._values_schema = values
        self._props["values"] = values

    @property
    def values(self):
        """Returns: the schema of the values in this map."""
        return self._values_schema

    def to_json(self, names=None):
        if names is None:
            names = Names()
        to_dump = self.props.copy()
        to_dump["values"] = self.values.to_json(names)
        return to_dump

    def __eq__(self, that):
        to_cmp = json.loads(str(self))
        return to_cmp == json.loads(str(that))


# ------------------------------------------------------------------------------


class UnionSchema(Schema):
    """Schema of a union."""

    def __init__(self, schemas):
        """Initializes a new union schema object.

        Args:
          schemas: Ordered collection of schema branches in the union.
        """
        super(UnionSchema, self).__init__(data_type=UNION)
        self._schemas = tuple(schemas)

        # Validate the schema branches:

        # All named schema names are unique:
        named_branches = tuple(filter(lambda schema: schema.type in NAMED_TYPES, self._schemas))
        unique_names = frozenset(map(lambda schema: schema.fullname, named_branches))
        if len(unique_names) != len(named_branches):
            schemas = "".join(map(lambda schema: (f"\n\t - {schema}"), self._schemas))
            raise AvroException(f"Invalid union branches with duplicate schema name:{schemas}")

        # Types are unique within unnamed schemas, and union is not allowed:
        unnamed_branches = tuple(filter(lambda schema: schema.type not in NAMED_TYPES, self._schemas))
        unique_types = frozenset(map(lambda schema: schema.type, unnamed_branches))
        if UNION in unique_types:
            schemas = "".join(map(lambda schema: (f"\n\t - {schema}"), self._schemas))
            raise AvroException(f"Invalid union branches contain other unions:{schemas}")
        if len(unique_types) != len(unnamed_branches):
            schemas = "".join(map(lambda schema: (f"\n\t - {schema}"), self._schemas))
            raise AvroException(f"Invalid union branches with duplicate type:{schemas}")

    @property
    def schemas(self):
        """Returns: the ordered list of schema branches in the union."""
        return self._schemas

    def to_json(self, names=None):
        if names is None:
            names = Names()
        to_dump = []
        for schema in self.schemas:
            to_dump.append(schema.to_json(names))
        return to_dump

    def __eq__(self, that):
        to_cmp = json.loads(str(self))
        return to_cmp == json.loads(str(that))


# ------------------------------------------------------------------------------


class ErrorUnionSchema(UnionSchema):
    """Schema representing the declared errors of a protocol message."""

    def __init__(self, schemas):
        """Initializes an error-union schema.

        Args:
          schema: collection of error schema.
        """
        # Prepend "string" to handle system errors
        schemas = [PrimitiveSchema(data_type=STRING)] + list(schemas)
        super(ErrorUnionSchema, self).__init__(schemas=schemas)

    def to_json(self, names=None):
        if names is None:
            names = Names()
        to_dump = []
        for schema in self.schemas:
            # Don't print the system error schema
            if schema.type == STRING:
                continue
            to_dump.append(schema.to_json(names))
        return to_dump


# ------------------------------------------------------------------------------


class RecordSchema(NamedSchema):
    """Schema of a record."""

    @staticmethod
    def _make_field(index, field_desc, names):
        """Builds field schemas from a list of field JSON descriptors.

        :param int index: 0-based index of the field in the record.
        :param Any field_desc: JSON descriptors of a record field.
        :param Any names: The names for this schema.
        :return: The field schema.
        :rtype: Field
        """
        field_schema = schema_from_json_data(
            json_data=field_desc["type"],
            names=names,
        )
        other_props = dict(filter_keys_out(items=field_desc, keys=FIELD_RESERVED_PROPS))
        return Field(
            data_type=field_schema,
            name=field_desc["name"],
            index=index,
            has_default=("default" in field_desc),
            default=field_desc.get("default", _NO_DEFAULT),
            order=field_desc.get("order", None),
            doc=field_desc.get("doc", None),
            other_props=other_props,
        )

    @staticmethod
    def make_field_list(field_desc_list, names):
        """Builds field schemas from a list of field JSON descriptors.
        Guarantees field name unicity.

        :param Any field_desc_list: Collection of field JSON descriptors.
        :param Any names: The names for this schema.
        :return: Field schemas.
        :rtype: Field
        """
        for index, field_desc in enumerate(field_desc_list):
            yield RecordSchema._make_field(index, field_desc, names)

    @staticmethod
    def _make_field_map(fields):
        """Builds the field map.
        Guarantees field name unicity.

        :param Any fields: Iterable of field schema.
        :return: A map of field schemas, indexed by name.
        :rtype: Dict[Any, Any]
        """
        field_map = {}
        for field in fields:
            if field.name in field_map:
                raise SchemaParseException(f"Duplicate record field name {field.name!r}.")
            field_map[field.name] = field
        return field_map

    def __init__(
        self, name, namespace, fields=None, make_fields=None, names=None, record_type=RECORD, doc=None, other_props=None
    ):
        """Initializes a new record schema object.

        Args:
          name: Name of the record (absolute or relative).
          namespace: Optional namespace the record belongs to, if name is relative.
          fields: collection of fields to add to this record.
              Exactly one of fields or make_fields must be specified.
          make_fields: function creating the fields that belong to the record.
              The function signature is: make_fields(names) -> ordered field list.
              Exactly one of fields or make_fields must be specified.
          names:
          record_type: Type of the record: one of RECORD, ERROR or REQUEST.
              Protocol requests are not named.
          doc:
          other_props:
        """
        if record_type == REQUEST:
            # Protocol requests are not named:
            super(RecordSchema, self).__init__(
                data_type=REQUEST,
                other_props=other_props,
            )
        elif record_type in [RECORD, ERROR]:
            # Register this record name in the tracker:
            super(RecordSchema, self).__init__(
                data_type=record_type,
                name=name,
                namespace=namespace,
                names=names,
                other_props=other_props,
            )
        else:
            raise SchemaParseException(f"Invalid record type: {record_type!r}.")

        nested_names = []
        if record_type in [RECORD, ERROR]:
            avro_name = names.get_name(name=name, namespace=namespace)
            nested_names = names.new_with_default_namespace(namespace=avro_name.namespace)
        elif record_type == REQUEST:
            # Protocol request has no name: no need to change default namespace:
            nested_names = names

        if fields is None:
            fields = make_fields(names=nested_names)
        else:
            assert make_fields is None
        self._fields = tuple(fields)

        self._field_map = RecordSchema._make_field_map(self._fields)

        self._props["fields"] = fields
        if doc is not None:
            self._props["doc"] = doc

    @property
    def fields(self):
        """Returns: the field schemas, as an ordered tuple."""
        return self._fields

    @property
    def field_map(self):
        """Returns: a read-only map of the field schemas index by field names."""
        return self._field_map

    def to_json(self, names=None):
        if names is None:
            names = Names()
        # Request records don't have names
        if self.type == REQUEST:
            return [f.to_json(names) for f in self.fields]

        if self.fullname in names.names:
            return self.name_ref(names)
        names.names[self.fullname] = self

        to_dump = names.prune_namespace(self.props.copy())
        to_dump["fields"] = [f.to_json(names) for f in self.fields]
        return to_dump

    def __eq__(self, that):
        to_cmp = json.loads(str(self))
        return to_cmp == json.loads(str(that))


# ------------------------------------------------------------------------------
# Module functions


def filter_keys_out(items, keys):
    """Filters a collection of (key, value) items.
    Exclude any item whose key belongs to keys.

    :param Dict[Any, Any] items: Dictionary of items to filter the keys out of.
    :param Dict[Any, Any] keys: Dictionary of keys to filter the extracted keys against.
    :return: Filtered items.
    :rtype: Tuple(Any, Any)
    """
    for key, value in items.items():
        if key in keys:
            continue
        yield key, value


# ------------------------------------------------------------------------------


def _schema_from_json_string(json_string, names):
    if json_string in PRIMITIVE_TYPES:
        return PrimitiveSchema(data_type=json_string)

    # Look for a known named schema:
    schema = names.get_schema(name=json_string)
    if schema is None:
        raise SchemaParseException(f"Unknown named schema {json_string!r}, known names: {sorted(names.names)!r}.")
    return schema


def _schema_from_json_array(json_array, names):
    def MakeSchema(desc):
        return schema_from_json_data(json_data=desc, names=names)

    return UnionSchema(map(MakeSchema, json_array))


def _schema_from_json_object(json_object, names):
    data_type = json_object.get("type")
    if data_type is None:
        raise SchemaParseException(f'Avro schema JSON descriptor has no "type" property: {json_object!r}')

    other_props = dict(filter_keys_out(items=json_object, keys=SCHEMA_RESERVED_PROPS))

    if data_type in PRIMITIVE_TYPES:
        # FIXME should not ignore other properties
        result = PrimitiveSchema(data_type, other_props=other_props)

    elif data_type in NAMED_TYPES:
        name = json_object.get("name")
        namespace = json_object.get("namespace", names.default_namespace)
        if data_type == FIXED:
            size = json_object.get("size")
            result = FixedSchema(name, namespace, size, names, other_props)
        elif data_type == ENUM:
            symbols = json_object.get("symbols")
            doc = json_object.get("doc")
            result = EnumSchema(name, namespace, symbols, names, doc, other_props)

        elif data_type in [RECORD, ERROR]:
            field_desc_list = json_object.get("fields", ())

            def MakeFields(names):
                return tuple(RecordSchema.make_field_list(field_desc_list, names))

            result = RecordSchema(
                name=name,
                namespace=namespace,
                make_fields=MakeFields,
                names=names,
                record_type=data_type,
                doc=json_object.get("doc"),
                other_props=other_props,
            )
        else:
            raise ValueError(f"Internal error: unknown type {data_type!r}.")

    elif data_type in VALID_TYPES:
        # Unnamed, non-primitive Avro type:

        if data_type == ARRAY:
            items_desc = json_object.get("items")
            if items_desc is None:
                raise SchemaParseException(f'Invalid array schema descriptor with no "items" : {json_object!r}.')
            result = ArraySchema(
                items=schema_from_json_data(items_desc, names),
                other_props=other_props,
            )

        elif data_type == MAP:
            values_desc = json_object.get("values")
            if values_desc is None:
                raise SchemaParseException(f'Invalid map schema descriptor with no "values" : {json_object!r}.')
            result = MapSchema(
                values=schema_from_json_data(values_desc, names=names),
                other_props=other_props,
            )

        elif data_type == ERROR_UNION:
            error_desc_list = json_object.get("declared_errors")
            assert error_desc_list is not None
            error_schemas = map(lambda desc: schema_from_json_data(desc, names=names), error_desc_list)
            result = ErrorUnionSchema(schemas=error_schemas)

        else:
            raise ValueError(f"Internal error: unknown type {data_type!r}.")
    else:
        raise SchemaParseException(f"Invalid JSON descriptor for an Avro schema: {json_object!r}")
    return result


# Parsers for the JSON data types:
_JSONDataParserTypeMap = {
    str: _schema_from_json_string,
    list: _schema_from_json_array,
    dict: _schema_from_json_object,
}


def schema_from_json_data(json_data, names=None):
    """Builds an Avro Schema from its JSON descriptor.
    Raises SchemaParseException if the descriptor is invalid.

    :param Any json_data: JSON data representing the descriptor of the Avro schema.
    :param Any names: Optional tracker for Avro named schemas.
    :return: The Avro schema parsed from the JSON descriptor.
    :rtype: Any
    """
    if names is None:
        names = Names()

    # Select the appropriate parser based on the JSON data type:
    parser = _JSONDataParserTypeMap.get(type(json_data))
    if parser is None:
        raise SchemaParseException(f"Invalid JSON descriptor for an Avro schema: {json_data!r}.")
    return parser(json_data, names=names)


# ------------------------------------------------------------------------------


def parse(json_string):
    """Constructs a Schema from its JSON descriptor in text form.
    Raises SchemaParseException if a JSON parsing error is met, or if the JSON descriptor is invalid.

    :param str json_string: String representation of the JSON descriptor of the schema.
    :return: The parsed schema.
    :rtype: Any
    """
    try:
        json_data = json.loads(json_string)
    except Exception as exn:
        raise SchemaParseException(
            f"Error parsing schema from JSON: {json_string!r}. " f"Error message: {exn!r}."
        ) from exn

    # Initialize the names object
    names = Names()

    # construct the Avro Schema object
    return schema_from_json_data(json_data, names)
