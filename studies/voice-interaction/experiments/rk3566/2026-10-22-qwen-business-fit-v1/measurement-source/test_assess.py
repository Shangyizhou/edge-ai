"""Check assessment boundaries without generating model outputs."""
import json
import unittest
from assess import assess_case, create_default_actions


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.registry=create_default_actions().registry
        self.tools=self.registry.schemas()

    def row(self,raw,expected=(),final=None):
        return dict(id='synthetic-assessment-regression',status='output_limit_or_missing_stop',raw=raw,expected=list(expected),native_final=final or dict(stop=True,stop_type='eos'))

    def test_native_eos_not_missing_stopped_eos_establishes_completion(self):
        row=self.row('{"fc":["volume_set(level=30)"],"res":"准备调整"}',[dict(name='volume_set',arguments=dict(level=30))])
        checked=assess_case(row,self.tools,self.registry)
        self.assertTrue(checked['case_pass'])
        self.assertEqual(checked['raw_status'],'output_limit_or_missing_stop')

    def test_valid_json_is_not_valid_function_protocol(self):
        checked=assess_case(self.row('{"fc":["volume_set","level","30"],"res":"回复"}'),self.tools,self.registry)
        self.assertTrue(checked['json_valid'])
        self.assertFalse(checked['protocol_valid'])
        self.assertFalse(checked['case_pass'])

    def test_wrong_argument_can_parse_but_fail_binding(self):
        checked=assess_case(self.row('{"fc":["volume_set(unknown=30)"],"res":"回复"}'),self.tools,self.registry)
        self.assertTrue(checked['protocol_valid'])
        self.assertFalse(checked['registry_valid'])
        self.assertFalse(checked['case_pass'])

    def test_valid_call_is_not_correct_intent(self):
        checked=assess_case(self.row('{"fc":["volume_set(level=30)"],"res":"回复"}'),self.tools,self.registry)
        self.assertTrue(checked['registry_valid'])
        self.assertFalse(checked['intent_pass'])

    def test_limited_generation_does_not_pass_even_with_parseable_prefix(self):
        checked=assess_case(self.row('{"fc":[],"res":"说明"}',final=dict(stop=True,stop_type='limit')),self.tools,self.registry)
        self.assertTrue(checked['protocol_valid'])
        self.assertTrue(checked['intent_pass'])
        self.assertFalse(checked['generation_complete'])
        self.assertFalse(checked['case_pass'])

if __name__=='__main__':unittest.main()
