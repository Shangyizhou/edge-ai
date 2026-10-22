"""Native Qwen tool syntax and observable Agent intake checks."""

import json
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

    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=invalid_constant)


def native_reply(raw, finish_reason="stop", wire_calls=None):
    """Return an Agent-equivalent complete reply; plain JSON cannot call tools."""
    if finish_reason not in ("stop", "tool_calls"):
        raise ProtocolError("incomplete response: " + str(finish_reason))
    if wire_calls is not None:
        calls = []
        for index, item in enumerate(wire_calls):
            if item.get("type") != "function":
                raise ProtocolError("native call is not a function")
            function = item["function"]
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
        text = text[end + len("</think>"):]
    matches = list(re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.S))
    rest = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.S)
    if "<tool_call>" in rest or "</tool_call>" in rest:
        raise ProtocolError("unfinished or unmatched tool marker")
    calls = []
    for index, match in enumerate(matches):
        value = strict_json(match.group(1))
        if not isinstance(value, dict) or set(value) != {"name", "arguments"}:
            raise ProtocolError("tool object must contain name and arguments")
        calls.append(_call(value["name"], value["arguments"], index))
    return {"content": rest.strip(), "tool_calls": calls}


def _call(name, arguments, index):
    if not isinstance(name, str) or not name or not isinstance(arguments, dict):
        raise ProtocolError("invalid native tool name or argument object")
    return {"call_id": "local_call_" + str(index), "name": name,
            "arguments": arguments}


def intake(raw, finish_reason, tools, expected, wire_calls=None,
           registry_validator=None):
    """Evaluate syntax and schema separately; invoke no action implementation."""
    result = {"native_parse": False, "json_valid": None,
              "schema_valid": None, "registry_valid": None,
              "expected_behavior": False, "persona_valid": None,
              "reviewer": "deterministic frozen fixture rules"}
    try:
        reply = native_reply(raw, finish_reason, wire_calls)
        result["native_parse"] = True
        result["reply"] = reply
    except (ProtocolError, json.JSONDecodeError, KeyError, TypeError) as error:
        result["error"] = str(error)
        # A malformed native JSON payload is distinct from truncation.
        result["json_valid"] = False if "<tool_call>" in raw else None
        return result
    calls = reply["tool_calls"]
    kind = expected.get("kind", "tool")
    if calls:
        from jsonschema import Draft202012Validator

        schemas = {tool["function"]["name"]: tool["function"]["parameters"]
                   for tool in tools}
        result["json_valid"] = True
        errors = []
        for call in calls:
            schema = schemas.get(call["name"])
            if schema is None:
                errors.append("unknown tool: " + call["name"])
            else:
                errors.extend(error.message for error in
                              Draft202012Validator(schema).iter_errors(
                                  call["arguments"]))
        result["schema_valid"] = not errors
        result["schema_errors"] = errors
        if registry_validator:
            completed = subprocess.run(
                registry_validator, input=json.dumps({"calls": calls}),
                text=True, capture_output=True, check=False, timeout=30)
            if completed.returncode:
                raise RuntimeError("Registry validator failed: " +
                                   completed.stderr[-2000:])
            registry = strict_json(completed.stdout)
            result["registry_valid"] = bool(registry["passed"])
            result["registry_result"] = registry
        target = expected.get("calls")
        actual = [{"name": call["name"], "arguments": call["arguments"]}
                  for call in calls]
        result["expected_behavior"] = (
            kind == "tool" and result["schema_valid"] and
            (target is None or actual == target))
    elif kind != "tool":
        content = reply["content"]
        required = expected.get("contains_all", [])
        alternatives = expected.get("contains_any", [])
        forbidden = expected.get("excludes", [])
        passed = (bool(content) and all(x in content for x in required) and
                  (not alternatives or any(x in content for x in alternatives))
                  and not any(x in content for x in forbidden))
        result["expected_behavior"] = passed
        if kind == "persona":
            result["persona_valid"] = passed
    return result
