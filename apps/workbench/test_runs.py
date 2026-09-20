import tempfile
import unittest
from pathlib import Path
import adapters


class RunTests(unittest.TestCase):
    def test_persistent_binding_and_refresh(self):
        self.assertTrue(hasattr(adapters, 'RunStore'), 'persistent run adapter missing')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runs.sqlite3'
            store = adapters.RunStore(path)
            run = 'e224a4bc-f252-4aba-830d-ad2b9f637570'
            store.bind('task-one', run)
            store.bind('task-one', run)
            with self.assertRaises(ValueError):
                store.bind('task-two', run)
            with self.assertRaises(ValueError):
                store.bind('task-one', 'bad; command')
            store.refresh(run, lambda value: {'state': 'reported_success', 'claim_token': 'private'})
            item = adapters.RunStore(path).list()[0]
            self.assertEqual(item['state'], 'reported_success')
            self.assertNotIn('private', str(item))
            def offline(value):
                raise RuntimeError('transport failed secret')
            store.refresh(run, offline)
            item = store.list()[0]
            self.assertEqual(item['state'], 'reported_success')
            self.assertTrue(item['error'])
            self.assertNotIn('secret', str(item))


if __name__ == '__main__':
    unittest.main()
