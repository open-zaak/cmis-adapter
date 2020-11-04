from io import BytesIO
from typing import List, Optional, TypeVar, Union
from uuid import UUID

from django.utils import timezone
from django.utils.crypto import constant_time_compare

from cmislib.exceptions import UpdateConflictException

from .models import CMISConfig, Vendor
from .utils import folder as folder_utils
from .utils.exceptions import (
    DocumentConflictException,
    DocumentLockConflictException,
    DocumentNotLockedException,
    FolderDoesNotExistError,
)

# The Document/Folder/Oio/Gebruiksrechten classes used in practice depend on the client
# (different classes exist for the webservice and browser binding)
Document = TypeVar("Document")
Gebruiksrechten = TypeVar("Gebruiksrechten")
Folder = TypeVar("Folder")
ObjectInformatieObject = TypeVar("ObjectInformatieObject")


class CMISClient:

    _main_repo_id = None
    _root_folder_id = None

    document_type = None
    gebruiksrechten_type = None
    oio_type = None
    folder_type = None
    zaakfolder_type = None
    zaaktypefolder_type = None

    def get_other_base_folder_name(self):
        config = CMISConfig.objects.get()
        return config.get_other_base_folder_name()

    def get_zaak_base_folder_name(self):
        config = CMISConfig.objects.get()
        return config.get_zaak_base_folder_name()

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

    def get_folder_by_name(self, name: str, parent: Folder) -> Folder:
        children_folders = parent.get_children_folders()
        for folder in children_folders:
            if folder.name == name:
                return folder
        raise FolderDoesNotExistError(
            "Folder %(folder_name)s does not exist in %(parent_folder_name)s.",
            params={"folder_name": folder.name, "parent_folder": parent.name},
        )

    def delete_cmis_folders_in_base(self):
        """Delete all the folders in the base folders"""
        config = CMISConfig.get_solo()

        root_folder = self.get_folder(self.root_folder_id)
        for folder_name in set(
            [config.get_zaak_base_folder_name(), config.get_other_base_folder_name()]
        ):
            try:
                folder = self.get_folder_by_name(folder_name, root_folder)
                folder.delete_tree()
            except FolderDoesNotExistError:
                pass

    def update_document(
        self, drc_uuid: str, lock: str, data: dict, content: Optional[BytesIO] = None
    ) -> Document:
        """Update a Document (with the EnkelvoudigInformatieObject properties)

        :param drc_uuid: string, the value of drc:document__uuid
        :param lock: string, value of the lock
        :param data: dict, the new properties of the document
        :param content: BytesIO, the new content of the document
        :return: Document, the updated document
        """
        cmis_doc = self.get_document(drc_uuid)

        if not cmis_doc.isVersionSeriesCheckedOut:
            raise DocumentNotLockedException(
                "Document is not checked out and/or locked."
            )

        if not cmis_doc.lock:
            raise DocumentNotLockedException(
                "Document is not checked out and/or locked."
            )

        correct_lock = constant_time_compare(lock, cmis_doc.lock)

        if not correct_lock:
            raise DocumentLockConflictException("Wrong document lock given.")

        # build up the properties
        current_properties = cmis_doc.properties
        new_properties = self.document_type.build_properties(data, new=False)

        diff_properties = {
            key: value
            for key, value in new_properties.items()
            if current_properties.get(key) != value
        }

        try:
            cmis_doc.update_properties(diff_properties, content)
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc

        return cmis_doc

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
                    document remains in the temporary folder
                - If the document is already linked to a zaak, the document is copied to the temporary folder and
                    the oio is created in the temporary folder
        2. The oio creates a link to a Zaak:
            A. If the document is already related to a zaak, a copy of the document is put in the
                correct zaaktype/zaak folder.
            B. If the document is NOT related to a zaak: the document is moved from the temporary folder
            to the correct zaaktype/zaak folder.

        If the document is linked already to a gebruiksrechten, then the gebruiksrechten object is also moved/copied.

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
        else:
            zaak_url = data["zaak"]

        # The oio for the besluit is created in the "Related data" of the temporary folder,
        # since it is not related to a zaak
        if zaak_url is None:
            destination_folder = self.get_or_create_other_folder()
        # The oio is created in the "Related data" folder of the zaak folder
        else:
            client_zaak = get_zds_client(zaak_url)
            zaak_data = client_zaak.retrieve("zaak", url=zaak_url)
            client_zaaktype = get_zds_client(zaak_data["zaaktype"])
            zaaktype_data = client_zaaktype.retrieve(
                "zaaktype", url=zaak_data["zaaktype"]
            )

            # Get or create the destination folder
            destination_folder = self.get_or_create_zaak_folder(
                zaaktype_data, zaak_data
            )

        related_data_folder = self.get_or_create_folder(
            "Related data", destination_folder
        )

        # Check if there are other Oios related to the document
        retrieved_oios = self.query(
            return_type_name="oio",
            lhs=["drc:oio__informatieobject = '%s'"],
            rhs=[data.get("informatieobject")],
        )

        # Get the parent folder to check if the document is in a Zaak folder
        parent_folder = document.get_parent_folders()[0]

        # Check if there are gebruiksrechten related to the document
        related_gebruiksrechten = self.query(
            return_type_name="gebruiksrechten",
            lhs=["drc:gebruiksrechten__informatieobject = '%s'"],
            rhs=[data.get("informatieobject")],
        )

        # Case 1: Already related to a zaak. Copy the document to the destination folder.
        if len(retrieved_oios) > 0 or "drc:zaakfolder" in parent_folder.objectTypeId:
            self.copy_document(document, destination_folder)
            if len(related_gebruiksrechten) > 0:
                for gebruiksrechten in related_gebruiksrechten:
                    self.copy_gebruiksrechten(gebruiksrechten, related_data_folder)
        # Case 2: Not related to a zaak. Move the document to the destination folder
        else:
            document.move_object(destination_folder)
            if len(related_gebruiksrechten) > 0:
                for gebruiksrechten in related_gebruiksrechten:
                    gebruiksrechten.move_object(related_data_folder)

        # Create the Oio in the "Related data" folder
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

    def get_or_create_zaak_folder(self, zaaktype: dict, zaak: dict) -> Folder:
        """Get or create all the folders in the configurable 'zaak' folder path"""
        cmis_config = CMISConfig.get_solo()
        path_elements = folder_utils.get_folder_structure(cmis_config.zaak_folder_path)

        parent_folder = self.get_folder(self.root_folder_id)
        now = timezone.now()

        zaaktype.setdefault(
            "object_type_id",
            f"{self.get_object_type_id_prefix('zaaktypefolder')}drc:zaaktypefolder",
        )
        zaaktype_properties = self.zaaktypefolder_type.build_properties(zaaktype)

        zaak.setdefault(
            "object_type_id",
            f"{self.get_object_type_id_prefix('zaakfolder')}drc:zaakfolder",
        )
        zaak_properties = self.zaakfolder_type.build_properties(zaak)

        ctx = {
            folder_utils.YEAR_PATH_ELEMENT_TEMPLATE.folder_name: (str(now.year), {}),
            folder_utils.MONTH_PATH_ELEMENT_TEMPLATE.folder_name: (str(now.month), {}),
            folder_utils.DAY_PATH_ELEMENT_TEMPLATE.folder_name: (str(now.day), {}),
            folder_utils.ZAAKTYPE_PATH_ELEMENT_TEMPLATE.folder_name: (
                f"zaaktype-{zaaktype.get('omschrijving')}-{zaaktype.get('identificatie')}",
                zaaktype_properties,
            ),
            folder_utils.ZAAK_PATH_ELEMENT_TEMPLATE.folder_name: (
                f"zaak-{zaak['identificatie']}",
                zaak_properties,
            ),
        }

        for pe in path_elements:
            folder_name, props = ctx.get(pe.folder_name, (pe.folder_name, {}))

            parent_folder = self.get_or_create_folder(folder_name, parent_folder, props)

        return parent_folder

    def get_or_create_other_folder(self) -> Folder:
        """Get or create all the folders in the configurable 'other' folder path"""
        cmis_config = CMISConfig.get_solo()
        path_elements = folder_utils.get_folder_structure(cmis_config.other_folder_path)

        parent_folder = self.get_folder(self.root_folder_id)
        now = timezone.now()

        ctx = {
            folder_utils.YEAR_PATH_ELEMENT_TEMPLATE.folder_name: (str(now.year), {}),
            folder_utils.MONTH_PATH_ELEMENT_TEMPLATE.folder_name: (str(now.month), {}),
            folder_utils.DAY_PATH_ELEMENT_TEMPLATE.folder_name: (str(now.day), {}),
        }

        for pe in path_elements:
            folder_name, props = ctx.get(pe.folder_name, (pe.folder_name, {}))

            parent_folder = self.get_or_create_folder(folder_name, parent_folder, props)

        return parent_folder

    def get_documents_related_to_zaak(self, identificatie: str) -> List[Document]:
        """Get all documents in the zaak folder with drc:zaakfolder__identificatie.

        :param identificatie: str, identification of the zaak
        :return: list of Documents
        """

        zaak_folder = self.query(
            return_type_name="zaakfolder",
            lhs=["drc:zaak__identificatie = '%s'"],
            rhs=[str(identificatie)],
        )[0]

        documents = zaak_folder.get_children_documents()

        return documents
