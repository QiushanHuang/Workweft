import unittest
import importlib.util


class InterchangeTest(unittest.TestCase):
    def test_minddesk_metadata_roundtrip(self):
        self.assertIsNotNone(importlib.util.find_spec('interchange'))
        from interchange import to_minddesk, from_minddesk
        source={'projects':[{'id':'p','title':'Project','description':'Details','archived':False}],
                'tasks':[{'id':'t','project_id':'p','title':'Task','description':'Body','status':'todo','dependencies':[]}],
                'assets':[{'id':'a','task_id':'t','title':'File','kind':'local_file','target':'/tmp/example.txt','description':'Pointer'}]}
        native=to_minddesk(source)
        self.assertEqual(native['format'],'minddesk.export.manifest')
        restored=from_minddesk(native)
        self.assertEqual(restored['tasks'][0]['title'],'Task')
        self.assertEqual(restored['assets'][0]['target'],'/tmp/example.txt')
        self.assertEqual(restored['tasks'][0]['status'],'todo')
