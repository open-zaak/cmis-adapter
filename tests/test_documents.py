import datetime
import io
import os
import uuid
from unittest import skipIf

from django.test import TestCase
from django.utils import timezone

from freezegun import freeze_time

from drc_cmis.utils.exceptions import DocumentDoesNotExistError, FolderDoesNotExistError

from .mixins import DMSMixin


@freeze_time("2020-07-27 12:00:00")
class CMISDocumentTests(DMSMixin, TestCase):
    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    def test_build_properties_webservice(self):
        properties = {
            "integriteitwaarde": "Something",
            "verwijderd": "false",
            "ontvangstdatum": "2020-07-28",
            "versie": "1.0",
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }

        types = {
            "integriteitwaarde": "propertyString",
            "verwijderd": "propertyBoolean",
            "ontvangstdatum": "propertyDateTime",
            "versie": "propertyDecimal",
            "creatiedatum": "propertyDateTime",
            "titel": "propertyString",
        }
        identification = str(uuid.uuid4())
        document = self.cmis_client.create_document(
            identification=identification, data=properties
        )

        built_properties = document.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            if prop_name.split("__")[-1] in properties:
                converted_prop_name = prop_name.split("__")[-1]
                self.assertEqual(types[converted_prop_name], prop_dict["type"])
                self.assertEqual(properties[converted_prop_name], prop_dict["value"])

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
            identification=identification, data=properties
        )

        built_properties = document.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)

        for prop_name, prop_value in built_properties.items():

            if prop_name.split("__")[-1] in properties:
                converted_prop_name = prop_name.split("__")[-1]
                self.assertEqual(properties[converted_prop_name], prop_value)

    def test_checkout_document(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=identification, data=data
        )

        pwc = document.checkout()

        self.assertEqual(pwc.versionLabel, "pwc")

    def test_checkin_document(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=identification, data=data
        )

        pwc = document.checkout()
        self.assertEqual(pwc.versionLabel, "pwc")

        new_doc = pwc.checkin(checkin_comment="Testing Check-in...")
        self.assertEqual(new_doc.versionLabel, "2.0")

    def test_get_pwc(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=identification, data=data
        )
        document.checkout()

        # Retrieve pwc from the original document
        pwc = document.get_private_working_copy()
        self.assertIsNotNone(pwc.versionLabel)

    def test_get_pwc_with_no_checked_out_doc(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=identification, data=data
        )

        # Retrieve pwc from the original document
        pwc = document.get_private_working_copy()
        self.assertIsNone(pwc)

    def test_update_properties(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "link": "http://a.link",
        }
        content = io.BytesIO(b"Content before update")
        document = self.cmis_client.create_document(
            identification=identification, data=data, content=content
        )
        self.assertEqual(
            document.creatiedatum.strftime("%Y-%m-%d"),
            datetime.date(2020, 7, 27).strftime("%Y-%m-%d"),
        )
        self.assertEqual(document.titel, "detailed summary")
        self.assertEqual(document.link, "http://a.link")
        posted_content = document.get_content_stream()
        content.seek(0)
        self.assertEqual(posted_content.read(), content.read())

        # Updating the document
        new_properties = {
            "link": "http://an.updated.link",
        }
        new_content = io.BytesIO(b"Content after update")
        data = document.build_properties(new_properties, new=False)
        pwc = document.checkout()
        updated_pwc = pwc.update_properties(properties=data, content=new_content)
        updated_document = updated_pwc.checkin("Testing properties update")
        self.assertEqual(updated_document.link, "http://an.updated.link")
        self.assertNotEqual(updated_document.versionLabel, document.versionLabel)
        updated_content = updated_document.get_content_stream()
        content.seek(0)
        self.assertEqual(updated_content.read(), b"Content after update")

    def test_get_content_stream(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification, data=data, content=content
        )

        content_stream = document.get_content_stream()
        self.assertEqual(content_stream.read(), b"Some very important content")

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "Version numbers differ between bindings",
    )
    def test_set_content_stream_webservice(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification, data=data, content=content
        )

        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 1)

        content = io.BytesIO(b"Different content")
        document.set_content_stream(content)

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
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification, data=data, content=content
        )

        # With browser binding creating a document with content creates 2 versions
        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 2)

        content = io.BytesIO(b"Different content")
        document.set_content_stream(content)

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
        }
        content = io.BytesIO(b"Some very important content")
        document = self.cmis_client.create_document(
            identification=identification, data=data, content=content
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
            "link": "http://an.updated.link",
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
            identification=identification, data=data, content=content
        )

        # With browser binding, adding the content changes the document version
        all_versions = document.get_all_versions()
        self.assertEqual(len(all_versions), 2)

        # Updating the content raises the version by 0.1
        content = io.BytesIO(b"Different content")
        document.set_content_stream(content)

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

    def test_delete_document_with_pwc(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=identification, data=data
        )

        pwc = document.checkout()

        self.assertEqual(pwc.versionLabel, "pwc")

        document.delete_object()

    def test_move_document_to_folder(self):
        base_folder = self.cmis_client.base_folder
        new_folder = self.cmis_client.create_folder("Folder", base_folder.objectId)

        identification = str(uuid.uuid4())
        properties = {
            "bronorganisatie": "159351741",
            "creatiedatum": timezone.now(),
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

        # Document created in temporary folder
        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content,
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
            "link": "http://een.link",
            "beschrijving": "test_beschrijving",
            "vertrouwelijkheidaanduiding": "openbaar",
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification="d1bf9324-46c8-43ae-8bdb-d1a70d682f68",
            data=properties,
            content=content,
        )

        parent_folders = document.get_parent_folders()

        self.assertEqual(len(parent_folders), 1)
        # The object is created automatically in a temporary folder name after the current date
        self.assertEqual(parent_folders[0].name, "27")


