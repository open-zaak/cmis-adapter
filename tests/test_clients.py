import io
import os
import uuid
from unittest import skipIf

from django.test import TestCase
from django.utils import timezone

import requests_mock
from freezegun import freeze_time

from drc_cmis.utils.exceptions import (
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockedException,
    DocumentNotLockedException,
    FolderDoesNotExistError,
    LockDidNotMatchException,
)

from .mixins import DMSMixin
from .utils import mock_service_oas_get


@freeze_time("2020-07-27 12:00:00")
class CMISClientFolderTests(DMSMixin, TestCase):
    def test_create_base_folder(self):

        self.assertIs(self.cmis_client._base_folder, None)

        # Since the base folder hasn't been used yet, this will create it
        base_folder = self.cmis_client.base_folder

        self.assertEqual(base_folder.baseTypeId, "cmis:folder")
        self.assertEqual(base_folder.name, self.cmis_client.base_folder_name)

    def test_create_zaaktype_folder(self):

        # Create the zaaktype folder in the base folder
        zaak_type = {
            "url": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "identificatie": 1,
            "omschrijving": "Melding Openbare Ruimte",
        }

        zaaktype_folder = self.cmis_client.get_or_create_zaaktype_folder(zaak_type)
        self.assertEqual("zaaktype-", zaaktype_folder.name[:9])
        self.assertEqual(zaaktype_folder.objectTypeId, "F:drc:zaaktypefolder")

    def test_create_zaak_folder(self):

        # Create the zaaktype folder in the base folder
        zaak_type = {
            "url": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "identificatie": 1,
            "omschrijving": "Melding Openbare Ruimte",
        }

        zaaktype_folder = self.cmis_client.get_or_create_zaaktype_folder(zaak_type)

        # Create the zaak folder in the zaaktype folder
        zaak = {
            "url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "zaaktype": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "startdatum": "2023-12-06",
            "einddatum": None,
            "registratiedatum": "2019-04-17",
            "bronorganisatie": "509381406",
        }

        zaak_folder = self.cmis_client.get_or_create_zaak_folder(
            zaak=zaak, zaaktype_folder=zaaktype_folder,
        )
        self.assertEqual("zaak-", zaak_folder.name[:5])
        self.assertEqual(zaak_folder.objectTypeId, "F:drc:zaakfolder")

    def test_get_base_folder(self):
        self.assertIs(self.cmis_client._base_folder, None)
        self.cmis_client.base_folder
        self.cmis_client._base_folder = None

        # Since the base_folder has already been created, it will be retrieved
        base_folder = self.cmis_client.base_folder

        self.assertEqual(base_folder.baseTypeId, "cmis:folder")
        self.assertEqual(base_folder.name, self.cmis_client.base_folder_name)

    @skipIf(
        os.getenv("CMIS_BINDING") == "BROWSER",
        reason="Function not implemented for browser binding",
    )
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


