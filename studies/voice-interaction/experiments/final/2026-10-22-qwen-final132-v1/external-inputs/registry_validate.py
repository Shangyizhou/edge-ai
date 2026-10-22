"""Validate immutable ros-robot source snapshot without invoking handlers."""
import json
import sys
from pathlib import Path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / 'ros-robot/ros2_ws/src/robot_agent'))
from robot_agent.actions.capabilities import create_default_actions
from robot_agent.actions.perception import PerceptionActions
from robot_agent.actions.registry import PlanValidationError
from robot_agent.results import ToolCall
registry = create_default_actions().registry
registry.register_perception(PerceptionActions(None))
value = json.load(sys.stdin)
calls = [ToolCall(x['call_id'], x['name'], x['arguments']) for x in value['calls']]
try:
    plan = registry.validate_calls(calls)
except PlanValidationError as error:
    print(json.dumps({'passed': False, 'reason': str(error)}, ensure_ascii=False))
else:
    print(json.dumps({'passed': True, 'commands': [{'name': x.name, 'parameters': dict(x.parameters), 'tool_call_id': x.tool_call_id} for x in plan.commands]}, ensure_ascii=False))
