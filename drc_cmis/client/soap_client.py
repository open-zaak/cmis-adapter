import datetime
import uuid
from io import BytesIO
from typing import List, Optional, Union
from uuid import UUID

from django.utils.crypto import constant_time_compare

from cmislib.domain import CmisId
from cmislib.exceptions import UpdateConflictException

from drc_cmis.client.exceptions import (
    CmisUpdateConflictException,
    DocumentConflictException,
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockConflictException,
    DocumentLockedException,
    DocumentNotLockedException,
)
from drc_cmis.client.mapper import mapper
from drc_cmis.client.query import CMISQuery
from drc_cmis.cmis.soap_drc_document import Document, Folder
from drc_cmis.cmis.soap_request import SOAPCMISRequest
from drc_cmis.cmis.utils import (
    build_query_filters,
    extract_num_items,
    extract_object_properties_from_xml,
    extract_xml_from_soap,
    get_xml_doc,
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
                extracted_data = extract_object_properties_from_xml(
                    xml_response, "query"
                )
                folders = [Folder(data) for data in extracted_data]
            else:
                folders = []

            # Check if the base folder has already been created
            for folder in folders:
                if folder.name == self.base_folder_name:
                    self._base_folder = folder
                    break

            # If the base folder hasn't been created yet, create it
            if self._base_folder is None:
                self._base_folder = self.create_folder(
                    self.base_folder_name, self.root_folder_id
                )

        return self._base_folder

    def query(self, return_type, lhs: List[str], rhs: List[str]) -> List["return_type"]:
        table = return_type.table
        where = (" WHERE " + " AND ".join(lhs)) if lhs else ""
        query = CMISQuery("SELECT * FROM %s%s" % (table, where))

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id, statement=query(*rhs), cmis_action="query"
        )

        soap_response = self.request(
            "DiscoveryService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(xml_response, "query")

        return [return_type(cmis_object) for cmis_object in extracted_data]

    def get_or_create_folder(self, name: str, parent: Folder) -> Folder:
        """Get or create a folder 'name/' in a folder with cmis:objectId `parent_id`

        :param name: string, the name of the folder to create
        :param parent: Folder, the parent folder
        :return: the folder that was created
        """

        children_folders = parent.get_children_folders()
        for folder in children_folders:
            if folder.name == name:
                return folder

        # Create new folder, as it doesn't exist yet
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
        extracted_data = extract_object_properties_from_xml(
            xml_response, "createFolder"
        )[0]
        return Folder(extracted_data)

    def create_document(
        self, identification: str, data: dict, content: BytesIO = None
    ) -> Document:

        self.check_document_exists(identification)

        now = datetime.datetime.now()
        data.setdefault("versie", "1")

        content_id = str(uuid.uuid4())
        if content is None:
            content = BytesIO()

        year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
        month_folder = self.get_or_create_folder(str(now.month), year_folder)
        day_folder = self.get_or_create_folder(str(now.day), month_folder)

        properties = Document.build_properties(
            data, new=True, identification=identification
        )

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            folder_id=day_folder.objectId,
            properties=properties,
            cmis_action="createDocument",
            content_id=content_id,
        )

        soap_response = self.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
            attachments=[(content_id, content)],
        )

        xml_response = extract_xml_from_soap(soap_response)
        # Creating the document only returns its ID
        extracted_data = extract_object_properties_from_xml(
            xml_response, "createDocument"
        )[0]
        new_document_id = extracted_data["properties"]["objectId"]["value"]

        # Request all the properties of the newly created document
        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            object_id=new_document_id,
            cmis_action="getObject",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]

        return Document(extracted_data)

    def lock_document(self, uuid: str, lock: str):
        cmis_doc = self.get_document(uuid)

        already_locked = DocumentLockedException(
            "Document was already checked out", code="double_lock"
        )

        try:
            pwc = cmis_doc.checkout()
            assert (
                pwc.isPrivateWorkingCopy
            ), "checkout result must be a private working copy"
            if pwc.lock:
                raise already_locked

            # store the lock value on the PWC so we can compare it later
            pwc.update_properties({mapper("lock"): lock})
        except CmisUpdateConflictException as exc:
            raise already_locked from exc

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
        num_items = extract_num_items(xml_response)
        if num_items == 0:
            raise does_not_exist

        extracted_data = extract_object_properties_from_xml(xml_response, "query")[0]
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