@freeze_time("2020-07-27 12:00:00")
class CMISClientContentObjectsTests(DMSMixin, TestCase):
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
        related_data_folder = children[0]
        self.assertEqual(related_data_folder.name, "Related data")

        oio = self.cmis_client.create_content_object(data={}, object_type="oio")

        # Check that the new oio is in the same folder
        self.assertEqual(
            oio.get_parent_folders()[0].objectId, related_data_folder.objectId
        )

    def test_create_gebruiksrechten(self):
        properties = {
            "informatieobject": "http://some.test.url/d06f86e0-1c3a-49cf-b5cd-01c079cf8147",
            "startdatum": timezone.now(),
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        gebruiksrechten = self.cmis_client.create_content_object(
            data=properties, object_type="gebruiksrechten"
        )

        self.assertEqual(
            gebruiksrechten.informatieobject, properties["informatieobject"]
        )
        self.assertEqual(
            gebruiksrechten.startdatum, properties["startdatum"],
        )
        self.assertEqual(
            gebruiksrechten.omschrijving_voorwaarden,
            properties["omschrijving_voorwaarden"],
        )

    def test_create_content_object_oio(self):
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
            "startdatum": timezone.now(),
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


@freeze_time("2020-07-27 12:00:00")
@requests_mock.Mocker(real_http=True)  # real HTTP for the Alfresco requests
class CMISClientOIOTests(DMSMixin, TestCase):
    base_besluit_url = "https://yetanothertestserver/api/v1/"
    base_zaak_url = "https://testserver/api/v1/"
    base_zaaktype_url = "https://anotherserver/ztc/api/v1/"

    zaak_url = f"{base_zaak_url}zaken/1c8e36be-338c-4c07-ac5e-1adf55bec04a"
    zaak = {
        "url": zaak_url,
        "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
        "zaaktype": f"{base_zaaktype_url}zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
        "startdatum": "2023-12-06",
        "einddatum": None,
        "registratiedatum": "2019-04-17",
        "bronorganisatie": "509381406",
    }

    besluit_url = f"{base_besluit_url}besluit/9d3dd93a-778d-4d26-8c48-db7b2a584307"
    besluit = {
        "verantwoordelijke_organisatie": "517439943",
        "identificatie": "123123",
        "besluittype": f"http://testserver/besluittype/some-random-id",
        "zaak": zaak_url,
        "datum": "2018-09-06",
        "toelichting": "Vergunning verleend.",
        "ingangsdatum": "2018-10-01",
        "vervaldatum": "2018-11-01",
    }

    zaaktype_url = f"{base_zaaktype_url}zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1"
    zaaktype = {
        "url": zaaktype_url,
        "identificatie": 1,
        "omschrijving": "Melding Openbare Ruimte",
    }

    another_zaak_url = f"{base_zaak_url}zaken/305e7c70-8a11-4321-80cc-e60498090fab"
    another_zaak = {
        "url": another_zaak_url,
        "identificatie": "1717b1f0-16e5-42d4-ba28-cbce211bb94b",
        "zaaktype": f"{base_zaaktype_url}zaaktypen/951172cc-9b59-4346-b4be-d3a4e1c3c0f1",
        "startdatum": "2023-12-06",
        "einddatum": None,
        "registratiedatum": "2019-04-17",
        "bronorganisatie": "509381406",
    }

    another_zaaktype_url = (
        f"{base_zaaktype_url}zaaktypen/951172cc-9b59-4346-b4be-d3a4e1c3c0f1"
    )
    another_zaaktype = {
        "url": another_zaaktype_url,
        "identificatie": 2,
        "omschrijving": "Melding Openbare Ruimte",
    }

    def test_create_zaak_oio_with_unlinked_document(self, m):
        # Mocking the retrieval of the Zaak
        m.get(self.zaak_url, json=self.zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the zaaktype
        m.get(self.zaaktype_url, json=self.zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Creating the document in the temporary folder
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

        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content,
        )

        # Test that the document is in the temporary folder
        children = self.cmis_client.base_folder.get_children_folders()
        year_folder = children[0]
        children = year_folder.get_children_folders()
        month_folder = children[0]
        children = month_folder.get_children_folders()
        day_folder = children[0]

        self.assertEqual(day_folder.objectId, document.get_parent_folders()[0].objectId)

        # Creating the oio must move the document to a new folder
        oio = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(oio)

        # Test the new folder structure
        children = self.cmis_client.base_folder.get_children_folders()
        self.assertEqual(len(children), 2)
        for child in children:
            if child.name != "2020":
                zaaktype_folder = child
                break

        self.assertEqual(zaaktype_folder.name, "zaaktype-Melding Openbare Ruimte-1")
        zaak_folder = zaaktype_folder.get_children_folders()[0]
        self.assertEqual(zaak_folder.name, "zaak-1bcfd0d6-c817-428c-a3f4-4047038c184d")
        children = zaak_folder.get_children_folders()
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

        self.assertEqual(day_folder.objectId, document.get_parent_folders()[0].objectId)

    def test_create_zaak_oio_with_linked_document(self, m):
        # Mocking the retrieval of the Zaaks
        m.get(self.zaak_url, json=self.zaak)
        m.get(self.another_zaak_url, json=self.another_zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the zaaktypes
        m.get(self.zaaktype_url, json=self.zaaktype)
        m.get(self.another_zaaktype_url, json=self.another_zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Create document
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
            identification="64d15843-1990-4af2-b6c8-d5a0be52402f",
            data=properties,
            content=content,
        )

        # Create an oio linked to this document
        oio1 = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(data=oio1)

        # Create a second oio to link the same document to a different zaak
        oio2 = {
            "object": self.another_zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(data=oio2)

        # Test that the second folder structure
        children = self.cmis_client.base_folder.get_children_folders()
        self.assertEqual(len(children), 3)
        children_folders_names = [folder.name for folder in children]
        self.assertIn("zaaktype-Melding Openbare Ruimte-1", children_folders_names)
        self.assertIn("zaaktype-Melding Openbare Ruimte-2", children_folders_names)
        for folder in children:
            if folder.name == "zaaktype-Melding Openbare Ruimte-2":
                zaaktype_folder = folder
                break

        zaak_folder = zaaktype_folder.get_children_folders()[0]
        self.assertEqual(zaak_folder.name, "zaak-1717b1f0-16e5-42d4-ba28-cbce211bb94b")
        children = zaak_folder.get_children_folders()
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

        self.assertNotEqual(
            day_folder.objectId, document.get_parent_folders()[0].objectId
        )

        # Check that there are 2 documents with the same identificatie
        documents = self.cmis_client.query(
            "Document",
            lhs=["drc:document__identificatie = '%s'"],
            rhs=[document.identificatie],
        )

        self.assertEqual(len(documents), 2)

        # Check that one is a copy of the other
        copied_document_was_retrieved = False
        for retrieved_document in documents:
            if retrieved_document.uuid != document.uuid:
                copied_document = retrieved_document
                copied_document_was_retrieved = True
                break

        self.assertTrue(copied_document_was_retrieved)
        self.assertEqual(copied_document.kopie_van, document.uuid)

    def test_create_besluit_oio_with_unlinked_document(self, m):
        # Mocking the retrieval of the Besluit
        m.get(self.besluit_url, json=self.besluit)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_besluit_url)

        # Mocking the retrieval of the Zaak
        m.get(self.zaak_url, json=self.zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the zaaktype
        m.get(self.zaaktype_url, json=self.zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Creating the document in the temporary folder
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

        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content,
        )

        # Test that the document is in the temporary folder
        children = self.cmis_client.base_folder.get_children_folders()
        year_folder = children[0]
        children = year_folder.get_children_folders()
        month_folder = children[0]
        children = month_folder.get_children_folders()
        day_folder = children[0]

        self.assertEqual(day_folder.objectId, document.get_parent_folders()[0].objectId)

        # Creating the oio must move the document to a new folder
        oio = {
            "object": self.besluit_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "besluit",
        }
        self.cmis_client.create_oio(oio)

        # Test the new folder structure
        children = self.cmis_client.base_folder.get_children_folders()
        self.assertEqual(len(children), 2)
        for child in children:
            if child.name != "2020":
                zaaktype_folder = child
                break

        self.assertEqual(zaaktype_folder.name, "zaaktype-Melding Openbare Ruimte-1")
        zaak_folder = zaaktype_folder.get_children_folders()[0]
        self.assertEqual(zaak_folder.name, "zaak-1bcfd0d6-c817-428c-a3f4-4047038c184d")
        children = zaak_folder.get_children_folders()
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

        self.assertEqual(day_folder.objectId, document.get_parent_folders()[0].objectId)

    def test_create_besluit_oio_with_linked_document(self, m):
        # Mocking the retrieval of the Besluit
        m.get(self.besluit_url, json=self.besluit)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_besluit_url)

        # Mocking the retrieval of the Zaaks
        m.get(self.zaak_url, json=self.zaak)
        m.get(self.another_zaak_url, json=self.another_zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the zaaktypes
        m.get(self.zaaktype_url, json=self.zaaktype)
        m.get(self.another_zaaktype_url, json=self.another_zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Create document
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
            identification="64d15843-1990-4af2-b6c8-d5a0be52402f",
            data=properties,
            content=content,
        )

        # Create an oio linked to this document
        oio1 = {
            "object": self.another_zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(data=oio1)

        # Create a besluit oio to link the same document to a different zaak
        oio2 = {
            "object": self.besluit_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "besluit",
        }
        self.cmis_client.create_oio(data=oio2)

        # Test that the second folder structure
        children = self.cmis_client.base_folder.get_children_folders()
        self.assertEqual(len(children), 3)
        children_folders_names = [folder.name for folder in children]
        self.assertIn("zaaktype-Melding Openbare Ruimte-1", children_folders_names)
        self.assertIn("zaaktype-Melding Openbare Ruimte-2", children_folders_names)
        for folder in children:
            if folder.name == "zaaktype-Melding Openbare Ruimte-1":
                zaaktype_folder = folder
                break

        zaak_folder = zaaktype_folder.get_children_folders()[0]
        self.assertEqual(zaak_folder.name, "zaak-1bcfd0d6-c817-428c-a3f4-4047038c184d")
        children = zaak_folder.get_children_folders()
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

        self.assertNotEqual(
            day_folder.objectId, document.get_parent_folders()[0].objectId
        )

        # Check that there are 2 documents with the same identificatie
        documents = self.cmis_client.query(
            "Document",
            lhs=["drc:document__identificatie = '%s'"],
            rhs=[document.identificatie],
        )

        self.assertEqual(len(documents), 2)

        # Check that one is a copy of the other
        copied_document_was_retrieved = False
        for retrieved_document in documents:
            if retrieved_document.uuid != document.uuid:
                copied_document = retrieved_document
                copied_document_was_retrieved = True
                break

        self.assertTrue(copied_document_was_retrieved)
        self.assertEqual(copied_document.kopie_van, document.uuid)


@freeze_time("2020-07-27 12:00:00")
class CMISClientDocumentTests(DMSMixin, TestCase):
    def test_create_document_with_content(self):

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

        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content,
        )

        self.assertEqual(document.identificatie, identification)
        self.assertEqual(document.bronorganisatie, "159351741")
        self.assertEqual(
            document.creatiedatum, properties["creatiedatum"],
        )
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

    def test_create_document_with_begin_registratie(self):

        identification = str(uuid.uuid4())
        properties = {
            "begin_registratie": timezone.now(),
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
        }

        document = self.cmis_client.create_document(
            identification=identification, data=properties
        )

        self.assertEqual(
            document.creatiedatum, properties["creatiedatum"],
        )

        self.assertEqual(
            document.begin_registratie, properties["begin_registratie"],
        )

    def test_create_existing_document_raises_error(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": timezone.now(),
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
            "creatiedatum": timezone.now(),
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

    def test_lock_document(self):
        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.assertIs(document.get_private_working_copy(), None)

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        pwc = document.get_private_working_copy()
        self.assertEqual(pwc.baseTypeId, "cmis:document")

    def test_already_locked_document(self):
        data = {
            "creatiedatum": timezone.now(),
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
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        pwc = document.get_private_working_copy()
        self.assertEqual(pwc.baseTypeId, "cmis:document")

        unlocked_doc = self.cmis_client.unlock_document(uuid=doc_uuid, lock=lock)

        self.assertIs(unlocked_doc.get_private_working_copy(), None)

    def test_unlock_document_with_wrong_lock(self):
        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        with self.assertRaises(LockDidNotMatchException):
            self.cmis_client.unlock_document(uuid=doc_uuid, lock=str(uuid.uuid4()))

    def test_force_unlock(self):
        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
        }
        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data
        )
        lock = str(uuid.uuid4())
        doc_uuid = document.objectId.split("/")[-1]

        self.cmis_client.lock_document(uuid=doc_uuid, lock=lock)

        pwc = document.get_private_working_copy()
        self.assertEqual(pwc.baseTypeId, "cmis:document")

        unlocked_doc = self.cmis_client.unlock_document(
            uuid=doc_uuid, lock=str(uuid.uuid4()), force=True
        )

        self.assertIs(unlocked_doc.get_private_working_copy(), None)

    def test_update_document(self):
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
        self.assertEqual(
            updated_doc.creatiedatum, properties["creatiedatum"],
        )
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

    def test_copy_document(self):
        # Create first document
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

        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content,
        )

        # Make a different folder
        destination_folder = self.cmis_client.create_folder(
            "DestinationFolder", self.cmis_client.base_folder.objectId
        )

        # Copy the document
        copied_document = self.cmis_client.copy_document(document, destination_folder)

        for property_name, property_details in copied_document.properties.items():
            # Properties such as the cmis:nodeRefId, the cmis:name, will be different
            # The copied title contains the word 'copy'
            if (
                "cmis:" in property_name
                or "titel" in property_name
                or "kopie_van" in property_name
            ):
                continue
            self.assertEqual(
                property_details["value"], document.properties[property_name]["value"]
            )

        self.assertEqual(copied_document.kopie_van, document.uuid)
