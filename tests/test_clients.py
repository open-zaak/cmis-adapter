import datetime
import io
import os
import uuid
from unittest import skip, skipIf

from django.test import TestCase, tag
from django.utils import timezone

import pytz
import requests_mock
from freezegun import freeze_time

from drc_cmis.models import CMISConfig, Vendor
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
    def test_create_other_folder_path(self):
        # Test that no 'other' folder is present
        root_folder = self.cmis_client.get_folder(self.cmis_client.root_folder_id)
        children = root_folder.get_children_folders()
        drc_folder_exists = False
        for child_folder in children:
            if child_folder.name == "TestDRC":
                drc_folder_exists = True
                break
        self.assertFalse(drc_folder_exists)

        # Create the 'other' folder
        self.cmis_client.get_or_create_other_folder()

        # Test the path created
        children = root_folder.get_children_folders()
        drc_folder_exists = False
        for child_folder in children:
            if child_folder.name == "TestDRC":
                drc_folder_exists = True
                break
        self.assertTrue(drc_folder_exists)

        children = child_folder.get_children_folders()
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

    @tag("alfresco")
    def test_create_zaaktype_folder(self):
        # Test folder where to create the zaaktype
        test_destination_folder = self.cmis_client.get_or_create_other_folder()

        # Create the zaaktype folder in the base folder
        zaaktype = {
            "url": "https://ref.tst.vng.cloud/ztc/api/v1/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "identificatie": 1,
            "omschrijving": "Melding Openbare Ruimte",
            "object_type_id": f"{self.cmis_client.get_object_type_id_prefix('zaaktypefolder')}drc:zaaktypefolder",
        }

        properties = self.cmis_client.zaaktypefolder_type.build_properties(zaaktype)

        folder_name = "zaaktype-Melding Openbare Ruimte-1"

        zaaktype_folder = self.cmis_client.get_or_create_folder(
            folder_name, test_destination_folder, properties
        )
        self.assertEqual("zaaktype-", zaaktype_folder.name[:9])
        self.assertEqual(zaaktype_folder.objectTypeId, "F:drc:zaaktypefolder")

    @tag("alfresco")
    def test_create_zaak_folder(self):
        # Test folder where to create the zaaktype and zaak folder
        test_destination_folder = self.cmis_client.get_or_create_other_folder()

        # Create the zaaktype folder in the base folder
        zaaktype = {
            "url": "https://ref.tst.vng.cloud/ztc/api/v1/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "identificatie": 1,
            "omschrijving": "Melding Openbare Ruimte",
            "object_type_id": f"{self.cmis_client.get_object_type_id_prefix('zaaktypefolder')}drc:zaaktypefolder",
        }
        properties = self.cmis_client.zaaktypefolder_type.build_properties(zaaktype)
        folder_name = "zaaktype-Melding Openbare Ruimte-1"
        zaaktype_folder = self.cmis_client.get_or_create_folder(
            folder_name, test_destination_folder, properties
        )

        # Create the zaak folder in the zaaktype folder
        zaak = {
            "url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "identificatie": "1bcfd0d6-c817-428c-a3f4-4047038c184d",
            "zaaktype": "https://ref.tst.vng.cloud/ztc/api/v1/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
            "bronorganisatie": "509381406",
            "object_type_id": f"{self.cmis_client.get_object_type_id_prefix('zaakfolder')}drc:zaakfolder",
        }
        properties = self.cmis_client.zaakfolder_type.build_properties(zaak)

        zaak_folder = self.cmis_client.get_or_create_folder(
            "zaak-1bcfd0d6-c817-428c-a3f4-4047038c184d",
            test_destination_folder,
            properties,
        )
        self.assertEqual("zaak-1bcfd0d6-c817-428c-a3f4-4047038c184d", zaak_folder.name)
        self.assertEqual(zaak_folder.objectTypeId, "F:drc:zaakfolder")

    def test_get_repository_info(self):
        properties = self.cmis_client.get_repository_info()

        some_expected_properties = [
            "repositoryId",
            "repositoryName",
            "vendorName",
            "productName",
            "productVersion",
            "rootFolderId",
            "cmisVersionSupported",
        ]

        for expected_property in some_expected_properties:
            self.assertIn(expected_property, properties)

    def test_create_folder(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        children = other_folder.get_children_folders()
        self.assertEqual(len(children), 0)

        self.cmis_client.create_folder("TestFolder", other_folder.objectId)
        children = other_folder.get_children_folders()
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].name, "TestFolder")

    def test_existing_folder(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        self.cmis_client.create_folder("TestFolder1", other_folder.objectId)
        second_folder = self.cmis_client.create_folder(
            "TestFolder2", other_folder.objectId
        )
        self.cmis_client.create_folder("TestFolder3", other_folder.objectId)

        retrieved_folder = self.cmis_client.get_folder(second_folder.objectId)
        self.assertEqual(retrieved_folder.name, "TestFolder2")

        with self.assertRaises(FolderDoesNotExistError):
            invented_object_id = (
                "workspace://SpacesStore/d06f86e0-1c3a-49cf-b5cd-01c079cf8147"
            )
            self.cmis_client.get_folder(invented_object_id)

    def test_get_or_create_folder_when_folder_doesnt_exist(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        new_folder = self.cmis_client.get_or_create_folder(
            name="TestFolder", parent=other_folder
        )
        self.assertEqual(new_folder.name, "TestFolder")

    def test_get_or_create_folder_when_folder_exist(self):
        other_folder = self.cmis_client.get_or_create_other_folder()
        new_folder = self.cmis_client.create_folder(
            name="TestFolder", parent_id=other_folder.objectId
        )
        self.assertEqual(new_folder.name, "TestFolder")
        new_folder_id = new_folder.objectId

        retrieved_folder = self.cmis_client.get_or_create_folder(
            name="TestFolder", parent=other_folder
        )
        self.assertEqual(retrieved_folder.name, "TestFolder")
        self.assertEqual(retrieved_folder.objectId, new_folder_id)

    def test_delete_other_base_folder(self):
        base_folder = self.cmis_client.get_or_create_other_folder()
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
            FolderDoesNotExistError,
            self.cmis_client.get_folder,
            folder1.objectId,
        )
        self.assertRaises(
            FolderDoesNotExistError,
            self.cmis_client.get_folder,
            folder2.objectId,
        )
        self.assertRaises(
            FolderDoesNotExistError,
            self.cmis_client.get_folder,
            folder3.objectId,
        )

    @tag("alfresco")
    def test_get_vendor(self):
        vendor = self.cmis_client.vendor
        self.assertEqual(vendor.lower(), "alfresco")


@freeze_time("2020-07-27 12:00:00")
class CMISClientContentObjectsTests(DMSMixin, TestCase):
    def test_create_wrong_content_object(self):
        with self.assertRaises(AssertionError):
            self.cmis_client.create_content_object(data={}, object_type="wrongtype")

    def test_folder_structure_when_content_object_is_created(self):

        root_folder = self.cmis_client.get_folder(self.cmis_client.root_folder_id)
        children = root_folder.get_children_folders()
        drc_folder_exists = False
        for child_folder in children:
            if child_folder.name == "TestDRC":
                drc_folder_exists = True
                break
        self.assertFalse(drc_folder_exists)

        # Creates object in the default 'other' folder
        self.cmis_client.create_content_object(data={}, object_type="gebruiksrechten")

        # Test that the folder structure is correct
        children = root_folder.get_children_folders()
        drc_folder_exists = False
        for child_folder in children:
            if child_folder.name == "TestDRC":
                drc_folder_exists = True
                break
        self.assertTrue(drc_folder_exists)
        children = child_folder.get_children_folders()
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

        self.assertIsNotNone(gebruiksrechten.uuid)

        self.assertEqual(
            gebruiksrechten.informatieobject, properties["informatieobject"]
        )
        self.assertEqual(
            gebruiksrechten.startdatum.astimezone(pytz.timezone("UTC")),
            properties["startdatum"].astimezone(pytz.timezone("UTC")),
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

        self.assertIsNotNone(oio.uuid)
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
            drc_uuid=oio.uuid, object_type="oio"
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
            drc_uuid=gebruiksrechten.uuid, object_type="gebruiksrechten"
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
            invented_uuid = "d06f86e0-1c3a-49cf-b5cd-01c079cf8147"
            self.cmis_client.get_content_object(
                drc_uuid=invented_uuid, object_type="gebruiksrechten"
            )

    def test_get_non_existing_oio(self):
        with self.assertRaises(DocumentDoesNotExistError):
            invented_uuid = "d06f86e0-1c3a-49cf-b5cd-01c079cf8147"
            self.cmis_client.get_content_object(
                drc_uuid=invented_uuid, object_type="oio"
            )

    def test_delete_content_object(self):
        oio = self.cmis_client.create_content_object(data={}, object_type="oio")
        self.cmis_client.delete_content_object(drc_uuid=oio.uuid, object_type="oio")
        with self.assertRaises(DocumentDoesNotExistError):
            self.cmis_client.get_content_object(drc_uuid=oio.uuid, object_type="oio")

    def test_delete_oio(self):
        oio = self.cmis_client.create_content_object(data={}, object_type="oio")
        oio.delete_object()
        with self.assertRaises(DocumentDoesNotExistError):
            self.cmis_client.get_content_object(drc_uuid=oio.uuid, object_type="oio")

    def test_delete_gebruiksrechten(self):
        gebruiksrechten = self.cmis_client.create_content_object(
            data={}, object_type="gebruiksrechten"
        )
        gebruiksrechten.delete_object()
        with self.assertRaises(DocumentDoesNotExistError):
            self.cmis_client.get_content_object(
                drc_uuid=gebruiksrechten.uuid, object_type="gebruiksrechten"
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
    besluit_without_zaak_url = (
        f"{base_besluit_url}besluit/43d2f02f-a539-41a6-9494-3360fa9a670d"
    )
    besluit_without_zaak = {
        "verantwoordelijke_organisatie": "517439943",
        "identificatie": "123123",
        "besluittype": f"http://testserver/besluittype/some-random-id",
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
            identification="9124c668-db3f-4198-8823-4c21fed430d0",
            data=properties,
            content=content,
        )

        # Test that the document is in the temporary folder
        other_folder = self.cmis_client.get_or_create_other_folder()

        self.assertEqual(
            other_folder.objectId, document.get_parent_folders()[0].objectId
        )

        # Creating the oio must move the document to a new folder
        oio = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(oio)

        # Test the new folder structure
        zaaktype_folders = self.cmis_client.query(
            return_type_name="zaaktypefolder",
        )
        self.assertEqual(len(zaaktype_folders), 1)
        self.assertEqual(zaaktype_folders[0].name, "zaaktype-Melding Openbare Ruimte-1")

        children = self.cmis_client.query(
            return_type_name="Folder",
            lhs=["cmis:parentId = '%s'"],
            rhs=[zaaktype_folders[0].objectId],
        )
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
        zaak_folder = day_folder.get_children_folders()[0]
        self.assertEqual(zaak_folder.name, "zaak-1bcfd0d6-c817-428c-a3f4-4047038c184d")

        self.assertEqual(
            zaak_folder.objectId, document.get_parent_folders()[0].objectId
        )

    def test_create_zaak_oio_with_linked_document(self, m):
        # Mocking the retrieval of the Zaken
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
        zaaktype_folders = self.cmis_client.query(
            return_type_name="zaaktypefolder",
        )
        self.assertEqual(len(zaaktype_folders), 2)
        children_folders_names = [folder.name for folder in zaaktype_folders]
        self.assertIn("zaaktype-Melding Openbare Ruimte-1", children_folders_names)
        self.assertIn("zaaktype-Melding Openbare Ruimte-2", children_folders_names)
        for folder in zaaktype_folders:
            if folder.name == "zaaktype-Melding Openbare Ruimte-2":
                zaaktype_folder = folder
                break

        children = self.cmis_client.query(
            return_type_name="Folder",
            lhs=["cmis:parentId = '%s'"],
            rhs=[zaaktype_folder.objectId],
        )
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
        zaak_folder = day_folder.get_children_folders()[0]
        self.assertEqual(zaak_folder.name, "zaak-1717b1f0-16e5-42d4-ba28-cbce211bb94b")

        self.assertNotEqual(
            zaak_folder.objectId, document.get_parent_folders()[0].objectId
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
            identification=identification,
            data=properties,
            content=content,
        )

        # Test that the document is in the temporary folder
        other_folder = self.cmis_client.get_or_create_other_folder()

        self.assertEqual(
            other_folder.objectId, document.get_parent_folders()[0].objectId
        )

        # Creating the oio must move the document to a new folder
        oio = {
            "object": self.besluit_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "besluit",
        }
        self.cmis_client.create_oio(oio)

        # Test the new folder structure
        zaaktype_folders = self.cmis_client.query(
            return_type_name="zaaktypefolder",
        )
        self.assertEqual(len(zaaktype_folders), 1)

        self.assertEqual(zaaktype_folders[0].name, "zaaktype-Melding Openbare Ruimte-1")
        children = self.cmis_client.query(
            return_type_name="Folder",
            lhs=["cmis:parentId = '%s'"],
            rhs=[zaaktype_folders[0].objectId],
        )
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
        zaak_folder = day_folder.get_children_folders()[0]
        self.assertEqual(zaak_folder.name, "zaak-1bcfd0d6-c817-428c-a3f4-4047038c184d")

        self.assertEqual(
            zaak_folder.objectId, document.get_parent_folders()[0].objectId
        )

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

        # Test the second folder structure
        zaaktype_folders = self.cmis_client.query(
            return_type_name="zaaktypefolder",
        )
        self.assertEqual(len(zaaktype_folders), 2)
        children_folders_names = [folder.name for folder in zaaktype_folders]
        self.assertIn("zaaktype-Melding Openbare Ruimte-1", children_folders_names)
        self.assertIn("zaaktype-Melding Openbare Ruimte-2", children_folders_names)
        for folder in zaaktype_folders:
            if folder.name == "zaaktype-Melding Openbare Ruimte-1":
                zaaktype_folder = folder
                break

        children = self.cmis_client.query(
            return_type_name="Folder",
            lhs=["cmis:parentId = '%s'"],
            rhs=[zaaktype_folder.objectId],
        )
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
        zaak_folder = day_folder.get_children_folders()[0]
        self.assertEqual(zaak_folder.name, "zaak-1bcfd0d6-c817-428c-a3f4-4047038c184d")

        self.assertNotEqual(
            zaak_folder.objectId, document.get_parent_folders()[0].objectId
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

    def test_create_oio_with_zaak_key(self, m):
        # Mocking the retrieval of the Zaak
        m.get(self.zaak_url, json=self.zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the zaaktype
        m.get(self.zaaktype_url, json=self.zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Creating the document in the temporary folder
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
            identification="9124c668-db3f-4198-8823-4c21fed430d0",
            data=properties,
            content=content,
        )

        # Creating the oio, passing the zaak url with 'zaak' key instead of 'object'
        oio = {
            "zaak": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        oio = self.cmis_client.create_oio(oio)

        self.assertEqual(oio.zaak, self.zaak_url)
        self.assertEqual(oio.object_type, "zaak")
        self.assertEqual(
            oio.informatieobject,
            f"https://testserver/api/v1/documenten/{document.uuid}",
        )

    def test_create_oio_with_besluit_key(self, m):
        # Mocking the retrieval of the Zaak
        m.get(self.zaak_url, json=self.zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the Besluit
        m.get(self.besluit_url, json=self.besluit)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_besluit_url)

        # Mocking the retrieval of the zaaktype
        m.get(self.zaaktype_url, json=self.zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Creating the document in the temporary folder
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
            identification="9124c668-db3f-4198-8823-4c21fed430d0",
            data=properties,
            content=content,
        )

        # Creating the oio, passing the besluit url with 'besluit' key instead of 'object'
        oio = {
            "besluit": self.besluit_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "besluit",
        }
        oio = self.cmis_client.create_oio(oio)

        self.assertEqual(oio.besluit, self.besluit_url)
        self.assertEqual(oio.object_type, "besluit")
        self.assertEqual(
            oio.informatieobject,
            f"https://testserver/api/v1/documenten/{document.uuid}",
        )

    def test_create_oio_with_object_key(self, m):
        # Mocking the retrieval of the Zaak
        m.get(self.zaak_url, json=self.zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the zaaktype
        m.get(self.zaaktype_url, json=self.zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Creating the document in the temporary folder
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
            identification="9124c668-db3f-4198-8823-4c21fed430d0",
            data=properties,
            content=content,
        )

        # Creating the oio, passing the zaak url with 'zaak' key instead of 'object'
        oio = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        oio = self.cmis_client.create_oio(oio)

        self.assertEqual(oio.zaak, self.zaak_url)
        self.assertEqual(oio.object_type, "zaak")
        self.assertEqual(
            oio.informatieobject,
            f"https://testserver/api/v1/documenten/{document.uuid}",
        )

    def test_create_besluit_without_zaak(self, m):
        # Mocking the retrieval of the Besluit
        m.get(self.besluit_url, json=self.besluit)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_besluit_url)
        m.get(self.besluit_without_zaak_url, json=self.besluit_without_zaak)
        mock_service_oas_get(
            m=m, service="zrc-openapi", url=self.besluit_without_zaak_url
        )

        # Creating the document in the temporary folder
        identification = str(uuid.uuid4())
        properties = {
            "bronorganisatie": "159351741",
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "beschrijving": "test_beschrijving",
            "vertrouwelijkheidaanduiding": "openbaar",
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=identification,
            data=properties,
            content=content,
        )

        # Get the temporary folder
        other_folder = self.cmis_client.get_or_create_other_folder()

        # Creating the oio must leave the document in the temporary folder
        oio = {
            "object": self.besluit_without_zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "besluit",
        }
        self.cmis_client.create_oio(oio)

        self.assertEqual(
            other_folder.objectId, document.get_parent_folders()[0].objectId
        )

    def test_link_zaak_to_document_with_existing_besluit(self, m):
        # Mocking the retrieval of the Besluit
        m.get(self.besluit_url, json=self.besluit)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_besluit_url)
        m.get(self.besluit_without_zaak_url, json=self.besluit_without_zaak)
        mock_service_oas_get(
            m=m, service="zrc-openapi", url=self.besluit_without_zaak_url
        )

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
            "beschrijving": "test_beschrijving",
            "vertrouwelijkheidaanduiding": "openbaar",
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=identification,
            data=properties,
            content=content,
        )

        # Creating the oio leaves the document in the temporary folder
        oio_besluit_data = {
            "object": self.besluit_without_zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "besluit",
        }
        oio_besluit = self.cmis_client.create_oio(oio_besluit_data)

        # Creating another oio linking to a zaak should move the besluit oio
        # and the document to the new zaaktype/zaak folder
        oio_zaak_data = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        oio_zaak = self.cmis_client.create_oio(oio_zaak_data)

        # Get new folder structure
        zaaktype_folders = self.cmis_client.query(
            return_type_name="zaaktypefolder",
        )
        self.assertEqual(len(zaaktype_folders), 1)

        self.assertEqual(zaaktype_folders[0].name, "zaaktype-Melding Openbare Ruimte-1")
        children = self.cmis_client.query(
            return_type_name="Folder",
            lhs=["cmis:parentId = '%s'"],
            rhs=[zaaktype_folders[0].objectId],
        )
        self.assertEqual(len(children), 1)
        year_folder = children[0]
        month_folder = year_folder.get_children_folders()[0]
        day_folder = month_folder.get_children_folders()[0]
        zaak_folder = day_folder.get_children_folders()[0]
        related_data_folder = zaak_folder.get_children_folders()[0]

        other_folder = self.cmis_client.get_or_create_other_folder()
        related_data_temporary_folder = other_folder.get_children_folders()[0]

        self.assertEqual(
            related_data_folder.objectId, oio_zaak.get_parent_folders()[0].objectId
        )
        self.assertEqual(
            related_data_temporary_folder.objectId,
            oio_besluit.get_parent_folders()[0].objectId,
        )
        self.assertEqual(
            other_folder.objectId, document.get_parent_folders()[0].objectId
        )

    def test_link_besluit_without_zaak_to_document_linked_to_zaak(self, m):
        # Mocking the retrieval of the Besluit
        m.get(self.besluit_url, json=self.besluit)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_besluit_url)
        m.get(self.besluit_without_zaak_url, json=self.besluit_without_zaak)
        mock_service_oas_get(
            m=m, service="zrc-openapi", url=self.besluit_without_zaak_url
        )

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
            "beschrijving": "test_beschrijving",
            "vertrouwelijkheidaanduiding": "openbaar",
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=identification,
            data=properties,
            content=content,
        )

        # Link document to zaak
        oio_zaak_data = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(oio_zaak_data)

        # Check that only one document exists
        documents = self.cmis_client.query(return_type_name="Document")
        self.assertEqual(len(documents), 1)

        # Link document to besluit, but the besluit is not linked to a zaak
        oio_besluit_data = {
            "object": self.besluit_without_zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "besluit",
        }
        oio_besluit = self.cmis_client.create_oio(oio_besluit_data)

        other_folder = self.cmis_client.get_or_create_other_folder()
        related_data_folder = other_folder.get_children_folders()[0]

        self.assertEqual(
            related_data_folder.objectId, oio_besluit.get_parent_folders()[0].objectId
        )

        # A copy of the  document has been added to the temporary folder
        documents = self.cmis_client.query(return_type_name="Document")
        self.assertEqual(len(documents), 2)
        document_titles = [doc.titel for doc in documents]
        self.assertIn("detailed summary", document_titles)
        self.assertIn("detailed summary - copy", document_titles)

        document_copy = (
            documents[0]
            if documents[0].titel == "detailed summary - copy"
            else documents[1]
        )
        self.assertEqual(
            other_folder.objectId, document_copy.get_parent_folders()[0].objectId
        )

    def test_create_document_in_zaakfolder_without_oio(self, m):
        # Mocking the retrieval of the Zaak
        m.get(self.zaak_url, json=self.zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the zaaktype
        m.get(self.zaaktype_url, json=self.zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Creating the document in the temporary folder
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
            identification="9124c668-db3f-4198-8823-4c21fed430d0",
            data=properties,
            content=content,
        )

        # Creating the oio moves the document to the zaak folder
        oio = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(oio)

        # Creating a new document in the zaak folder
        zaak_folders = self.cmis_client.query(
            return_type_name="zaakfolder",
            lhs=["drc:zaak__identificatie = '%s'"],
            rhs=[self.zaak["identificatie"]],
        )

        self.assertEqual(len(zaak_folders), 1)
        zaak_folder = zaak_folders[0]

        self.cmis_client.create_document(
            identification="58b8ebbf-0555-4989-b591-ee92550ae2f3",
            data=properties,
            content=content,
            destination_folder=zaak_folder,
        )

        related_documents = self.cmis_client.get_documents_related_to_zaak(
            identificatie=self.zaak["identificatie"]
        )
        self.assertEqual(len(related_documents), 2)

    def test_link_document_in_zaakfolder_without_oio(self, m):
        # Mocking the retrieval of the Zaken
        m.get(self.zaak_url, json=self.zaak)
        m.get(self.another_zaak_url, json=self.another_zaak)
        mock_service_oas_get(m=m, service="zrc-openapi", url=self.base_zaak_url)

        # Mocking the retrieval of the zaaktypes
        m.get(self.zaaktype_url, json=self.zaaktype)
        m.get(self.another_zaaktype_url, json=self.another_zaaktype)
        mock_service_oas_get(m=m, service="ztc-openapi", url=self.base_zaaktype_url)

        # Creating the document in the temporary folder
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
            identification="9124c668-db3f-4198-8823-4c21fed430d0",
            data=properties,
            content=content,
        )

        # Creating the oio moves the document to the zaak folder
        oio = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(oio)

        # Creating a new document in the zaak folder
        zaak_folders = self.cmis_client.query(
            return_type_name="zaakfolder",
            lhs=["drc:zaak__identificatie = '%s'"],
            rhs=[self.zaak["identificatie"]],
        )

        self.assertEqual(len(zaak_folders), 1)
        zaak_folder = zaak_folders[0]

        new_document = self.cmis_client.create_document(
            identification="58b8ebbf-0555-4989-b591-ee92550ae2f3",
            data=properties,
            content=content,
            destination_folder=zaak_folder,
        )

        # Creating an oio that relates the new document to a different zaak should copy the document and not move it
        oio = {
            "object": self.another_zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{new_document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(oio)

        # Refresh new document
        new_document = self.cmis_client.get_document(drc_uuid=new_document.uuid)
        self.assertEqual(
            new_document.get_parent_folders()[0].objectId, zaak_folder.objectId
        )


@freeze_time("2020-07-27 12:00:00")
@requests_mock.Mocker(real_http=True)  # real HTTP for the Alfresco requests
class CMISClientGebruiksrechtenTests(DMSMixin, TestCase):
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

    def test_create_gebruiksrechten_with_unlinked_document(self, m):
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
            identification=identification,
            data=properties,
            content=content,
        )

        # Create gebruiksrechten
        gebruiksrechten_data = {
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "startdatum": "2018-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        gebruiksrechten = self.cmis_client.create_gebruiksrechten(
            data=gebruiksrechten_data
        )

        # Test that the gebruiksrechten is in the temporary folder
        other_folder = self.cmis_client.get_or_create_other_folder()
        children = other_folder.get_children_folders()
        related_data_folder = children[0]

        self.assertEqual(
            related_data_folder.objectId,
            gebruiksrechten.get_parent_folders()[0].objectId,
        )

        # Test that the properties are correctly set
        self.assertEqual(
            gebruiksrechten.informatieobject,
            f"https://testserver/api/v1/documenten/{document.uuid}",
        )
        self.assertEqual(
            gebruiksrechten.startdatum,
            datetime.datetime.strptime("2018-12-24T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"),
        )
        self.assertEqual(
            gebruiksrechten.omschrijving_voorwaarden,
            "Een hele set onredelijke voorwaarden",
        )

    def test_link_document_with_existing_gebruiksrechten(self, m):
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
            identification=identification,
            data=properties,
            content=content,
        )

        # Create gebruiksrechten (also in temporary folder)
        gebruiksrechten_data = {
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "startdatum": "2018-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        gebruiksrechten = self.cmis_client.create_gebruiksrechten(
            data=gebruiksrechten_data
        )

        # Creating the oio moves the document and the gebruiksrechten to the zaak folder
        oio_data = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(oio_data)

        # Test that the gebruiksrechten is not in the temporary folder
        other_folder = self.cmis_client.get_or_create_other_folder()
        children = other_folder.get_children_folders()
        related_data_folder = children[0]

        gebruiksrechten_parent = gebruiksrechten.get_parent_folders()[0]
        self.assertNotEqual(
            related_data_folder.objectId,
            gebruiksrechten_parent.objectId,
        )

        # Check that the parent folder of the Gebruiksrechten is in the zaak folder
        document_parent = document.get_parent_folders()[0]
        document_siblings = document_parent.get_children_folders()
        is_gebruiksrechten_there = False
        for sibling in document_siblings:
            if sibling.objectId == gebruiksrechten_parent.objectId:
                is_gebruiksrechten_there = True
                break
        self.assertTrue(is_gebruiksrechten_there)

    def test_create_gebruiksrechten_with_linked_document(self, m):
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
            identification=identification,
            data=properties,
            content=content,
        )

        # Creating the oio moves the document to the zaak folder
        oio = {
            "object": self.zaak_url,
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "object_type": "zaak",
        }
        self.cmis_client.create_oio(oio)

        # Create the gebruiksrechten directly in the zaak folder
        gebruiksrechten_data = {
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "startdatum": "2018-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        gebruiksrechten = self.cmis_client.create_gebruiksrechten(
            data=gebruiksrechten_data
        )

        # Check that the parent folder of the Gebruiksrechten is in the zaak folder
        gebruiksrechten_parent = gebruiksrechten.get_parent_folders()[0]
        document_parent = document.get_parent_folders()[0]
        document_siblings = document_parent.get_children_folders()
        is_gebruiksrechten_there = False
        for sibling in document_siblings:
            if sibling.objectId == gebruiksrechten_parent.objectId:
                is_gebruiksrechten_there = True
                break
        self.assertTrue(is_gebruiksrechten_there)

    def test_make_second_link_to_doc_with_existing_gebruiksrechten(self, m):
        # Mocking the retrieval of the Zaken
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

        # Create the gebruiksrechten
        gebruiksrechten_data = {
            "informatieobject": f"https://testserver/api/v1/documenten/{document.uuid}",
            "startdatum": "2018-12-24T00:00:00Z",
            "omschrijving_voorwaarden": "Een hele set onredelijke voorwaarden",
        }

        gebruiksrechten = self.cmis_client.create_gebruiksrechten(
            data=gebruiksrechten_data
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

        # Check that there are now 2 gebruiksrechten
        gebruiksrechten_copies = self.cmis_client.query(
            return_type_name="gebruiksrechten",
            lhs=["drc:gebruiksrechten__informatieobject = '%s'"],
            rhs=[gebruiksrechten.informatieobject],
        )

        self.assertEqual(len(gebruiksrechten_copies), 2)


@freeze_time("2020-07-27 12:00:00")
class CMISClientDocumentTests(DMSMixin, TestCase):
    def test_create_document_with_content(self):

        identification = str(uuid.uuid4())
        properties = {
            "uuid": str(uuid.uuid4()),
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
            identification=identification,
            data=properties,
            content=content,
        )

        self.assertIsNotNone(document.uuid)
        self.assertEqual(document.identificatie, identification)
        self.assertEqual(document.bronorganisatie, "159351741")
        self.assertEqual(
            document.creatiedatum,
            properties["creatiedatum"],
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

    def test_create_document_with_dates_and_datetimes(self):

        identification = str(uuid.uuid4())
        properties = {
            "begin_registratie": timezone.now(),
            "creatiedatum": timezone.now().date(),
            "integriteit_datum": timezone.now().date(),
            "ondertekening_datum": timezone.now().date(),
            "verzenddatum": timezone.now().date(),
            "ontvangstdatum": timezone.now().date(),
            "titel": "detailed summary",
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content
        )

        self.assertIsNotNone(document.uuid)

        # In OpenZaak, date fields that come back as datetimes through CMIS are converted with .date() to dates
        for key, value in properties.items():
            if isinstance(value, datetime.date) and not isinstance(
                value, datetime.datetime
            ):
                with self.subTest(key):
                    self.assertEqual(
                        getattr(document, key).date(),
                        timezone.now().date(),
                    )

        with self.subTest("begin_registratie"):
            self.assertEqual(
                document.begin_registratie.astimezone(pytz.timezone("UTC")),
                properties["begin_registratie"].astimezone(pytz.timezone("UTC")),
            )

    def test_create_existing_document_raises_error(self):
        identification = str(uuid.uuid4())
        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        self.cmis_client.create_document(
            identification=identification, data=data, content=content
        )

        with self.assertRaises(DocumentExistsError):
            self.cmis_client.create_document(identification=identification, data=data)

    def test_create_document_creates_folder_structure(self):
        root_folder = self.cmis_client.get_folder(self.cmis_client.root_folder_id)
        children = root_folder.get_children_folders()
        drc_folder_exists = False
        for child_folder in children:
            if child_folder.name == "TestDRC":
                drc_folder_exists = True
                break
        self.assertFalse(drc_folder_exists)

        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "uuid": str(uuid.uuid4()),
        }
        identification = str(uuid.uuid4())
        content = io.BytesIO(b"some file content")

        self.cmis_client.create_document(
            identification=identification, data=data, content=content
        )

        # Test that the folder structure is correct
        root_folder = self.cmis_client.get_folder(self.cmis_client.root_folder_id)
        children = root_folder.get_children_folders()
        drc_folder_exists = False
        for child_folder in children:
            if child_folder.name == "TestDRC":
                other_base_folder = child_folder
                drc_folder_exists = True
                break
        self.assertTrue(drc_folder_exists)
        children = other_base_folder.get_children_folders()
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
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data, content=content
        )
        lock = str(uuid.uuid4())

        self.assertFalse(document.isVersionSeriesCheckedOut)

        self.cmis_client.lock_document(drc_uuid=document.uuid, lock=lock)

        pwc = document.get_latest_version()
        self.assertTrue(pwc.isVersionSeriesCheckedOut)

    def test_already_locked_document(self):
        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data, content=content
        )
        lock = str(uuid.uuid4())

        self.cmis_client.lock_document(drc_uuid=document.uuid, lock=lock)

        with self.assertRaises(DocumentLockedException):
            self.cmis_client.lock_document(drc_uuid=document.uuid, lock=lock)

    def test_unlock_document(self):
        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data, content=content
        )
        lock = str(uuid.uuid4())

        self.cmis_client.lock_document(drc_uuid=document.uuid, lock=lock)

        pwc = document.get_latest_version()
        self.assertTrue(pwc.isVersionSeriesCheckedOut)

        unlocked_doc = self.cmis_client.unlock_document(
            drc_uuid=document.uuid, lock=lock
        )

        self.assertFalse(unlocked_doc.isVersionSeriesCheckedOut)

    def test_unlock_document_with_wrong_lock(self):
        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data, content=content
        )
        lock = str(uuid.uuid4())

        self.cmis_client.lock_document(drc_uuid=document.uuid, lock=lock)

        with self.assertRaises(LockDidNotMatchException):
            self.cmis_client.unlock_document(
                drc_uuid=document.uuid, lock=str(uuid.uuid4())
            )

    def test_force_unlock(self):
        data = {
            "creatiedatum": timezone.now(),
            "titel": "detailed summary",
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data, content=content
        )
        lock = str(uuid.uuid4())

        self.cmis_client.lock_document(drc_uuid=document.uuid, lock=lock)

        pwc = document.get_latest_version()
        self.assertTrue(pwc.isVersionSeriesCheckedOut)

        unlocked_doc = self.cmis_client.unlock_document(
            drc_uuid=document.uuid, lock=str(uuid.uuid4()), force=True
        )

        self.assertFalse(unlocked_doc.isVersionSeriesCheckedOut)

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
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"Content before update")

        document = self.cmis_client.create_document(
            identification=identification,
            data=properties,
            content=content,
        )

        new_properties = {
            "auteur": "updated auteur",
            "link": "http://an.updated.link",
            "beschrijving": "updated beschrijving",
        }
        new_content = io.BytesIO(b"Content after update")

        lock = str(uuid.uuid4())
        self.cmis_client.lock_document(drc_uuid=document.uuid, lock=lock)
        self.cmis_client.update_document(
            drc_uuid=document.uuid, lock=lock, data=new_properties, content=new_content
        )
        updated_doc = self.cmis_client.unlock_document(
            drc_uuid=document.uuid, lock=lock
        )

        self.assertEqual(updated_doc.identificatie, identification)
        self.assertEqual(updated_doc.bronorganisatie, "159351741")
        self.assertEqual(
            updated_doc.creatiedatum,
            properties["creatiedatum"],
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
        self.assertEqual(updated_doc.uuid, document.uuid)

        # Retrieving the content
        posted_content = updated_doc.get_content_stream()
        new_content.seek(0)
        self.assertEqual(posted_content.read(), new_content.read())

    def test_update_unlocked_document(self):
        identification = str(uuid.uuid4())
        properties = {
            "titel": "detailed summary",
            "auteur": "test_auteur",
            "uuid": str(uuid.uuid4()),
        }

        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=identification, data=properties, content=content
        )

        new_properties = {
            "auteur": "updated auteur",
        }

        with self.assertRaises(DocumentNotLockedException):
            self.cmis_client.update_document(
                drc_uuid=document.uuid, lock=str(uuid.uuid4()), data=new_properties
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
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=identification,
            data=properties,
            content=content,
        )

        # Make a different folder
        other_base_folder = self.cmis_client.get_or_create_other_folder()
        destination_folder = self.cmis_client.create_folder(
            "DestinationFolder", other_base_folder.objectId
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
                or "uuid" in property_name
            ):
                continue

            if isinstance(property_details["value"], datetime.datetime):
                self.assertEqual(
                    property_details["value"].astimezone(pytz.timezone("UTC")),
                    document.properties[property_name]["value"].astimezone(
                        pytz.timezone("UTC")
                    ),
                )
            else:
                self.assertEqual(
                    property_details["value"],
                    document.properties[property_name]["value"],
                )

        self.assertEqual(copied_document.kopie_van, document.uuid)
        self.assertNotEqual(copied_document.uuid, document.uuid)

    def test_delete_document(self):
        data = {
            "creatiedatum": datetime.date(2020, 7, 27),
            "titel": "detailed summary",
            "uuid": str(uuid.uuid4()),
        }
        content = io.BytesIO(b"some file content")

        document = self.cmis_client.create_document(
            identification=str(uuid.uuid4()), data=data, content=content
        )
        self.cmis_client.delete_document(drc_uuid=document.uuid)
        with self.assertRaises(DocumentDoesNotExistError):
            self.cmis_client.get_document(drc_uuid=document.uuid)
