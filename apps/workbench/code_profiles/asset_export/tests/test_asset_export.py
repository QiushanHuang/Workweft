import copy
import json
import unittest
from asset_export import export_references


class ExportTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(export_references([]), '# File references\n\nNo references registered.\n')

    def test_roundtrip_and_no_mutation(self):
        values=[{'id':'a','task_id':'t','title':'中文 * title', 'kind':'external_ref',
                 'target':'minddesk:opaque', 'description':'do not interpret'}]
        original=copy.deepcopy(values)
        text=export_references(values)
        self.assertTrue(text.startswith('# File references\n'))
        fence=next(line for line in text.splitlines() if line.endswith('json'))
        self.assertEqual(json.loads(text.split(fence+'\n',1)[1].rsplit(fence[:-4],1)[0].strip()),values)
        self.assertEqual(values,original)
        self.assertIn('中文',text)

    def test_untrusted_markdown_is_only_in_fenced_json(self):
        values=[{'title':'```\n<script>alert(1)</script>\n````','target':'/nonexistent/file'}]
        text=export_references(values)
        fence=next(line for line in text.splitlines() if line.endswith('json'))[:-4]
        self.assertGreaterEqual(len(fence),5)
        self.assertEqual(text.count('\n'+fence+'\n'),1)
        self.assertEqual(json.loads(text.split(fence+'json\n',1)[1].rsplit(fence,1)[0].strip()),values)

    def test_invalid_shapes(self):
        for value in (None, {}, 'text', [42]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                export_references(value)