@freeze_time("2020-07-27 12:00:00")
class CMISContentObjectsTests(DMSMixin, TestCase):
    def test_delete_object(self):
        gebruiksrechten = self.cmis_client.create_content_object(
            data={}, object_type="gebruiksrechten"
        )
        oio = self.cmis_client.create_content_object(data={}, object_type="oio")

        # Doesn't raise an exception, because the documents exist
        self.cmis_client.get_content_object(gebruiksrechten.objectId, "gebruiksrechten")
        self.cmis_client.get_content_object(oio.objectId, "oio")

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
        base_folder = self.cmis_client.base_folder
        new_folder = self.cmis_client.create_folder("Folder", base_folder.objectId)

        oio = self.cmis_client.create_content_object(data={}, object_type="oio")

        parent_folder = oio.get_parent_folders()[0]

        self.assertEqual(parent_folder.name, "Related data")

        moved_oio = oio.move_object(new_folder)

        parent_folder = moved_oio.get_parent_folders()[0]

        self.assertEqual(parent_folder.name, "Folder")


class CMISFolderTests(DMSMixin, TestCase):
    def test_get_children_folders(self):
        base_folder = self.cmis_client.base_folder
        self.cmis_client.create_folder("TestFolder1", base_folder.objectId)
        self.cmis_client.create_folder("TestFolder2", base_folder.objectId)
        self.cmis_client.create_folder("TestFolder3", base_folder.objectId)

        children = base_folder.get_children_folders()

        self.assertEqual(len(children), 3)
        expected_children = ["TestFolder1", "TestFolder2", "TestFolder3"]
        for folder in children:
            self.assertIn(folder.name, expected_children)

    def test_delete_tree(self):
        base_folder = self.cmis_client.base_folder
        first_child = self.cmis_client.create_folder(
            "FirstChildFolder", base_folder.objectId
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

        base_children = base_folder.get_children_folders()
        child_children = first_child.get_children_folders()

        self.assertEqual(len(base_children), 1)
        self.assertEqual(len(child_children), 3)

        first_child.delete_tree()

        base_children = base_folder.get_children_folders()
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
    def test_build_zaakfolder_properties_webservice(self):

        from drc_cmis.webservice.drc_document import ZaakFolder

        properties = {
            "object_type_id": "F:drc:zaakfolder",
            "url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "zaaktype": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "bronorganisatie": "509381406",
        }

        built_properties = ZaakFolder.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            if prop_name.split("__")[-1] in properties:
                converted_prop_name = prop_name.split("__")[-1]
                self.assertEqual(properties[converted_prop_name], prop_dict["value"])

        self.assertEqual(
            built_properties["cmis:objectTypeId"]["value"], "F:drc:zaakfolder"
        )
        self.assertEqual(built_properties["cmis:objectTypeId"]["type"], "propertyId")

    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "The properties are built differently with different bindings",
    )
    def test_build_zaaktypefolder_properties_webservice(self):

        from drc_cmis.webservice.drc_document import ZaakTypeFolder

        properties = {
            "object_type_id": "F:drc:zaaktypefolder",
            "url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "omschrijving": "Melding Openbare Ruimte",
        }

        built_properties = ZaakTypeFolder.build_properties(data=properties)

        self.assertIn("cmis:objectTypeId", built_properties)

        for prop_name, prop_dict in built_properties.items():
            self.assertIn("type", prop_dict)
            self.assertIn("value", prop_dict)

            if prop_name.split("__")[-1] in properties:
                converted_prop_name = prop_name.split("__")[-1]
                self.assertEqual(properties[converted_prop_name], prop_dict["value"])

        self.assertEqual(
            built_properties["cmis:objectTypeId"]["value"], "F:drc:zaaktypefolder"
        )
        self.assertEqual(built_properties["cmis:objectTypeId"]["type"], "propertyId")
