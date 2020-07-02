from django.test import TestCase

from drc_cmis.client import CMISDRCClient, exceptions


class CMISOioTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = CMISDRCClient()

    def tearDown(self):
        super().tearDown()
        self.client.delete_cmis_folders_in_base()

    def test_create_with_zaak(self):

        data = {
            "informatieobject": "/some/url/",
            "object_type": "zaak",
            "zaak": "/some/other/url/",
        }

        cmis_oio = self.client.create_cmis_oio(data)

        self.assertEqual(data["informatieobject"], cmis_oio.informatieobject)
        self.assertEqual(data["object_type"], cmis_oio.object_type)
        self.assertEqual(None, cmis_oio.zaak_url)

    def test_get_all(self):
        data = {
            "informatieobject": "/some/url/",
            "object_type": "zaak",
            "zaak": "/some/other/url/",
        }

        sent_oio = []

        for _ in range(3):
            sent_oio.append(self.client.create_cmis_oio(data))

        retrieved_oio = self.client.get_all_cmis_oio()

        self.assertEqual(retrieved_oio["total_count"], 3)

    def test_get_one(self):
        data_1 = {
            "informatieobject": "/some/url/",
            "object_type": "zaak",
            "zaak": "/some/other/url/",
        }

        data_2 = {
            "informatieobject": "/some/fun/url/",
            "object_type": "zaak",
            "zaak": "/another/url/",
        }

        cmis_oio_1 = self.client.create_cmis_oio(data_1)
        self.client.create_cmis_oio(data_2)

        uuid = cmis_oio_1.versionSeriesId

        retrieved_oio = self.client.get_a_cmis_oio(uuid)

        self.assertEqual(data_1["informatieobject"], retrieved_oio.informatieobject)
        self.assertEqual(data_1["object_type"], retrieved_oio.object_type)
        self.assertEqual(None, retrieved_oio.zaak_url)

    def test_delete(self):
        data = {
            "informatieobject": "/some/url/",
            "object_type": "zaak",
            "zaak": "/some/other/url/",
        }

        cmis_oio = self.client.create_cmis_oio(data)

        uuid = cmis_oio.versionSeriesId

        self.client.delete_cmis_oio(uuid)

        with self.assertRaises(exceptions.DocumentDoesNotExistError):
            self.client.get_a_cmis_oio(uuid)
