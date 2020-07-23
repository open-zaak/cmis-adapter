import io
import uuid

from django.test import TestCase

from .mixins import DMSSOAPMixin


class CMISSOAPClientTests(DMSSOAPMixin, TestCase):
    def test_create_document_without_content(self):

        identification = str(uuid.uuid4())
        properties = {
            "bronorganisatie": "159351741",
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
            "auteur": "test_auteur",
            "formaat": "txt",
            "taal": "eng",
            "bestandsnaam": "dummy.txt",
            "link": "http://een.link",
            "beschrijving": "test_beschrijving",
            "vertrouwelijkheidaanduiding": "openbaar",
        }

        document = self.cmis_client.create_document(
            identification=identification, data=properties,
        )

        self.assertEqual(document.identificatie, identification)
        self.assertEqual(document.bronorganisatie, "159351741")
        self.assertEqual(document.creatiedatum.strftime("%Y-%m-%d"), "2018-06-27")
        self.assertEqual(document.titel, "detailed summary")
        self.assertEqual(document.auteur, "test_auteur")
        self.assertEqual(document.formaat, "txt")
        self.assertEqual(document.taal, "eng")
        self.assertEqual(document.versie, 1)
        self.assertEqual(document.bestandsnaam, "dummy.txt")
        self.assertEqual(document.link, "http://een.link")
        self.assertEqual(document.beschrijving, "test_beschrijving")
        self.assertEqual(document.vertrouwelijkheidaanduiding, "openbaar")

    def test_create_document_with_content(self):

        identification = str(uuid.uuid4())
        properties = {
            "bronorganisatie": "159351741",
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
            "auteur": "test_auteur",
            "formaat": "txt",
            "taal": "eng",
            "bestandsnaam": "dummy.txt",
            "link": "http://een.link",
            "beschrijving": "test_beschrijving",
            "vertrouwelijkheidaanduiding": "openbaar",
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content,
        )

        self.assertEqual(document.identificatie, identification)
        self.assertEqual(document.bronorganisatie, "159351741")
        self.assertEqual(document.creatiedatum.strftime("%Y-%m-%d"), "2018-06-27")
        self.assertEqual(document.titel, "detailed summary")
        self.assertEqual(document.auteur, "test_auteur")
        self.assertEqual(document.formaat, "txt")
        self.assertEqual(document.taal, "eng")
        self.assertEqual(document.versie, 1)
        self.assertEqual(document.bestandsnaam, "dummy.txt")
        self.assertEqual(document.link, "http://een.link")
        self.assertEqual(document.beschrijving, "test_beschrijving")
        self.assertEqual(document.vertrouwelijkheidaanduiding, "openbaar")

        self.assertIsNotNone(document.contentStreamId)
        self.assertEqual(document.contentStreamLength, len("some file content"))

        # Retrieving the actual content
        posted_content = document.get_content_stream()
        content.seek(0)
        self.assertEqual(posted_content.read(), content.read())
