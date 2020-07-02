from io import BytesIO

from django.test import TestCase

from drc_cmis.backend import BackendException, CMISDRCStorageBackend
from drc_cmis.client import CMISDRCClient

from .factories import EnkelvoudigInformatieObjectFactory
from .mixins import DMSMixin


class CMISDeleteDocumentTests(DMSMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.backend = CMISDRCStorageBackend()
        self.cmis_client = CMISDRCClient()

    def test_delete_document_no_document(self):
        with self.assertRaises(BackendException):
            self.backend.delete_document("identification")

    def test_delete_documents(self):
        eio = EnkelvoudigInformatieObjectFactory(identificatie="test")
        eio_dict = eio.__dict__

        cmis_doc = self.cmis_client.create_document(
            eio.identificatie, eio_dict.copy(), BytesIO(b"some content")
        )
        self.assertIsNotNone(cmis_doc)
        self.assertFalse(cmis_doc.verwijderd)

        self.backend.delete_document(cmis_doc.versionSeriesId)
        cmis_doc.reload()
        self.assertTrue(cmis_doc.verwijderd)
