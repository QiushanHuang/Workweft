import unittest
from import_summary import summarize_import

class SummaryTests(unittest.TestCase):
    def test_counts_and_policy(self):
        self.assertEqual(summarize_import({'projects':2,'tasks':3,'assets':4}), '2 projects · 3 tasks · 4 references\nImport creates new copies; existing data is not overwritten. Tasks reset to todo.')
    def test_bad_counts(self):
        for bad in [None,{}, {'projects':True,'tasks':0,'assets':0},{'projects':-1,'tasks':0,'assets':0},{'projects':'1','tasks':0,'assets':0}]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                summarize_import(bad)
