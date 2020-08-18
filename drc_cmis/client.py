from typing import List, TypeVar, Union
from uuid import UUID

from django.utils import timezone

from drc_cmis.utils.exceptions import DocumentDoesNotExistError

from .models import Vendor

# The Document/Folder/Oio/Gebruiksrechten classes used in practice depend on the client
# (different classes exist for the webservice and browser binding)
Document = TypeVar("Document")
Gebruiksrechten = TypeVar("Gebruiksrechten")
Folder = TypeVar("Folder")
ObjectInformatieObject = TypeVar("ObjectInformatieObject")


class CMISClient:

    _main_repo_id = None
    _root_folder_id = None
    _base_folder = None

    document_type = None
    gebruiksrechten_type = None
    oio_type = None
    folder_type = None
    zaakfolder_type = None
    zaaktypefolder_type = None

    def get_return_type(self, type_name: str) -> type:
        error_message = f"No class {type_name} exists for this client."
        type_name = type_name.lower()
        assert type_name in [
            "zaaktypefolder",
            "zaakfolder",
            "folder",
            "document",
            "gebruiksrechten",
            "oio",
        ], error_message

        if type_name == "folder":
            return self.folder_type
        elif type_name == "document":
            return self.document_type
        elif type_name == "gebruiksrechten":
            return self.gebruiksrechten_type
        elif type_name == "oio":
            return self.oio_type
        elif type_name == "zaaktypefolder":
            return self.zaaktypefolder_type
        elif type_name == "zaakfolder":
            return self.zaakfolder_type

    def get_object_type_id_prefix(self, object_type: str) -> str:
        """Get the prefix for the cmis:objectTypeId.

        Alfresco requires prefixes for create statements of custom objects.
        https://stackoverflow.com/a/28322276/7146757

        :param object_type: str, the type of the object
        :return: str, the prefix (F: or D:)
        """
        if self.vendor.lower() == Vendor.alfresco:
            if object_type in ["zaaktypefolder", "zaakfolder"]:
                return "F:"
            if object_type in ["document", "oio", "gebruiksrechten"]:
                return "D:"

        return ""

    def get_all_versions(self, document: Document) -> List[Document]:
        """Get all versions of a document from the CMS"""
        return document.get_all_versions()

    def get_or_create_folder(
        self, name: str, parent: Folder, properties: dict = None
    ) -> Folder:
        """Get or create a folder 'name/' in the parent folder

        :param name: string, the name of the folder to create
        :param parent: Folder, the parent folder
        :param properties: dict, contains the properties of the folder to create
        :return: Folder, the folder that was created/retrieved
        """

        children_folders = parent.get_children_folders()
        for folder in children_folders:
            if folder.name == name:
                return folder

        # Create new folder, as it doesn't exist yet
        return self.create_folder(name, parent.objectId, properties)

    def delete_cmis_folders_in_base(self):
        """Deletes all the folders in the base folder

        There are 2 cases:
        1. The base folder is the root folder: only the zaaktype and temporary folders should be deleted
        2. The base folder is a child of the root folder: the base folder is deleted.
        """
        # Case 2
        if self.base_folder_name != "":
            self.base_folder.delete_tree()
            self._base_folder = None
        # Case 1
        else:
            # TODO
            pass

    def create_oio(self, data: dict) -> ObjectInformatieObject:
        """Create ObjectInformatieObject which relates a document with a zaak or besluit

        There are a few possible cases.
        1. The oio creates a link to a Besluit:
            A. The besluit is linked to a zaak:
                - If the document is NOT already linked to a zaak, it is moved from the temporary folder to
                    the zaak folder
                - If the document is already linked to a zaak, it will be copied to the new zaak folder
            B. The besluit is not linked to a zaak:
                - If the document is NOT already linked to a zaak, the oio is created in the temporary folder and the
                    document is NOT moved
                - If the document is already linked to a zaak, the document is not moved and the oio will go
                    in the temporary folder
        2. The oio creates a link to a Zaak:
            A. If the document is already related to a zaak, a copy of the document is put in the
                correct zaaktype/zaak folder.
            B. If the document is NOT related to a zaak: the document is moved from the temporary folder
            to the correct zaaktype/zaak folder.

        If the document is linked already to a gebruiksrechten, then the gebruiksrechten object is also moved.

        :param data: dict, the oio details.
        :return: Oio created
        """
        from drc_cmis.client_builder import get_zds_client

        # Get the document
        document_uuid = data.get("informatieobject").split("/")[-1]
        document = self.get_document(drc_uuid=document_uuid)

        if "object" in data:
            data[data["object_type"]] = data.pop("object")

        # Retrieve the zaak and the zaaktype
        if data["object_type"] == "besluit":
            client_besluit = get_zds_client(data["besluit"])
            besluit_data = client_besluit.retrieve("besluit", url=data["besluit"])
            zaak_url = besluit_data.get("zaak")
            if zaak_url is None:
                # The besluit is created in the temporary folder, since it is not related to a zaak
                now = timezone.now()
                year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
                month_folder = self.get_or_create_folder(str(now.month), year_folder)
                day_folder = self.get_or_create_folder(str(now.day), month_folder)
                related_data_folder = self.get_or_create_folder(
                    "Related data", day_folder
                )
                return self.create_content_object(
                    data=data, object_type="oio", destination_folder=related_data_folder
                )
        else:
            zaak_url = data["zaak"]
        client_zaak = get_zds_client(zaak_url)
        zaak_data = client_zaak.retrieve("zaak", url=zaak_url)
        client_zaaktype = get_zds_client(zaak_data["zaaktype"])
        zaaktype_data = client_zaaktype.retrieve("zaaktype", url=zaak_data["zaaktype"])

        # Get or create the destination folder
        zaaktype_folder = self.get_or_create_zaaktype_folder(zaaktype_data)
        zaak_folder = self.get_or_create_zaak_folder(zaak_data, zaaktype_folder)

        now = timezone.now()
        year_folder = self.get_or_create_folder(str(now.year), zaak_folder)
        month_folder = self.get_or_create_folder(str(now.month), year_folder)
        day_folder = self.get_or_create_folder(str(now.day), month_folder)
        related_data_folder = self.get_or_create_folder("Related data", day_folder)

        # Check if there are other Oios related to the document
        retrieved_oios = self.query(
            return_type_name="oio",
            lhs=["drc:oio__informatieobject = '%s'"],
            rhs=[data.get("informatieobject")],
        )

        # Check if there are gebruiksrechten related to the document
        related_gebruiksrechten = self.query(
            return_type_name="gebruiksrechten",
            lhs=["drc:gebruiksrechten__informatieobject = '%s'"],
            rhs=[data.get("informatieobject")],
        )

        # Case 1: Already related to a zaak. Copy the document to the destination folder.
        if len(retrieved_oios) > 0:
            self.copy_document(document, day_folder)
            if len(related_gebruiksrechten) > 0:
                for gebruiksrechten in related_gebruiksrechten:
                    self.copy_gebruiksrechten(gebruiksrechten, related_data_folder)
        # Case 2: Not related to a zaak. Move the document to the destination folder
        else:
            document.move_object(day_folder)
            if len(related_gebruiksrechten) > 0:
                for gebruiksrechten in related_gebruiksrechten:
                    gebruiksrechten.move_object(related_data_folder)

        # Create the Oio in a separate folder
        return self.create_content_object(
            data=data, object_type="oio", destination_folder=related_data_folder
        )

    def create_gebruiksrechten(self, data: dict) -> Gebruiksrechten:
        """Create gebruiksrechten

        The geburiksrechten is created in the 'Related data' folder in the folder
        of the related document

        :param data: dict, data of the gebruiksrechten
        :return: Gebruiksrechten
        """

        document_uuid = data.get("informatieobject").split("/")[-1]
        document = self.get_document(drc_uuid=document_uuid)

        parent_folder = document.get_parent_folders()[0]
        related_data_folder = self.get_or_create_folder("Related data", parent_folder)

        return self.create_content_object(
            data=data,
            object_type="gebruiksrechten",
            destination_folder=related_data_folder,
        )

    def delete_content_object(self, drc_uuid: Union[str, UUID], object_type: str):
        """Delete the gebruiksrechten/objectinformatieobject with specified uuid

        :param drc_uuid: string or UUID, the value of drc:oio__uuid/drc:gebruiksrechten__uuid
        number gives the cmis:objectId
        :param object_type: string, either "gebruiksrechten" or "oio"
        :return: Either a Gebruiksrechten or ObjectInformatieObject
        """

        content_object = self.get_content_object(drc_uuid, object_type=object_type)
        content_object.delete_object()

    def delete_document(self, drc_uuid: str) -> None:
        """Delete all versions of a document with given uuid

        :param drc_uuid: string, the value of drc:oio__uuid/drc:gebruiksrechten__uuid
        """
        document = self.get_document(drc_uuid=drc_uuid)
        document.delete_object()

    def get_or_create_zaaktype_folder(self, zaaktype: dict) -> Folder:
        """Get or create the zaaktype folder in the base folder

        The folder has prefix 'zaaktype-'

        :param zaaktype: dict, contains the properties of the zaaktype
        :return: Folder
        """

        zaaktype.setdefault(
            "object_type_id",
            f"{self.get_object_type_id_prefix('zaaktypefolder')}drc:zaaktypefolder",
        )

        properties = self.zaaktypefolder_type.build_properties(zaaktype)

        folder_name = (
            f"zaaktype-{zaaktype.get('omschrijving')}-{zaaktype.get('identificatie')}"
        )
        return self.get_or_create_folder(folder_name, self.base_folder, properties)

    def get_or_create_zaak_folder(self, zaak: dict, zaaktype_folder: Folder) -> Folder:
        """
        Create a folder with the prefix 'zaak-' to make a zaak folder
        """
        zaak.setdefault(
            "object_type_id",
            f"{self.get_object_type_id_prefix('zaakfolder')}drc:zaakfolder",
        )
        properties = self.zaakfolder_type.build_properties(zaak)

        return self.get_or_create_folder(
            f"zaak-{zaak['identificatie']}", zaaktype_folder, properties
        )

    def get_latest_version_not_pwc(self, extracted_data: List) -> Document:
        """Return the latest version which is not the pwc

        :param extracted_data: dict, the results of a query
        "SELECT * FROM drc:document WHERE drc:document__uuid = '<uuid>'"
        :return: Document, the latest not locked version of a document
        """
        error_string = "Document bestaat niet in het CMIS connection"
        does_not_exist = DocumentDoesNotExistError(error_string)

        if len(extracted_data) == 0:
            raise does_not_exist
        elif len(extracted_data) == 1:
            return self.document_type(extracted_data[0])
        elif len(extracted_data) == 2:
            # In this case there is both the latest version and pwc
            # return the latest version
            for doc_data in extracted_data:
                if doc_data["properties"]["cmis:versionLabel"]["value"] != "pwc":
                    return self.document_type(doc_data)
