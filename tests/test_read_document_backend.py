from io import BytesIO

from django.test import TestCase

from drc_cmis.backend import BackendException, CMISDRCStorageBackend

from .factories import EnkelvoudigInformatieObjectFactory
from .mixins import DMSMixin


class CMISReadDocumentTests(DMSMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.backend = CMISDRCStorageBackend()

    def test_get_documents(self):
        eio = EnkelvoudigInformatieObjectFactory()
        doc = self.backend.create_document(eio.__dict__, BytesIO(b"some content"))
        self.assertIsNotNone(doc)

        # Because we need to give alfresco some time to index the document there is a timeout
        import time

        time.sleep(25)

        documents = self.backend.get_documents()
        self.assertEqual(len(documents.results), 1)

    def test_get_documents_empty(self):
        documents = self.backend.get_documents()

        self.assertEqual(len(documents.results), 0)

    def test_get_document(self):
        eio = EnkelvoudigInformatieObjectFactory(identificatie="test")
        eio_dict = eio.__dict__

        document = self.backend.create_document(eio_dict.copy(), None)
        self.assertIsNotNone(document)
        self.assertEqual(document.identificatie, "test")

        fetched_document = self.backend.get_document(document.url.split("/")[-1])
        self.assertEqual(document.titel, fetched_document.titel)

    def test_get_document_no_document(self):
        with self.assertRaises(BackendException):
            self.backend.get_document("some-randonm-string")
