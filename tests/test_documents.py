import datetime
import io
import os
import uuid
from unittest import skipIf
from unittest.mock import patch

from django.test import TestCase, override_settings, tag
from django.utils import timezone

from freezegun import freeze_time

from drc_cmis.models import CMISConfig, UrlMapping
from drc_cmis.utils.exceptions import DocumentDoesNotExistError, FolderDoesNotExistError
from drc_cmis.webservice.utils import URLTooLongException

from .mixins import DMSMixin


@freeze_time("2020-07-27 12:00:00")
class CMISDocumentTests(DMSMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        config = CMISConfig.get_solo()

        UrlMapping.objects.create(
            long_pattern="https://drc.utrechtproeftuin.nl",
            short_pattern="https://drc.nl",
            config=config,
        )

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=False)
    def test_build_properties_webservice(self):
        properties = {
            "identificatie": str(uuid.uuid4()),
            "bronorganisatie": "159351741",
            "integriteitwaarde": "Something",
            "verwijderd": "false",
            "ontvangstdatum": "2020-07-28",
            "versie": "1.0",
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }

        types = {
            "identificatie": "propertyString",
            "bronorganisatie": "propertyString",
            "integriteitwaarde": "propertyString",
            "verwijderd": "propertyBoolean",
            "ontvangstdatum": "propertyDateTime",
            "versie": "propertyDecimal",
            "creatiedatum": "propertyDateTime",
            "titel": "propertyString",
        }
        document = self.cmis_client.create_document(
            identification=properties["identificatie"],
            data=properties,
            bronorganisatie="159351741",
        )

        built_properties = document.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)
        self.assertIn("drc:document__uuid", built_properties)
        self.assertIsNotNone(built_properties["drc:document__uuid"])

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            if prop_name.split("__")[-1] in properties:
                converted_prop_name = prop_name.split("__")[-1]
                self.assertEqual(types[converted_prop_name], prop_dict["type"])
                self.assertEqual(properties[converted_prop_name], prop_dict["value"])

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=False)
    def test_build_properties_without_identificatie_webservice(self):
        # No identificatie
        properties = {
            "bronorganisatie": "159351741",
            "integriteitwaarde": "Something",
            "verwijderd": "false",
            "ontvangstdatum": "2020-07-28",
            "versie": "1.0",
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }

        document = self.cmis_client.create_document(
            data=properties, bronorganisatie="159351741", identification=None
        )

        built_properties = document.build_properties(data=properties)

        self.assertIn("drc:document__uuid", built_properties)
        self.assertIn("drc:document__identificatie", built_properties)
        self.assertEqual(
            built_properties["drc:document__uuid"],
            built_properties["drc:document__identificatie"],
        )

        # Empty identificatie
        properties["identificatie"] = ""

        built_properties = document.build_properties(data=properties)

        self.assertIn("drc:document__uuid", built_properties)
        self.assertIn("drc:document__identificatie", built_properties)
        self.assertEqual(
            built_properties["drc:document__uuid"],
            built_properties["drc:document__identificatie"],
        )

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=True)
    def test_build_properties_webservice_with_mapping(self):
        properties = {
            "identificatie": str(uuid.uuid4()),
            "bronorganisatie": "159351741",
            "integriteitwaarde": "Something",
            "verwijderd": "false",
            "ontvangstdatum": "2020-07-28",
            "versie": "1.0",
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
            "informatieobjecttype": "https://drc.utrechtproeftuin.nl/catalogi/api/v1/informatieobjecttypen/6dd973a8-57da-4200-9d77-8045e5678abe",
            "link": "http://een.link",
        }

        types = {
            "identificatie": "propertyString",
            "bronorganisatie": "propertyString",
            "integriteitwaarde": "propertyString",
            "verwijderd": "propertyBoolean",
            "ontvangstdatum": "propertyDateTime",
            "versie": "propertyDecimal",
            "creatiedatum": "propertyDateTime",
            "titel": "propertyString",
            "informatieobjecttype": "propertyString",
            "link": "propertyString",
        }
        document = self.cmis_client.create_document(
            identification=properties["identificatie"],
            data=properties,
            bronorganisatie="159351741",
        )

        built_properties = document.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)
        self.assertIn("drc:document__uuid", built_properties)
        self.assertIsNotNone(built_properties["drc:document__uuid"])

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            if prop_name.split("__")[-1] in properties:
                converted_prop_name = prop_name.split("__")[-1]
                if converted_prop_name == "informatieobjecttype":
                    self.assertEqual(
                        "https://drc.nl/catalogi/api/v1/informatieobjecttypen/6dd973a8-57da-4200-9d77-8045e5678abe",
                        prop_dict["value"],
                    )
                else:
                    self.assertEqual(
                        properties[converted_prop_name], prop_dict["value"]
                    )
                self.assertEqual(types[converted_prop_name], prop_dict["type"])

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=True)
    def test_build_properties_webservice_with_mapping_url_too_long(self):
        properties = {
            "bronorganisatie": "159351741",
            "integriteitwaarde": "Something",
            "verwijderd": "false",
            "ontvangstdatum": "2020-07-28",
            "versie": "1.0",
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
            "informatieobjecttype": "https://drc.utrechtproeftuin.nl/catalogi/api/v1/informatieobjecttypen/6dd973a8-57da-4200-9d77-8045e5678abe/this-url-will-be-too-long-when-shrunk",
            "link": "http://een.link",
        }

        with self.assertRaises(URLTooLongException):
            self.cmis_client.create_document(
                identification="2edb313f-5607-4c78-bd4f-50981711828d",
                data=properties,
                bronorganisatie="159351741",
            )

    @skipIf(
        os.getenv("CMIS_BINDING") != "BROWSER",
        "The properties are built differently with different bindings",
    )
    def test_build_properties_browser(self):
        properties = {
            "integriteitwaarde": "Something",
            "verwijderd": "false",
            "ontvangstdatum": datetime.date(2020, 7, 27),
            "versie": 1,
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }

        identification = str(uuid.uuid4())
        document = self.cmis_client.create_document(
            identification=identification, bronorganisatie="159351741", data=properties
        )

        built_properties = document.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)
        self.assertIn("drc:document__uuid", built_properties)
        self.assertIsNotNone(built_properties["drc:document__uuid"])

        for prop_name, prop_value in built_properties.items():
            if prop_name.split("__")[-1] in properties:
                converted_prop_name = prop_name.split("__")[-1]
                self.assertEqual(properties[converted_prop_name], prop_value)

    @skipIf(
        os.getenv("CMIS_BINDING") != "BROWSER",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=False)
    def test_build_properties_without_identificatie_browser(self):
        # No identificatie
        properties = {
            "integriteitwaarde": "Something",
            "verwijderd": "false",
            "ontvangstdatum": datetime.date(2020, 7, 27),
            "versie": 1,
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }

        document = self.cmis_client.create_document(
            data=properties, bronorganisatie="159351741", identification=None
        )

        built_properties = document.build_properties(data=properties)

        self.assertIn("drc:document__uuid", built_properties)
        self.assertIn("drc:document__identificatie", built_properties)
        self.assertEqual(
            built_properties["drc:document__uuid"],
            built_properties["drc:document__identificatie"],
        )

        # Empty identificatie
        properties["identificatie"] = ""

        built_properties = document.build_properties(data=properties)

        self.assertIn("drc:document__uuid", built_properties)
        self.assertIn("drc:document__identificatie", built_properties)
        self.assertEqual(
            built_properties["drc:document__uuid"],
            built_properties["drc:document__identificatie"],
        )

    @tag("alfresco")
    def test_checkout_document(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"some file content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        pwc = document.checkout()

        self.assertEqual(pwc.versionLabel, "pwc")

    @tag("alfresco")
    def test_document_with_pdf_attachment(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "bestandsnaam": "filename.pdf",
        }
        # Contains non-UTF-8 characters
        content = io.BytesIO(
            b"%PDF-1.4\n%\xc3\xa4\xc3\xbc\xc3\xb6\n2 0 obj\n<</Length 3 0 R/Filter/FlateDecode>>\nstream\nx\x9c"
        )
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        posted_content = document.get_content_stream()
        content.seek(0)
        self.assertEqual(posted_content.read(), content.read())

        self.assertEqual("application/pdf", document.contentStreamMimeType)

    @tag("alfresco")
    def test_checkin_document(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"some file content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        pwc = document.checkout()
        self.assertEqual(pwc.versionLabel, "pwc")

        new_doc = pwc.checkin(checkin_comment="Testing Check-in...")
        self.assertEqual(new_doc.versionLabel, "2.0")

    @tag("alfresco")
    def test_get_document(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"some file content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        document.checkout()
        retrieved_doc = self.cmis_client.get_document(drc_uuid=document.uuid)
        self.assertEqual(retrieved_doc.versionLabel, "pwc")

    def test_get_pwc(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"some file content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )
        document.checkout()

        # Retrieve pwc from the original document
        pwc = document.get_latest_version()
        self.assertTrue(pwc.isVersionSeriesCheckedOut)

    def test_get_pwc_with_no_checked_out_doc(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"some file content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        # Retrieve pwc from the original document
        pwc = document.get_latest_version()
        self.assertFalse(pwc.isVersionSeriesCheckedOut)

    def test_update_properties(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "beschrijving": "beschrijving 1",
            "link": "http://a.link",
            "bestandsnaam": "filename.txt",
        }
        content = io.BytesIO(b"Content before update")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            bronorganisatie="159351741",
            content=content,
        )
        self.assertEqual(
            document.creatiedatum.strftime("%Y-%m-%d"),
            datetime.date(2020, 7, 27).strftime("%Y-%m-%d"),
        )
        self.assertEqual(document.titel, "detailed summary")
        self.assertEqual(document.link, "http://a.link")
        self.assertEqual("text/plain", document.contentStreamMimeType)

        posted_content = document.get_content_stream()
        content.seek(0)
        self.assertEqual(posted_content.read(), content.read())

        # Updating the document
        new_properties = {
            "beschrijving": "beschrijving 2",
            "link": "http://an.updated.link",
        }
        new_content = io.BytesIO(b"Content after update")
        data = document.build_properties(new_properties, new=False)
        pwc = document.checkout()

        pwc.update_content(new_content, "filename.txt")
        updated_pwc = pwc.update_properties(properties=data)

        updated_document = updated_pwc.checkin("Testing properties update")
        self.assertEqual(updated_document.beschrijving, "beschrijving 2")

        self.assertEqual(updated_document.link, "http://an.updated.link")
        self.assertNotEqual(updated_document.versionLabel, document.versionLabel)
        updated_content = updated_document.get_content_stream()
        content.seek(0)
        self.assertEqual(updated_content.read(), b"Content after update")
        self.assertEqual("text/plain", updated_document.contentStreamMimeType)

    def test_update_remove_url(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "beschrijving": "beschrijving 1",
            "link": "https://drc.utrechtproeftuin.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147/download",
            "taal": "eng",
        }
        content = io.BytesIO(b"Content before update")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            bronorganisatie="159351741",
            content=content,
        )
        self.assertEqual(
            document.link,
            "https://drc.utrechtproeftuin.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147/download",
        )
        self.assertEqual(document.taal, "eng")
        posted_content = document.get_content_stream()
        content.seek(0)
        self.assertEqual(posted_content.read(), content.read())

        # Updating the document
        new_properties = {
            "beschrijving": "beschrijving 2",
            "link": "",
            "taal": "",
        }
        data = document.build_properties(new_properties, new=False)
        pwc = document.checkout()
        updated_pwc = pwc.update_properties(properties=data)

        updated_document = updated_pwc.checkin("Testing properties update")

        self.assertEqual(updated_document.beschrijving, "beschrijving 2")
        self.assertNotEqual(updated_document.versionLabel, document.versionLabel)

        if os.getenv("CMIS_BINDING") == "WEBSERVICE":
            self.assertIsNone(updated_document.taal)
            self.assertIsNone(updated_document.link)
        elif os.getenv("CMIS_BINDING") == "BROWSER":
            self.assertEqual(updated_document.taal, "")
            self.assertEqual(updated_document.link, "")

    def test_get_content_stream(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "bestandsnaam": "filename.txt",
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            bronorganisatie="159351741",
            content=content,
        )

        content_stream = document.get_content_stream()
        self.assertEqual(content_stream.read(), b"Some very important content")
        self.assertEqual("text/plain", document.contentStreamMimeType)

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "Version numbers differ between bindings",
    )
    def test_set_content_stream_webservice(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "bestandsnaam": "filename.txt",
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 1)
        self.assertEqual("text/plain", document.contentStreamMimeType)

        content = io.BytesIO(b"Different content")
        document.set_content_stream(content, "filename.txt")

        # Refresh document
        updated_document = self.cmis_client.get_document(document.uuid)
        self.assertEqual("text/plain", updated_document.contentStreamMimeType)

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 2)

        latest_version = all_versions[0]
        self.assertEqual(latest_version.versionLabel, "1.1")

        content_stream = latest_version.get_content_stream()
        self.assertEqual(content_stream.read(), b"Different content")

    @skipIf(
        os.getenv("CMIS_BINDING") != "BROWSER",
        "Version numbers differ between bindings",
    )
    def test_set_content_stream_browser(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "bestandsnaam": "filename.txt",
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            bronorganisatie="159351741",
            content=content,
        )

        # With browser binding creating a document with content creates 2 versions
        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 2)

        content = io.BytesIO(b"Different content")
        document.set_content_stream(content, "filename.txt")

        # Refresh document
        updated_document = self.cmis_client.get_document(document.uuid)
        self.assertEqual("text/plain", updated_document.contentStreamMimeType)

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 3)

        latest_version = all_versions[0]
        self.assertEqual(latest_version.versionLabel, "1.2")

        content_stream = latest_version.get_content_stream()
        self.assertEqual(content_stream.read(), b"Different content")

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "Version numbers differ between bindings",
    )
    def test_get_all_versions_webservice(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "beschrijving": "beschrijving 1",
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 1)

        # Updating the content raises the version by 0.1
        content = io.BytesIO(b"Different content")
        document.set_content_stream(content)

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 2)

        self.assertEqual(all_versions[0].versionLabel, "1.1")
        self.assertEqual(all_versions[1].versionLabel, "1.0")

        # Updating the properties raises the version by 1.0
        new_properties = {
            "beschrijving": "beschrijving 2",
        }
        data = all_versions[0].build_properties(new_properties, new=False)
        pwc = all_versions[0].checkout()
        updated_pwc = pwc.update_properties(properties=data)
        updated_pwc.checkin("Testing getting all versions update")

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 3)

        self.assertEqual(all_versions[0].versionLabel, "2.0")
        self.assertEqual(all_versions[1].versionLabel, "1.1")
        self.assertEqual(all_versions[2].versionLabel, "1.0")

    @skipIf(
        os.getenv("CMIS_BINDING") != "BROWSER",
        "Version numbers differ between bindings",
    )
    def test_get_all_versions_browser(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        # With browser binding, adding the content changes the document version
        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 2)

        # Updating the content raises the version by 0.1
        content = io.BytesIO(b"Different content")
        document.set_content_stream(content, "filename.txt")

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 3)

        self.assertEqual(all_versions[0].versionLabel, "1.2")
        self.assertEqual(all_versions[1].versionLabel, "1.1")
        self.assertEqual(all_versions[2].versionLabel, "1.0")

        # Updating the properties raises the version by 1.0
        new_properties = {
            "link": "http://an.updated.link",
        }
        data = all_versions[0].build_properties(new_properties, new=False)
        pwc = all_versions[0].checkout()
        updated_pwc = pwc.update_properties(properties=data)
        updated_pwc.checkin("Testing getting all versions update")

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 4)

        self.assertEqual(all_versions[0].versionLabel, "2.0")
        self.assertEqual(all_versions[1].versionLabel, "1.2")
        self.assertEqual(all_versions[2].versionLabel, "1.1")
        self.assertEqual(all_versions[3].versionLabel, "1.0")

    @tag("alfresco")
    def test_delete_document_with_pwc(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"some file content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        pwc = document.checkout()

        self.assertEqual(pwc.versionLabel, "pwc")

        document.delete_object()

    def test_delete_pwc(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"some file content")
        document = self.cmis_client.create_document(
            identification=identification,
            data=data,
            content=content,
            bronorganisatie="159351741",
        )

        pwc = document.checkout()

        pwc.delete_object()

        with self.assertRaises(DocumentDoesNotExistError):
            document.get_latest_version()

    def test_move_document_to_folder(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        new_folder = self.cmis_client.create_folder("Folder", other_folder.objectId)

        identification = str(uuid.uuid4())
        properties = {
            "bronorganisatie": "159351741",
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "auteur": "test_auteur",
            "formaat": "txt",
            "taal": "eng",
            "bestandsnaam": "dummy.txt",
            "beschrijving": "test_beschrijving",
            "vertrouwelijkheidaanduiding": "openbaar",
        }
        content = io.BytesIO(b"some file content")

        # Document created in temporary folder
        document = self.cmis_client.create_document(
            identification=identification,
            data=properties,
            content=content,
            bronorganisatie="159351741",
        )

        parent_folder = document.get_parent_folders()[0]

        self.assertEqual(parent_folder.name, "27")

        moved_document = document.move_object(new_folder)

        parent_folder = moved_document.get_parent_folders()[0]

        self.assertEqual(parent_folder.name, "Folder")

    def test_get_parent_folders_of_document(self):
        properties = {
            "bronorganisatie": "159351741",
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "auteur": "test_auteur",
            "formaat": "txt",
            "taal": "eng",
            "bestandsnaam": "dummy.txt",
            "beschrijving": "test_beschrijving",
            "vertrouwelijkheidaanduiding": "openbaar",
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification="d1bf9324-46c8-43ae-8bdb-d1a70d682f68",
            data=properties,
            content=content,
            bronorganisatie="159351741",
        )

        parent_folders = document.get_parent_folders()

        self.assertEqual(len(parent_folders), 1)
        # The object is created automatically in a temporary folder name after the current date
        self.assertEqual(parent_folders[0].name, "27")

    def create_document_without_extension(self):
        properties = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "bestandsnaam": "filename-without-extension",
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification="d1bf9324-46c8-43ae-8bdb-d1a70d682f68",
            data=properties,
            content=content,
            bronorganisatie="159351741",
        )

        self.assertEqual("application/octet-stream", document.contentStreamMimeType)


@freeze_time("2020-07-27 12:00:00")
class CMISContentObjectsTests(DMSMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        config = CMISConfig.get_solo()

        UrlMapping.objects.create(
            long_pattern="https://drc.utrechtproeftuin.nl",
            short_pattern="https://drc.nl",
            config=config,
        )
        UrlMapping.objects.create(
            long_pattern="https://openzaak.utrechtproeftuin.nl/besluiten",
            short_pattern="https://bes.nl",
            config=config,
        )
        UrlMapping.objects.create(
            long_pattern="https://openzaak.utrechtproeftuin.nl/zaken",
            short_pattern="https://zak.nl",
            config=config,
        )
        UrlMapping.objects.create(
            long_pattern="https://openzaak.utrechtproeftuin.nl/catalogi",
            short_pattern="https://cat.nl",
            config=config,
        )

    # TODO the same for zaak folder
    def test_get_or_create_cmis_folder(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        new_folder = self.cmis_client.create_folder("Folder", other_folder.objectId)

        child_folder = self.cmis_client.get_or_create_folder("ChildFolder", new_folder)

        self.assertEqual(child_folder.name, "ChildFolder")
        self.assertEqual(child_folder.parentId, new_folder.objectId)

        self.cmis_client.get_or_create_folder("ChildFolder", new_folder)

        new_folder_children = new_folder.get_children_folders()
        self.assertEqual(len(new_folder_children), 1)

    def test_get_or_create_zaak_folder(self):
        zaaktype = {
            "url": "https://openzaak.utrechtproeftuin.nl/catalogi/api/v1/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "identificatie": 1,
            "omschrijving": "Melding Openbare Ruimte",
            "object_type_id": f"{self.cmis_client.get_object_type_id_prefix('zaaktypefolder')}drc:zaaktypefolder",
        }
        zaak = {
            "url": "https://openzaak.utrechtproeftuin.nl/zaken/api/v1/zaken/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "zaaktype": "https://openzaak.utrechtproeftuin.nl/catalogi/api/v1/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "bronorganisatie": "509381406",
            "object_type_id": f"{self.cmis_client.get_object_type_id_prefix('zaakfolder')}drc:zaakfolder",
        }

        zaak_folder = self.cmis_client.get_or_create_zaak_folder(zaaktype, zaak)
        zaak_parent = self.cmis_client.get_folder(object_id=zaak_folder.parentId)

        self.assertEqual(len(zaak_parent.get_children_folders()), 1)

        self.cmis_client.get_or_create_folder(zaak_folder.name, zaak_parent)

        self.assertEqual(len(zaak_parent.get_children_folders()), 1)

    @patch("drc_cmis.webservice.drc_document.ObjectInformatieObject._reorganise_files")
    def test_delete_object(self, m):
        gebruiksrechten = self.cmis_client.create_content_object(
            data={}, object_type="gebruiksrechten"
        )
        oio = self.cmis_client.create_content_object(data={}, object_type="oio")

        # Doesn't raise an exception, because the documents exist
        self.cmis_client.get_content_object(gebruiksrechten.uuid, "gebruiksrechten")
        self.cmis_client.get_content_object(oio.uuid, "oio")

        gebruiksrechten.delete_object()
        oio.delete_object()

        # Raises exception because the documents have been deleted
        with self.assertRaises(DocumentDoesNotExistError):
            self.cmis_client.get_content_object(
                gebruiksrechten.objectId, "gebruiksrechten"
            )
            self.cmis_client.get_content_object(oio.objectId, "oio")

    def test_get_parent_folders_of_gebruiksrechten(self):
        gebruiksrechten = self.cmis_client.create_content_object(
            data={}, object_type="gebruiksrechten"
        )
        parent_folders = gebruiksrechten.get_parent_folders()

        self.assertEqual(len(parent_folders), 1)
        # The object is created automatically in a temporary folder name after the current date
        self.assertEqual(parent_folders[0].name, "Related data")

    def test_move_oio_to_folder(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        new_folder = self.cmis_client.create_folder("Folder", other_folder.objectId)

        oio = self.cmis_client.create_content_object(data={}, object_type="oio")

        parent_folder = oio.get_parent_folders()[0]

        self.assertEqual(parent_folder.name, "Related data")

        moved_oio = oio.move_object(new_folder)

        parent_folder = moved_oio.get_parent_folders()[0]

        self.assertEqual(parent_folder.name, "Folder")

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "Properties are built differently between bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=True)
    def test_create_properties_gebruiksrechten_webservice_mapping(self):
        from drc_cmis.webservice.drc_document import Gebruiksrechten

        current_datetime = timezone.now()

        data = {
            "informatieobject": "https://drc.utrechtproeftuin.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "startdatum": current_datetime,
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        properties = Gebruiksrechten.build_properties(data)
        self.assertEqual(
            properties["drc:gebruiksrechten__informatieobject"]["value"],
            "https://drc.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
        )
        self.assertEqual(
            properties["drc:gebruiksrechten__startdatum"]["value"],
            current_datetime.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        )
        self.assertEqual(
            properties["drc:gebruiksrechten__omschrijving_voorwaarden"]["value"],
            "Een hele set onredelijke voorwaarden",
        )
        self.assertNotIn(
            "drc:gebruiksrechten__uuid",
            properties,
        )

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "Properties are built differently between bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=False)
    def test_create_properties_gebruiksrechten_webservice(self):
        from drc_cmis.webservice.drc_document import Gebruiksrechten

        current_datetime = timezone.now()

        data = {
            "informatieobject": "https://drc.utrechtproeftuin.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "startdatum": current_datetime,
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        properties = Gebruiksrechten.build_properties(data)
        self.assertEqual(
            properties["drc:gebruiksrechten__informatieobject"]["value"],
            "https://drc.utrechtproeftuin.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
        )
        self.assertEqual(
            properties["drc:gebruiksrechten__startdatum"]["value"],
            current_datetime.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        )
        self.assertEqual(
            properties["drc:gebruiksrechten__omschrijving_voorwaarden"]["value"],
            "Een hele set onredelijke voorwaarden",
        )
        self.assertNotIn(
            "drc:gebruiksrechten__uuid",
            properties,
        )

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "Properties are built differently between bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=True)
    def test_create_properties_oio_webservice_mapping(self):
        from drc_cmis.webservice.drc_document import ObjectInformatieObject

        data = {
            "informatieobject": "https://drc.utrechtproeftuin.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "object_type": "besluit",
            "besluit": "https://openzaak.utrechtproeftuin.nl/besluiten/api/v1/besluiten/ba0a30d4-5b4d-464c-b5d3-855ad796492f",
        }

        properties = ObjectInformatieObject.build_properties(data)
        self.assertEqual(
            properties["drc:oio__informatieobject"]["value"],
            "https://drc.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
        )
        self.assertEqual(
            properties["drc:oio__object_type"]["value"],
            "besluit",
        )
        self.assertEqual(
            properties["drc:oio__besluit"]["value"],
            "https://bes.nl/api/v1/besluiten/ba0a30d4-5b4d-464c-b5d3-855ad796492f",
        )
        self.assertNotIn(
            "drc:oio__uuid",
            properties,
        )

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "Properties are built differently between bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=False)
    def test_create_properties_oio_webservice(self):
        from drc_cmis.webservice.drc_document import ObjectInformatieObject

        data = {
            "informatieobject": "https://drc.utrechtproeftuin.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "object_type": "besluit",
            "besluit": "https://openzaak.utrechtproeftuin.nl/besluiten/api/v1/besluiten/ba0a30d4-5b4d-464c-b5d3-855ad796492f",
        }

        properties = ObjectInformatieObject.build_properties(data)
        self.assertEqual(
            properties["drc:oio__informatieobject"]["value"],
            "https://drc.utrechtproeftuin.nl/api/v1/enkelvoudiginformatieobjecten/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
        )
        self.assertEqual(
            properties["drc:oio__object_type"]["value"],
            "besluit",
        )
        self.assertEqual(
            properties["drc:oio__besluit"]["value"],
            "https://openzaak.utrechtproeftuin.nl/besluiten/api/v1/besluiten/ba0a30d4-5b4d-464c-b5d3-855ad796492f",
        )
        self.assertNotIn(
            "drc:oio__uuid",
            properties,
        )

    @skipIf(
        os.getenv("CMIS_BINDING") != "BROWSER",
        "Properties are built differently between bindings",
    )
    def test_create_properties_gebruiksrechten_browser(self):
        from drc_cmis.browser.drc_document import Gebruiksrechten

        current_datetime = timezone.now()

        data = {
            "informatieobject": "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "startdatum": current_datetime,
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        properties = Gebruiksrechten.build_properties(data)
        self.assertEqual(
            properties["drc:gebruiksrechten__informatieobject"],
            "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
        )
        self.assertEqual(
            properties["drc:gebruiksrechten__startdatum"],
            current_datetime.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        )
        self.assertEqual(
            properties["drc:gebruiksrechten__omschrijving_voorwaarden"],
            "Een hele set onredelijke voorwaarden",
        )
        self.assertNotIn(
            "drc:gebruiksrechten__uuid",
            properties,
        )

    @skipIf(
        os.getenv("CMIS_BINDING") != "BROWSER",
        "Properties are built differently between bindings",
    )
    def test_create_properties_oio_browser(self):
        from drc_cmis.browser.drc_document import ObjectInformatieObject

        data = {
            "informatieobject": "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "object_type": "besluit",
            "besluit": "http://another.test.url/",
        }

        properties = ObjectInformatieObject.build_properties(data)
        self.assertEqual(
            properties["drc:oio__informatieobject"],
            "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
        )
        self.assertEqual(
            properties["drc:oio__object_type"],
            "besluit",
        )
        self.assertEqual(
            properties["drc:oio__besluit"],
            "http://another.test.url/",
        )
        self.assertNotIn(
            "drc:oio__uuid",
            properties,
        )


class CMISFolderTests(DMSMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        config = CMISConfig.get_solo()

        UrlMapping.objects.create(
            long_pattern="https://openzaak.utrechtproeftuin.nl/zaken",
            short_pattern="https://zak.nl",
            config=config,
        )
        UrlMapping.objects.create(
            long_pattern="https://openzaak.utrechtproeftuin.nl/catalogi",
            short_pattern="https://cat.nl",
            config=config,
        )

    def test_get_children_folders(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        self.cmis_client.create_folder("TestFolder1", other_folder.objectId)
        self.cmis_client.create_folder("TestFolder2", other_folder.objectId)
        self.cmis_client.create_folder("TestFolder3", other_folder.objectId)

        children = other_folder.get_children_folders()

        self.assertEqual(len(children), 3)
        expected_children = ["TestFolder1", "TestFolder2", "TestFolder3"]
        for folder in children:
            self.assertIn(folder.name, expected_children)

    def test_delete_tree(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        first_child = self.cmis_client.create_folder(
            "FirstChildFolder", other_folder.objectId
        )

        test_folder1 = self.cmis_client.create_folder(
            "TestFolder1", first_child.objectId
        )
        test_folder2 = self.cmis_client.create_folder(
            "TestFolder2", first_child.objectId
        )
        test_folder3 = self.cmis_client.create_folder(
            "TestFolder3", first_child.objectId
        )

        base_children = other_folder.get_children_folders()
        child_children = first_child.get_children_folders()

        self.assertEqual(len(base_children), 1)
        self.assertEqual(len(child_children), 3)

        first_child.delete_tree()

        base_children = other_folder.get_children_folders()
        self.assertEqual(len(base_children), 0)

        with self.assertRaises(FolderDoesNotExistError):
            self.cmis_client.get_folder(first_child.objectId)
            self.cmis_client.get_folder(test_folder1.objectId)
            self.cmis_client.get_folder(test_folder2.objectId)
            self.cmis_client.get_folder(test_folder3.objectId)

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=True)
    def test_build_zaakfolder_properties_webservice_mapping(self):
        from drc_cmis.webservice.drc_document import ZaakFolder

        properties = {
            "object_type_id": "F:drc:zaakfolder",
            "url": "https://openzaak.utrechtproeftuin.nl/zaken/api/v1/zaken/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "zaaktype": "https://openzaak.utrechtproeftuin.nl/catalogi/api/v1/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "bronorganisatie": "509381406",
        }

        built_properties = ZaakFolder.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            converted_prop_name = prop_name.split("__")[-1]
            if converted_prop_name in properties:
                if converted_prop_name == "url":
                    self.assertEqual(
                        "https://zak.nl/api/v1/zaken/random-zaak-uuid",
                        prop_dict["value"],
                    )
                elif converted_prop_name == "zaaktype":
                    self.assertEqual(
                        "https://cat.nl/api/v1/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                        prop_dict["value"],
                    )
                else:
                    self.assertEqual(
                        properties[converted_prop_name], prop_dict["value"]
                    )

        self.assertEqual(
            built_properties["cmis:objectTypeId"]["value"], "F:drc:zaakfolder"
        )
        self.assertEqual(built_properties["cmis:objectTypeId"]["type"], "propertyId")

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=False)
    def test_build_zaakfolder_properties_webservice(self):
        from drc_cmis.webservice.drc_document import ZaakFolder

        properties = {
            "object_type_id": "F:drc:zaakfolder",
            "url": "https://openzaak.utrechtproeftuin.nl/zaken/api/v1/zaken/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "zaaktype": "https://openzaak.utrechtproeftuin.nl/catalogi/api/v1/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "bronorganisatie": "509381406",
        }

        built_properties = ZaakFolder.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            converted_prop_name = prop_name.split("__")[-1]
            if converted_prop_name in properties:
                self.assertEqual(properties[converted_prop_name], prop_dict["value"])

        self.assertEqual(
            built_properties["cmis:objectTypeId"]["value"], "F:drc:zaakfolder"
        )
        self.assertEqual(built_properties["cmis:objectTypeId"]["type"], "propertyId")

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=True)
    def test_build_zaaktypefolder_properties_webservice_mapping(self):
        from drc_cmis.webservice.drc_document import ZaakTypeFolder

        properties = {
            "object_type_id": "F:drc:zaaktypefolder",
            "url": "https://openzaak.utrechtproeftuin.nl/catalogi/api/v1/zaaktypen/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "omschrijving": "Melding Openbare Ruimte",
        }

        built_properties = ZaakTypeFolder.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            converted_prop_name = prop_name.split("__")[-1]
            if converted_prop_name in properties:
                if converted_prop_name == "url":
                    self.assertEqual(
                        "https://cat.nl/api/v1/zaaktypen/random-zaak-uuid",
                        prop_dict["value"],
                    )
                else:
                    self.assertEqual(
                        properties[converted_prop_name], prop_dict["value"]
                    )

        self.assertEqual(
            built_properties["cmis:objectTypeId"]["value"], "F:drc:zaaktypefolder"
        )
        self.assertEqual(built_properties["cmis:objectTypeId"]["type"], "propertyId")

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    @override_settings(CMIS_URL_MAPPING_ENABLED=False)
    def test_build_zaaktypefolder_properties_webservice(self):
        from drc_cmis.webservice.drc_document import ZaakTypeFolder

        properties = {
            "object_type_id": "F:drc:zaaktypefolder",
            "url": "https://openzaak.utrechtproeftuin.nl/catalogi/api/v1/zaaktypen/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "omschrijving": "Melding Openbare Ruimte",
        }

        built_properties = ZaakTypeFolder.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            converted_prop_name = prop_name.split("__")[-1]
            if converted_prop_name in properties:
                self.assertEqual(properties[converted_prop_name], prop_dict["value"])

        self.assertEqual(
            built_properties["cmis:objectTypeId"]["value"], "F:drc:zaaktypefolder"
        )
        self.assertEqual(built_properties["cmis:objectTypeId"]["type"], "propertyId")
