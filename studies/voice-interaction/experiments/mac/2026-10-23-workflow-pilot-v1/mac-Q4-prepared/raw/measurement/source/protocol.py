"""Native Qwen tool syntax and observable Agent intake checks."""

import json
import math
import re
import subprocess


class ProtocolError(ValueError):
    """A complete response does not conform to its native transport."""


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ProtocolError("duplicate JSON field: " + key)
        value[key] = item
    return value


def strict_json(text):
    def invalid_constant(value):
        raise ProtocolError("non-finite JSON constant: " + value)

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ProtocolError("non-finite JSON number: " + value)
        return number

    return json.loads(
        text,
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
        parse_float=finite_float,
    )


def json_status(raw, wire_calls=None):
    """Check native JSON independently of envelope and completion.

    None means no identifiable payload. An incomplete JSON fragment is
    false; complete JSON with a missing marker or length finish is true.
    Ordinary content JSON never becomes a native tool call.
    """
    try:
        if wire_calls is not None:
            if isinstance(wire_calls, list) and not wire_calls:
                return None
            # The outer wire value was already decoded by the transport.
            strict_json(json.dumps(wire_calls, allow_nan=False))
            if isinstance(wire_calls, list):
                for item in wire_calls:
                    function = (
                        item.get("function")
                        if isinstance(item, dict)
                        else None
                    )
                    if isinstance(function, dict) and isinstance(
                        function.get("arguments"), str
                    ):
                        strict_json(function["arguments"])
            return True
        text = raw
        if text.lstrip().startswith("<think>"):
            end = text.find("</think>")
            if end == -1:
                return None
            text = text[end + len("</think>") :]
        payloads, _ = _raw_payloads(text, require_envelopes=False)
        return True if payloads else None
    except (ValueError, TypeError, OverflowError):
        return False


def _raw_payloads(text, require_envelopes):
    """Decode JSON boundaries before inspecting envelope markers."""
    decoder = json.JSONDecoder(
        object_pairs_hook=unique_object,
        parse_constant=lambda value: strict_json(value),
        parse_float=lambda value: strict_json(value),
    )
    payloads, content, cursor = [], [], 0
    while True:
        marker = re.search(r"</?tool_call\b", text[cursor:])
        if marker is None:
            content.append(text[cursor:])
            return payloads, "".join(content)
        start = cursor + marker.start()
        content.append(text[cursor:start])
        if not text.startswith("<tool_call>", start):
            if require_envelopes:
                raise ProtocolError("unfinished or unmatched tool marker")
            # Malformed envelopes do not create a JSON payload.
            cursor = start + len(marker.group())
            continue
        body_start = start + len("<tool_call>")
        while body_start < len(text) and text[body_start].isspace():
            body_start += 1
        value, end = decoder.raw_decode(text, body_start)
        payloads.append(value)
        cursor = end
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if text.startswith("</tool_call>", cursor):
            cursor += len("</tool_call>")
        elif require_envelopes:
            raise ProtocolError("unfinished or unmatched tool marker")
        elif cursor < len(text) and not re.match(
            r"</?tool_call\b", text[cursor:]
        ):
            raise ProtocolError("trailing native JSON garbage")


def native_reply(raw, finish_reason="stop", wire_calls=None):
    """Return a complete Agent reply; plain JSON cannot call tools."""
    if json_status(raw, wire_calls) is False:
        raise ProtocolError("invalid native JSON payload")
    if finish_reason not in ("stop", "tool_calls"):
        raise ProtocolError("incomplete response: " + str(finish_reason))
    if wire_calls is not None:
        if not isinstance(wire_calls, list):
            raise ProtocolError("native wire calls must be an array")
        calls = []
        for index, item in enumerate(wire_calls):
            if not isinstance(item, dict) or item.get("type") != "function":
                raise ProtocolError("native call is not a function")
            function = item.get("function")
            if not isinstance(function, dict):
                raise ProtocolError("native function must be an object")
            arguments = function["arguments"]
            if isinstance(arguments, str):
                arguments = strict_json(arguments)
            calls.append(_call(function["name"], arguments, index))
        return {"content": raw, "tool_calls": calls}
    text = raw
    if text.lstrip().startswith("<think>"):
        end = text.find("</think>")
        if end == -1:
            raise ProtocolError("unfinished thinking block")
        text = text[end + len("</think>") :]
    payloads, rest = _raw_payloads(text, require_envelopes=True)
    calls = []
    for index, value in enumerate(payloads):
        if not isinstance(value, dict) or set(value) != {"name", "arguments"}:
            raise ProtocolError("tool object must contain name and arguments")
        calls.append(_call(value["name"], value["arguments"], index))
    return {"content": rest.strip(), "tool_calls": calls}


def _call(name, arguments, index):
    if (
        not isinstance(name, str)
        or not name
        or not isinstance(arguments, dict)
    ):
        raise ProtocolError("invalid native tool name or argument object")
    json.dumps(arguments, allow_nan=False)
    return {
        "call_id": "local_call_" + str(index),
        "name": name,
        "arguments": arguments,
    }


def intake(
    raw,
    finish_reason,
    tools,
    expected,
    wire_calls=None,
    registry_validator=None,
):
    """Evaluate syntax and Schema without invoking action handlers."""
    result = {
        "native_parse": False,
        "json_valid": json_status(raw, wire_calls),
        "response_complete": finish_reason in ("stop", "tool_calls"),
        "schema_valid": None,
        "registry_valid": None,
        "expected_behavior": False,
        "persona_valid": None,
        "reviewer": "deterministic frozen fixture rules",
    }
    try:
        reply = native_reply(raw, finish_reason, wire_calls)
        result["native_parse"] = True
        result["reply"] = reply
    except (ValueError, KeyError, TypeError) as error:
        result["error"] = str(error)
        # JSON evidence does not depend on envelope or finish state.
        return result
    calls = reply["tool_calls"]
    kind = expected.get("kind", "tool")
    if calls:
        from jsonschema import Draft202012Validator

        schemas = {
            tool["function"]["name"]: tool["function"]["parameters"]
            for tool in tools
        }
        result["json_valid"] = True
        errors = []
        for call in calls:
            schema = schemas.get(call["name"])
            if schema is None:
                errors.append("unknown tool: " + call["name"])
            else:
                errors.extend(
                    error.message
                    for error in Draft202012Validator(schema).iter_errors(
                        call["arguments"]
                    )
                )
        result["schema_valid"] = not errors
        result["schema_errors"] = errors
        if registry_validator:
            completed = subprocess.run(
                registry_validator,
                input=json.dumps({"calls": calls}),
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            if completed.returncode:
                raise RuntimeError(
                    "Registry validator failed: " + completed.stderr[-2000:]
                )
            registry = strict_json(completed.stdout)
            result["registry_valid"] = bool(registry["passed"])
            result["registry_result"] = registry
        target = expected.get("calls")
        actual = [
            {"name": call["name"], "arguments": call["arguments"]}
            for call in calls
        ]
        result["expected_behavior"] = (
            kind == "tool"
            and result["schema_valid"]
            and (target is None or actual == target)
        )
    elif kind != "tool":
        content = reply["content"]
        required = expected.get("contains_all", [])
        alternatives = expected.get("contains_any", [])
        forbidden = expected.get("excludes", [])
        passed = (
            bool(content)
            and all(x in content for x in required)
            and (not alternatives or any(x in content for x in alternatives))
            and not any(x in content for x in forbidden)
        )
        result["expected_behavior"] = passed
        if kind == "persona":
            result["persona_valid"] = passed
    return result
