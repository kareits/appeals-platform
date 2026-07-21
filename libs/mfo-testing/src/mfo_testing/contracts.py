"""Lightweight contract-test assertions.

Provides a minimal JSON-Schema-style structural check for use in contract tests before a full
schema-validation dependency is introduced (TASK_00C). It verifies required keys and basic value
types without pulling in an external validator.
"""

from __future__ import annotations

from typing import Any

# Mapping of JSON Schema primitive type names to the corresponding Python runtime types.
_JSON_TYPE_TO_PYTHON: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def assert_matches_schema(payload: Any, schema: dict[str, Any]) -> None:
    """Assert that a payload satisfies a minimal JSON-Schema-like description.

    Supports ``type`` (object/array/string/number/integer/boolean), ``required`` keys for objects,
    and nested ``properties``. This is a stopgap until a full JSON Schema validator is adopted in
    TASK_00C.

    Args:
        payload: The value to validate.
        schema: The schema description to validate against.

    Raises:
        AssertionError: If the payload violates the schema.
    """
    expected_type = schema.get("type")
    if expected_type is not None:
        python_type = _JSON_TYPE_TO_PYTHON[expected_type]
        # ``bool`` is a subclass of ``int``; guard so booleans are not accepted as integers.
        if expected_type in {"number", "integer"} and isinstance(payload, bool):
            raise AssertionError(f"Expected {expected_type}, got bool: {payload!r}")
        if not isinstance(payload, python_type):
            raise AssertionError(f"Expected type {expected_type}, got {type(payload).__name__}")

    if expected_type == "object":
        for key in schema.get("required", []):
            if key not in payload:
                raise AssertionError(f"Missing required key: {key!r}")
        for key, subschema in schema.get("properties", {}).items():
            if key in payload:
                assert_matches_schema(payload[key], subschema)
