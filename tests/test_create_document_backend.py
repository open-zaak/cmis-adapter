from io import BytesIO

from django.test import TestCase

from rest_framework.exceptions import ErrorDetail

from drc_cmis.backend import BackendException, CMISDRCStorageBackend

from .factories import EnkelvoudigInformatieObjectFactory
from .mixins import DMSMixin


class CMISCreateDocumentTests(DMSMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.backend = CMISDRCStorageBackend()

    def test_create_document(self):
        eio = EnkelvoudigInformatieObjectFactory()
        document = self.backend.create_document(
            eio.__dict__.copy(), BytesIO(b"some content")
        )
        self.assertIsNotNone(document)

    def test_create_document_error_identification_exists(self):
        eio = EnkelvoudigInformatieObjectFactory()
        eio_dict = eio.__dict__
        eio_dict["identificatie"] = "test"

        document = self.backend.create_document(
            eio_dict.copy(), BytesIO(b"some content")
        )
        self.assertIsNotNone(document)

        eio_dict["titel"] = "gewoon_een_andere_titel"

        with self.assertRaises(BackendException) as exception:
            self.backend.create_document(eio_dict.copy(), BytesIO(b"some content"))
        self.assertEqual(
            exception.exception.detail,
            {
                None: ErrorDetail(
                    string=f"Document identificatie {eio.identificatie} is niet uniek.",
                    code="invalid",
                )
            },
        )