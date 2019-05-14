from django.test import TestCase

from drc_cmis.exceptions import SyncException
from drc_cmis.models import ChangeLog

from ..mixins import DMSMixin


class CMISClientTests(DMSMixin, TestCase):
    def test_run_sync_dryrun(self):
        self.cmis_client.sync(dryrun=True)

    def test_run_sync(self):
        result = self.cmis_client.sync()
        self.assertGreaterEqual(result.get("created"), 0)
        self.assertEqual(result.get("updated"), 0)
        self.assertEqual(result.get("deleted"), 0)
        self.assertEqual(result.get("security"), 0)
        self.assertGreater(result.get("failed"), 0)

    def test_run_sync_twice_at_the_same_time(self):
        ChangeLog.objects.create(token=1)

        with self.assertRaises(SyncException) as exc:
            self.cmis_client.sync()

        self.assertEqual(exc.exception.args, ("A synchronization process is already running.",))

    def test_run_sync_twice(self):
        result1 = self.cmis_client.sync()
        self.assertGreaterEqual(result1.get("created"), 0)
        self.assertEqual(result1.get("updated"), 0)
        self.assertEqual(result1.get("deleted"), 0)
        self.assertEqual(result1.get("security"), 0)
        self.assertGreater(result1.get("failed"), 0)

        result2 = self.cmis_client.sync()
        self.assertEqual(result2, {})
