from io import BytesIO

from django.test import TestCase
from django.utils import timezone

from drc_cmis.backend import CMISDRCStorageBackend
from drc_cmis.client import CMISDRCClient

from .factories import EnkelvoudigInformatieObjectFactory
from .mixins import DMSMixin


class CMISCreateConnectionTests(DMSMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.backend = CMISDRCStorageBackend()
        self.cmis_client = CMISDRCClient()

    def test_create_document_case_connection(self):
        # Create zaaktype_folder
        zaaktype_folder = self.cmis_client.get_or_create_zaaktype_folder(
            {
                "url": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                "identificatie": 1,
                "omschrijving": "Melding Openbare Ruimte",
            }
        )

        # Create zaak_folder
        self.cmis_client.get_or_create_zaak_folder(
            {
                "url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
                "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
                "zaaktype": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                "startdatum": "2023-12-06",
                "einddatum": None,
                "registratiedatum": "2019-04-17",
                "bronorganisatie": "509381406",
            },
            zaaktype_folder,
        )

        # Create document
        eio = EnkelvoudigInformatieObjectFactory(identificatie="test")
        eio_dict = eio.__dict__

        document = self.backend.create_document(
            eio_dict.copy(), BytesIO(b"some content")
        )
        self.assertIsNotNone(document)

        connection = self.backend.create_document_case_connection(
            {
                "informatieobject": document.url,
                "object": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            }
        )
        self.assertIsNotNone(connection)

    def test_create_document_case_connection_without_case_folder(self):
        # Create document
        eio = EnkelvoudigInformatieObjectFactory(identificatie="test")
        eio_dict = eio.__dict__

        document = self.backend.create_document(eio_dict.copy(), None)
        self.assertIsNotNone(document)

        data = {
            "informatieobject": document.url,
            "object": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "registratiedatum": timezone.now(),
        }
        connection = self.backend.create_document_case_connection(data)
        self.assertIsNotNone(connection)

    def test_create_document_case_connection_create_copy(self):
        # Create zaaktype_folder
        zaaktype_folder = self.cmis_client.get_or_create_zaaktype_folder(
            {
                "url": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                "identificatie": 1,
                "omschrijving": "Melding Openbare Ruimte",
            }
        )

        # Create zaak_folders
        self.cmis_client.get_or_create_zaak_folder(
            {
                "url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
                "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
                "zaaktype": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                "startdatum": "2023-12-06",
                "einddatum": None,
                "registratiedatum": "2019-04-17",
                "bronorganisatie": "509381406",
            },
            zaaktype_folder,
        )

        self.cmis_client.get_or_create_zaak_folder(
            {
                "url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid2",
                "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184b",
                "zaaktype": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                "startdatum": "2023-12-06",
                "einddatum": None,
                "registratiedatum": "2019-04-17",
                "bronorganisatie": "509381406",
            },
            zaaktype_folder,
        )

        # Create document
        eio = EnkelvoudigInformatieObjectFactory(identificatie="test")
        eio_dict = eio.__dict__

        document = self.backend.create_document(eio_dict.copy(), None)
        self.assertIsNotNone(document)

        connection1 = self.backend.create_document_case_connection(
            {
                "informatieobject": document.url,
                "object": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            }
        )

        connection2 = self.backend.create_document_case_connection(
            {
                "informatieobject": document.url,
                "object": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid2",
            }
        )

        self.assertIsNotNone(connection1)
        self.assertIsNotNone(connection2)
        # self.assertNotEqual(connection1, connection2)  # TODO: Fix this!!!
