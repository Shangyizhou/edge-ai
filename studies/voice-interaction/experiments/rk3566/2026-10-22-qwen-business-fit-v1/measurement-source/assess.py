"""Separate generation completion, JSON syntax, parsing, binding and intent."""
import json
from pathlib import Path
import sys

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, '/home/orangepi/code/ros-robot/ros2_ws/src/robot_agent')
from robot_agent.actions.capabilities import create_default_actions
from robot_agent.actions.perception import PerceptionActions
from robot_agent.conversation.local_model import _parse_legacy_reply
from robot_agent.results import _json_value


def assess_case(row, tools, registry):
    result = dict(row, raw_status=row['status'], json_valid=False,
                  protocol_valid=False, registry_valid=None, intent_pass=False,
                  case_pass=False, assessment_errors=[])
    final = row.get('native_final') or {}
    result['generation_complete'] = final.get('stop') is True and final.get('stop_type') == 'eos'
    try:
        json.loads(row['raw'])
        result['json_valid'] = True
    except (ValueError, TypeError) as error:
        result['assessment_errors'].append('JSON: ' + str(error))
        result['status'] = 'invalid_json'
        return result
    try:
        reply = _parse_legacy_reply(row['raw'], row['id'], tools)
        result.update(protocol_valid=True, response=reply.response,
                      calls=[dict(name=c.name, arguments=_json_value(c.arguments)) for c in reply.tool_calls])
    except ValueError as error:
        result['assessment_errors'].append('Protocol: ' + str(error))
        result['status'] = 'invalid_call_protocol'
        return result
    try:
        if reply.tool_calls:
            registry.validate_calls(reply.tool_calls)
        result['registry_valid'] = True
    except ValueError as error:
        result['registry_valid'] = False
        result['assessment_errors'].append('Registry: ' + str(error))
    result['intent_pass'] = result['calls'] == row['expected']
    result['status'] = ('complete' if result['generation_complete'] else 'incomplete_generation')
    result['case_pass'] = result['generation_complete'] and result['protocol_valid'] and result['registry_valid'] and result['intent_pass']
    return result


def main():
    raw = json.loads((EXP / 'results.json').read_text())
    tools = json.loads((EXP / 'tools-subset.json').read_text())
    registry = create_default_actions().registry
    registry.register_perception(PerceptionActions(None))
    assessed=[]
    for row in raw['cases']:
        assessed.append(assess_case(row, tools, registry))
    report=dict(raw,cases=assessed,assessment_note='Derived from unchanged raw responses; native stop_type=eos establishes completed generation, not absent stopped_eos. JSON syntax, protocol, Registry and intent are separate checks.')
    (EXP / 'assessment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print([(r['id'],r['generation_complete'],r['json_valid'],r['protocol_valid'],r['registry_valid'],r['intent_pass']) for r in assessed])

if __name__=='__main__':main()
