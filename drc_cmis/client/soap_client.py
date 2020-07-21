import datetime
from io import BytesIO
from typing import Optional, Union
from uuid import UUID

from cmislib.domain import CmisId
from cmislib.exceptions import UpdateConflictException
from django.utils.crypto import constant_time_compare

from client.exceptions import (
    DocumentExistsError,
    DocumentDoesNotExistError,
    DocumentNotLockedException,
    DocumentLockConflictException,
    DocumentConflictException,
)
from client.query import CMISQuery
from cmis.soap_drc_document import Folder, Document
from cmis.soap_request import SOAPCMISRequest
from cmis.utils import (
    get_xml_doc,
    extract_xml_from_soap,
    extract_properties_from_xml,
    extract_repository_id_from_xml,
    extract_root_folder_id_from_xml,
    extract_num_items,
    build_query_filters,
    extract_folders_from_xml,
)


class SOAPCMISClient(SOAPCMISRequest):

    _main_repo_id = None
    _root_folder_id = None
    _base_folder = None

    @property
    def base_folder(self) -> Folder:

        if self._base_folder is None:
            query = CMISQuery(f"SELECT * FROM cmis:folder WHERE IN_FOLDER('%s')")

            soap_envelope = get_xml_doc(
                repository_id=self.main_repo_id,
                statement=query(str(self.root_folder_id)),
                cmis_action="query",
            )

            soap_response = self.request(
                "DiscoveryService", soap_envelope=soap_envelope.toxml()
            )
            xml_response = extract_xml_from_soap(soap_response)
            num_items = extract_num_items(xml_response)
            if num_items > 0:
                extracted_data = extract_folders_from_xml(xml_response)
                folders = [Folder(data) for data in extracted_data]
            else:
                folders = []

            # Check if the base folder has already been created
            for folder in folders:
                # FIXME migration for the CMISConfig
                # if folder.name == self.base_folder_name:
                if folder.name == "DRC":
                    self._base_folder = folder
                    break

            # If the base folder hasn't been created yet, create it
            if self._base_folder is None:
                self._base_folder = self.create_folder(
                    self.base_folder_name, self.root_folder_id
                )

        return self._base_folder

    def get_or_create_folder(self, name: str, parent: Folder) -> Folder:
        """Get or create a folder 'name/' in a folder with cmis:objectId `parent_id`

        :param name: string, the name of the folder to create
        :param parent: Folder, the parent folder
        :return: the folder that was created
        """

        children_folders = parent.get_children_folders()
        for foldren in children_folders:
            if foldren.name == name:
                return foldren

        # Create new foldren, as it doesn't exist yet
        return self.create_folder(name, parent.objectId)

    def create_folder(self, name: str, parent_id: str) -> Folder:
        """Create a new folder inside a parent

        :param name: string, name of the new folder to create
        :param parent_id: string, cmis:objectId of the parent folder
        :return: Folder, the created folder
        """

        object_type_id = CmisId("cmis:folder")

        properties = {"cmis:objectTypeId": object_type_id, "cmis:name": name}

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            folder_id=parent_id,
            properties=properties,
            cmis_action="createFolder",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_properties_from_xml(xml_response, "createFolder")[0]
        return Folder(extracted_data)

    def create_document(
        self, identification: str, data: dict, content: Optional[BytesIO] = None
    ) -> Document:

        self.check_document_exists(identification)

        now = datetime.datetime.now()
        data.setdefault("versie", 1)

        if content is None:
            content = BytesIO()

        year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
        month_folder = self.get_or_create_folder(str(now.month), year_folder)
        day_folder = self.get_or_create_folder(str(now.day), month_folder)

    def update_document(
        self, uuid: str, lock: str, data: dict, content: Optional[BytesIO] = None
    ):

        cmis_doc = self.get_document(uuid)

        if not cmis_doc.isVersionSeriesCheckedOut:
            raise DocumentNotLockedException(
                "Document is not checked out and/or locked."
            )

        assert not cmis_doc.isPrivateWorkingCopy, "Unexpected PWC retrieved"

        pwc = cmis_doc.get_private_working_copy()

        if not pwc.lock:
            raise DocumentNotLockedException(
                "Document is not checked out and/or locked."
            )

        correct_lock = constant_time_compare(lock, pwc.lock)

        if not correct_lock:
            raise DocumentLockConflictException("Wrong document lock given.")

        # build up the properties
        current_properties = cmis_doc.properties
        new_properties = Document.build_properties(data, new=False)

        diff_properties = {
            key: value
            for key, value in new_properties.items()
            if current_properties.get(key) != value
        }

        try:
            pwc.update_properties(diff_properties)
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc

    def get_document(
        self, uuid: Optional[str] = None, filters: Optional[dict] = None
    ) -> Document:
        """Retrieve a document in the main repository"""

        error_string = (
            f"Document met identificatie {uuid} bestaat niet in het CMIS connection"
        )
        does_not_exist = DocumentDoesNotExistError(error_string)

        if uuid is None:
            raise does_not_exist

        # This selects the latest version of a document
        query = CMISQuery(
            "SELECT * FROM drc:document WHERE cmis:objectId = 'workspace://SpacesStore/%s' %s"
        )

        filter_string = build_query_filters(
            filters, filter_string="AND ", strip_end=True
        )

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            statement=query(uuid, filter_string),
            cmis_action="query",
        )

        soap_response = self.request(
            "DiscoveryService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)

        extracted_data = extract_properties_from_xml(xml_response, "query")[0]
        return Document(extracted_data)

    def check_document_exists(self, identification: Union[str, UUID]):
        """Query by identification if a document is in the repository"""

        query = CMISQuery(
            f"SELECT * FROM drc:document WHERE drc:document__identificatie = '%s'"
        )

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            statement=query(str(identification)),
            cmis_action="query",
        )

        soap_response = self.request(
            "DiscoveryService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)

        num_items = extract_num_items(xml_response)

        if num_items > 0:
            error_string = f"Document identificatie {identification} is niet uniek."
            raise DocumentExistsError(error_string)
