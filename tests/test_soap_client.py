import datetime
import io
import uuid

from django.test import TestCase

from freezegun import freeze_time

from drc_cmis.client.exceptions import (
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockedException,
    DocumentNotLockedException,
    FolderDoesNotExistError,
)
from drc_cmis.client.soap_client import CMISClientException
from drc_cmis.cmis.soap_drc_document import Document, Folder

from .mixins import DMSSOAPMixin


@freeze_time("2020-07-27")
class CMISSOAPClientTests(DMSSOAPMixin, TestCase):
    def test_create_base_folder(self):

        self.assertIs(self.cmis_client._base_folder, None)

        # Since the base folder hasn't been used yet, this will create it
        base_folder = self.cmis_client.base_folder

        self.assertIsInstance(base_folder, Folder)
        self.assertEqual(base_folder.name, self.cmis_client.base_folder_name)

    def test_get_base_folder(self):
        self.assertIs(self.cmis_client._base_folder, None)
        self.cmis_client.base_folder
        self.cmis_client._base_folder = None

        # Since the base_folder has already been created, it will be retrieved
        base_folder = self.cmis_client.base_folder

        self.assertIsInstance(base_folder, Folder)
        self.assertEqual(base_folder.name, self.cmis_client.base_folder_name)

    def test_get_repository_info(self):
        properties = self.cmis_client.get_repository_info()

        expected_properties = [
            "repositoryId",
            "repositoryName",
            "repositoryDescription",
            "vendorName",
            "productName",
            "productVersion",
            "rootFolderId",
            "latestChangeLogToken",
            "cmisVersionSupported",
            "changesIncomplete",
            "changesOnType",
            "principalAnonymous",
            "principalAnyone",
        ]

        for expected_property in expected_properties:
            self.assertIn(expected_property, properties)

    # TODO
    def test_query(self):
        pass

    def test_create_folder(self):
        base_folder = self.cmis_client.base_folder
        children = base_folder.get_children_folders()
        self.assertEqual(len(children), 0)

        self.cmis_client.create_folder("TestFolder", base_folder.objectId)
        children = base_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].name, "TestFolder")

    def test_existing_folder(self):
        base_folder = self.cmis_client.base_folder
        self.cmis_client.create_folder("TestFolder1", base_folder.objectId)
        second_folder = self.cmis_client.create_folder(
            "TestFolder2", base_folder.objectId
        )
        self.cmis_client.create_folder("TestFolder3", base_folder.objectId)

        retrieved_folder = self.cmis_client.get_folder(second_folder.objectId)
        self.assertEqual(retrieved_folder.name, "TestFolder2")

        with self.assertRaises(FolderDoesNotExistError):
            invented_object_id = (
                "workspace://SpacesStore/d06f86e0-1c3a-49cf-b5cd-01c079cf8147"
            )
            self.cmis_client.get_folder(invented_object_id)

    def test_get_or_create_folder_when_folder_doesnt_exist(self):
        new_folder = self.cmis_client.get_or_create_folder(
            name="TestFolder", parent=self.cmis_client.base_folder
        )
        self.assertEqual(new_folder.name, "TestFolder")

    def test_get_or_create_folder_when_folder_exist(self):
        new_folder = self.cmis_client.create_folder(
            name="TestFolder", parent_id=self.cmis_client.base_folder.objectId
        )
        self.assertEqual(new_folder.name, "TestFolder")
        new_folder_id = new_folder.objectId

        retrieved_folder = self.cmis_client.get_or_create_folder(
            name="TestFolder", parent=self.cmis_client.base_folder
        )
        self.assertEqual(retrieved_folder.name, "TestFolder")
        self.assertEqual(retrieved_folder.objectId, new_folder_id)

    def test_delete_base_tree(self):
        base_folder = self.cmis_client.base_folder
        folder1 = self.cmis_client.create_folder("TestFolder1", base_folder.objectId)
        folder2 = self.cmis_client.create_folder("TestFolder2", base_folder.objectId)
        folder3 = self.cmis_client.create_folder("TestFolder3", base_folder.objectId)

        children = base_folder.get_children_folders()
        self.assertEqual(len(children), 3)

        self.cmis_client.delete_cmis_folders_in_base()

        self.assertRaises(
            FolderDoesNotExistError, self.cmis_client.get_folder, base_folder.objectId
        )
        self.assertRaises(
            FolderDoesNotExistError, self.cmis_client.get_folder, folder1.objectId,
        )
        self.assertRaises(
            FolderDoesNotExistError, self.cmis_client.get_folder, folder2.objectId,
        )
        self.assertRaises(
            FolderDoesNotExistError, self.cmis_client.get_folder, folder3.objectId,
        )

    def test_create_wrong_content_object(self):
        with self.assertRaises(AssertionError):
            self.cmis_client.create_content_object(data={}, object_type="wrongtype")

    def test_folder_structure_when_content_object_is_created(self):

        base_folder = self.cmis_client.base_folder
        children = base_folder.get_children_folders()
        self.assertEqual(len(children), 0)

        self.cmis_client.create_content_object(data={}, object_type="gebruiksrechten")

        # Test that the folder structure is correct
        children = base_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        year_folder = children[0]
        self.assertEqual(year_folder.name, "2020")
        children = year_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        month_folder = children[0]
        self.assertEqual(month_folder.name, "7")
        children = month_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        day_folder = children[0]
        self.assertEqual(day_folder.name, "27")
        children = day_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        gebruiksrechten_folder = children[0]
        self.assertEqual(gebruiksrechten_folder.name, "Gebruiksrechten")

        self.cmis_client.create_content_object(data={}, object_type="oio")

        # Only a new Oio folder is created in the day_folder
        children = day_folder.get_children_folders()
        self.assertEqual(len(children), 2)
        oio_folder = children[1]
        self.assertEqual(oio_folder.name, "Oio")

    def test_create_gebruiksrechten(self):
        properties = {
            "informatieobject": "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "startdatum": "2020-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        gebruiksrechten = self.cmis_client.create_content_object(
            data=properties, object_type="gebruiksrechten"
        )

        self.assertEqual(
            gebruiksrechten.informatieobject, properties["informatieobject"]
        )
        self.assertEqual(
            gebruiksrechten.startdatum,
            datetime.datetime.strptime(properties["startdatum"], "%Y-%m-%dT%H:%M:%S%z"),
        )
        self.assertEqual(
            gebruiksrechten.omschrijving_voorwaarden,
            properties["omschrijving_voorwaarden"],
        )

    def test_create_oio(self):
        properties = {
            "informatieobject": "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "object_type": "besluit",
            "besluit": "http://another.test.url/",
        }

        oio = self.cmis_client.create_content_object(data=properties, object_type="oio")

        self.assertEqual(oio.informatieobject, properties["informatieobject"])
        self.assertEqual(oio.object_type, properties["object_type"])
        self.assertEqual(oio.besluit, properties["besluit"])
        self.assertIs(oio.zaak, None)

    def test_get_existing_oio(self):
        properties = {
            "informatieobject": "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "object_type": "besluit",
            "besluit": "http://another.test.url/",
        }

        oio = self.cmis_client.create_content_object(data=properties, object_type="oio")

        retrieved_oio = self.cmis_client.get_content_object(
            uuid=oio.objectId, object_type="oio"
        )

        self.assertEqual(oio.informatieobject, retrieved_oio.informatieobject)
        self.assertEqual(oio.object_type, retrieved_oio.object_type)
        self.assertEqual(oio.besluit, retrieved_oio.besluit)
        self.assertIs(oio.zaak, None)
        self.assertIs(retrieved_oio.zaak, None)

    def test_get_existing_gebruiksrechten(self):
        properties = {
            "informatieobject": "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "startdatum": "2020-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        gebruiksrechten = self.cmis_client.create_content_object(
            data=properties, object_type="gebruiksrechten"
        )

        retrieved_gebruiksrechten = self.cmis_client.get_content_object(
            uuid=gebruiksrechten.objectId, object_type="gebruiksrechten"
        )

        self.assertEqual(
            gebruiksrechten.informatieobject, retrieved_gebruiksrechten.informatieobject
        )
        self.assertEqual(
            gebruiksrechten.startdatum, retrieved_gebruiksrechten.startdatum
        )
        self.assertEqual(
            gebruiksrechten.omschrijving_voorwaarden,
            retrieved_gebruiksrechten.omschrijving_voorwaarden,
        )
        self.assertIs(gebruiksrechten.einddatum, None)
        self.assertIs(retrieved_gebruiksrechten.einddatum, None)

    def test_get_non_existing_gebruiksrechten(self):
        with self.assertRaises(DocumentDoesNotExistError):
            invented_object_id = (
                "workspace://SpacesStore/d06f86e0-1c3a-49cf-b5cd-01c079cf8147"
            )
            self.cmis_client.get_content_object(
                uuid=invented_object_id, object_type="gebruiksrechten"
            )

    def test_get_non_existing_oio(self):
        with self.assertRaises(DocumentDoesNotExistError):
            invented_object_id = (
                "workspace://SpacesStore/d06f86e0-1c3a-49cf-b5cd-01c079cf8147"
            )
            self.cmis_client.get_content_object(
                uuid=invented_object_id, object_type="oio"
            )

    def test_delete_oio(self):
        oio = self.cmis_client.create_content_object(data={}, object_type="oio")
        oio.delete_object()
        with self.assertRaises(DocumentDoesNotExistError):
            self.cmis_client.get_content_object(uuid=oio.objectId, object_type="oio")

    def test_delete_gebruiksrechten(self):
        gebruiksrechten = self.cmis_client.create_content_object(
            data={}, object_type="gebruiksrechten"
        )
        gebruiksrechten.delete_object()
        with self.assertRaises(DocumentDoesNotExistError):
            self.cmis_client.get_content_object(
                uuid=gebruiksrechten.objectId, object_type="gebruiksrechten"
            )

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

    def test_create_existing_document_raises_error(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }
        self.cmis_client.create_document(identification=identification, data=data)

        with self.assertRaises(DocumentExistsError):
            self.cmis_client.create_document(identification=identification, data=data)

    def test_create_document_creates_folder_structure(self):
        base_folder = self.cmis_client.base_folder
        children = base_folder.get_children_folders()
        self.assertEqual(len(children), 0)

        data = {
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }
        identification = str(uuid.uuid4())
        self.cmis_client.create_document(identification=identification, data=data)

        # Test that the folder structure is correct
        children = base_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        year_folder = children[0]
        self.assertEqual(year_folder.name, "2020")
        children = year_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        month_folder = children[0]
        self.assertEqual(month_folder.name, "7")
        children = month_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        day_folder = children[0]
        self.assertEqual(day_folder.name, "27")
        children = day_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        document_folder = children[0]
        self.assertEqual(document_folder.name, "Documents")

    def test_lock_document(self):
        data = {
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.assertIs(document.get_private_working_copy(), None)

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        self.assertIsInstance(document.get_private_working_copy(), Document)

    def test_already_locked_document(self):
        data = {
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        with self.assertRaises(DocumentLockedException):
            self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

    def test_unlock_document(self):
        data = {
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        self.assertIsInstance(document.get_private_working_copy(), Document)

        unlocked_doc = self.cmis_client.unlock_document(uuid=doc_uuid, lock=lock)

        self.assertIs(unlocked_doc.get_private_working_copy(), None)

    def test_unlock_document_with_wrong_lock(self):
        data = {
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        with self.assertRaises(CMISClientException):
            self.cmis_client.unlock_document(uuid=doc_uuid, lock=str(uuid.uuid4()))

    def test_force_unlock(self):
        data = {
            "creatiedatum": "2018-06-27",
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        self.assertIsInstance(document.get_private_working_copy(), Document)

        unlocked_doc = self.cmis_client.unlock_document(
            uuid=doc_uuid, lock=str(uuid.uuid4()), force=True
        )

        self.assertIs(unlocked_doc.get_private_working_copy(), None)

    def test_update_document(self):
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
        content = io.BytesIO(b"Content before update")

        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content,
        )
        doc_id = document.objectId.split("/")[-1]

        new_properties = {
            "auteur": "updated auteur",
            "link": "http://an.updated.link",
            "beschrijving": "updated beschrijving",
        }
        new_content = io.BytesIO(b"Content after update")

        lock = str(uuid.uuid4())
        self.cmis_client.lock_document(uuid=doc_id, lock=lock)
        self.cmis_client.update_document(
            uuid=doc_id, lock=lock, data=new_properties, content=new_content
        )
        updated_doc = self.cmis_client.unlock_document(uuid=doc_id, lock=lock)

        self.assertEqual(updated_doc.identificatie, identification)
        self.assertEqual(updated_doc.bronorganisatie, "159351741")
        self.assertEqual(updated_doc.creatiedatum.strftime("%Y-%m-%d"), "2018-06-27")
        self.assertEqual(updated_doc.titel, "detailed summary")
        self.assertEqual(updated_doc.auteur, "updated auteur")
        self.assertEqual(updated_doc.formaat, "txt")
        self.assertEqual(updated_doc.taal, "eng")
        self.assertEqual(updated_doc.versie, 1)
        self.assertEqual(updated_doc.bestandsnaam, "dummy.txt")
        self.assertEqual(updated_doc.link, "http://an.updated.link")
        self.assertEqual(updated_doc.beschrijving, "updated beschrijving")
        self.assertEqual(updated_doc.vertrouwelijkheidaanduiding, "openbaar")

        # Retrieving the content
        posted_content = updated_doc.get_content_stream()
        new_content.seek(0)
        self.assertEqual(posted_content.read(), new_content.read())

    def test_update_unlocked_document(self):
        identification = str(uuid.uuid4())
        properties = {
            "titel": "detailed summary",
            "auteur": "test_auteur",
        }

        document = self.cmis_client.create_document(
            identification=identification, data=properties,
        )
        doc_id = document.objectId.split("/")[-1]

        new_properties = {
            "auteur": "updated auteur",
        }

        with self.assertRaises(DocumentNotLockedException):
            self.cmis_client.update_document(
                uuid=doc_id, lock=str(uuid.uuid4()), data=new_properties
            )
