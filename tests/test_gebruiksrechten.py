import datetime

from django.test import TestCase
from django.utils import timezone

from drc_cmis.client import CMISDRCClient, exceptions


class CMISGebruiksrechtenTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = CMISDRCClient()

    def tearDown(self):
        super().tearDown()
        self.client.delete_cmis_folders_in_base()

    def test_create(self):

        data = {
            "informatieobject": "/some/url/",
            "startdatum": "2018-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        cmis_gebruikrechten = self.client.create_cmis_gebruiksrechten(data)

        self.assertEqual(data["informatieobject"], cmis_gebruikrechten.informatieobject)
        self.assertEqual(
            data["startdatum"],
            convert_timestamp_to_json_datetime(cmis_gebruikrechten.startdatum),
        )
        self.assertEqual(
            data["omschrijving_voorwaarden"],
            cmis_gebruikrechten.omschrijving_voorwaarden,
        )

    def test_get_all(self):
        data = {
            "informatieobject": "/some/url/",
            "startdatum": "2018-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        sent_gebruiksrechten = []

        for _ in range(3):
            sent_gebruiksrechten.append(self.client.create_cmis_gebruiksrechten(data))

        retrieved_gebruiksrechten = self.client.get_all_cmis_gebruiksrechten()

        self.assertEqual(retrieved_gebruiksrechten["total_count"], 3)

    def test_get_one(self):

        data = {
            "informatieobject": "/some/url/",
            "startdatum": "2018-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        cmis_gebruikrechten = self.client.create_cmis_gebruiksrechten(data)

        uuid = cmis_gebruikrechten.versionSeriesId

        retrieved_gebruiksrechten = self.client.get_a_cmis_gebruiksrechten(uuid)

        self.assertEqual(
            data["informatieobject"], retrieved_gebruiksrechten.informatieobject
        )
        self.assertEqual(
            data["startdatum"],
            convert_timestamp_to_json_datetime(retrieved_gebruiksrechten.startdatum),
        )
        self.assertEqual(
            data["omschrijving_voorwaarden"],
            retrieved_gebruiksrechten.omschrijving_voorwaarden,
        )

    def test_delete(self):

        data = {
            "informatieobject": "/some/url/",
            "startdatum": "2018-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        cmis_gebruikrechten = self.client.create_cmis_gebruiksrechten(data)

        uuid = cmis_gebruikrechten.versionSeriesId

        self.client.delete_cmis_geruiksrechten(uuid)

        with self.assertRaises(exceptions.DocumentDoesNotExistError):
            self.client.get_a_cmis_gebruiksrechten(uuid)


def convert_timestamp_to_json_datetime(timestamp):
    """
    Takes an int such as 1467717221000 as input and returns 2016-07-05T1:13:41Z as output.
    """
    if timestamp is not None:
        timestamp = int(str(timestamp)[:10])
        django_datetime = timezone.make_aware(
            datetime.datetime.fromtimestamp(timestamp)
        ) + datetime.timedelta(hours=6)
        json_datetime = django_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        return json_datetime
