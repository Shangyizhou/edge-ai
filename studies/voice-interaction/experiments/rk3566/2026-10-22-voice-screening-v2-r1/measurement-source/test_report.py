"""Verify repeated phase windows and small-sample/HTML behavior, without models."""
import unittest
from report import windows, distribution, render


class ReportTests(unittest.TestCase):
    def test_repeated_inference_windows_are_preserved(self):
        events=[dict(event='phase',name='inference',state=state,monotonic_seconds=t)
                for state,t in [('start',1),('end',2),('start',3),('end',5)]]
        resources=[dict(monotonic_seconds=t,cpu_seconds=t*2,pss_kib=100+t,rss_kib=200+t) for t in range(7)]
        summaries,unfinished=windows(events,resources,4,4096)
        inference=summaries['inference']
        self.assertEqual(inference['windows'],2)
        self.assertEqual(inference['seconds'],3)
        self.assertEqual(inference['average_cpu_cores']['value'],2)
        self.assertEqual(inference['cpu_capacity_percent']['value'],50)
        self.assertEqual(unfinished,{})

    def test_missing_latency_is_not_zero(self):
        stats=distribution([None,None])
        self.assertEqual(stats['n'],0)
        self.assertIsNone(stats['median'])
        self.assertIsNone(stats['p95_nearest_rank'])

    def test_nearest_rank_and_median_are_distinct(self):
        stats=distribution([3,1,2,None])
        self.assertEqual(stats['median'],2)
        self.assertEqual(stats['p95_nearest_rank'],3)
        self.assertEqual(stats['n'],3)

    def test_report_explains_metrics_before_measured_data(self):
        page=render(dict(cases=[], decisions=[], metric_definitions={}, limitations=[]))
        self.assertLess(page.index('id="conclusions"'), page.index('id="meaning"'))
        self.assertLess(page.index('id="meaning"'), page.index('id="data"'))
        self.assertLess(page.index('id="data"'), page.index('id="evidence"'))
        for term in ['字错误率', '首内容', 'PCM', 'PSS', '独立质量样本']:
            self.assertIn(term, page[page.index('id="meaning"'):page.index('id="data"')])
        self.assertNotIn('<details open', page)

    def test_verdict_text_is_html_escaped(self):
        text=render(dict(cases=[],decisions=[dict(candidate='<script>',disposition='待查',reason='& reason')],metric_definitions={},limitations=[]))
        self.assertNotIn('<script>',text)
        self.assertIn('&lt;script&gt;',text)
        self.assertIn('&amp; reason',text)


if __name__=='__main__':unittest.main()
