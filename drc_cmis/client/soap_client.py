import datetime
import uuid
from io import BytesIO
from typing import List, Optional, Union
from uuid import UUID

from django.utils.crypto import constant_time_compare
from django.utils.translation import ugettext_lazy as _

from cmislib.domain import CmisId
from cmislib.exceptions import UpdateConflictException
from rest_framework.exceptions import ValidationError

from drc_cmis.client.exceptions import (
    CmisUpdateConflictException,
    DocumentConflictException,
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockConflictException,
    DocumentLockedException,
    DocumentNotLockedException,
    FolderDoesNotExistError,
)
from drc_cmis.client.mapper import mapper
from drc_cmis.client.query import CMISQuery
from drc_cmis.client.utils import get_random_string
from drc_cmis.cmis.soap_drc_document import (
    Document,
    Folder,
    Gebruiksrechten,
    ObjectInformatieObject,
)
from drc_cmis.cmis.soap_request import SOAPCMISRequest
from drc_cmis.cmis.utils import (
    build_query_filters,
    extract_num_items,
    extract_object_properties_from_xml,
    extract_xml_from_soap,
    make_soap_envelope,
)


class CMISClientException(ValidationError):
    def __init__(
        self,
        detail,
        create=False,
        update=False,
        retreive_single=False,
        delete=False,
        retreive_list=False,
        code=None,
    ):
        self.create = create
        self.update = update
        self.retreive_single = retreive_single
        self.delete = delete
        self.retreive_list = retreive_list

        super().__init__(detail, code)


class SOAPCMISClient(SOAPCMISRequest):

    _main_repo_id = None
    _root_folder_id = None
    _base_folder = None

    @property
    def base_folder(self) -> Folder:

        if self._base_folder is None:
            query = CMISQuery("SELECT * FROM cmis:folder WHERE IN_FOLDER('%s')")

            soap_envelope = make_soap_envelope(
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

    def query(
        self, return_type, lhs: List[str], rhs: List[str]
    ) -> List[Union[Document, Gebruiksrechten, ObjectInformatieObject]]:
        table = return_type.table
        where = (" WHERE " + " AND ".join(lhs)) if lhs else ""
        query = CMISQuery("SELECT * FROM %s%s" % (table, where))

        soap_envelope = make_soap_envelope(
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

        soap_envelope = make_soap_envelope(
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

        # Creating a folder only returns the objectId
        folder_id = extracted_data["properties"]["objectId"]["value"]

        return self.get_folder(folder_id)

    def get_folder(self, object_id: str) -> Folder:
        """Retrieve folder with given objectId"""

        query = CMISQuery(
            "SELECT * FROM cmis:folder WHERE cmis:objectId = 'workspace://SpacesStore/%s'"
        )

        soap_envelope = make_soap_envelope(
            repository_id=self.main_repo_id,
            statement=query(object_id),
            cmis_action="query",
        )

        soap_response = self.request(
            "DiscoveryService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        num_items = extract_num_items(xml_response)
        if num_items == 0:
            error_string = (
                f"Folder met objectId {object_id} bestaat niet in het CMIS connection"
            )
            does_not_exist = FolderDoesNotExistError(error_string)
            raise does_not_exist

        extracted_data = extract_object_properties_from_xml(xml_response, "query")[0]
        return Folder(extracted_data)

    def delete_cmis_folders_in_base(self):
        self.base_folder.delete_tree()

    # TODO Generalise so that it creates "Documents" too?
    def create_content_object(
        self, data: dict, object_type: str
    ) -> Union[Gebruiksrechten, ObjectInformatieObject]:
        """Create a Gebruiksrechten or a ObjectInformatieObject

        :param data: dict, properties of the object to create
        :param object_type: string, either "gebruiksrechten" or "oio"
        :return: Either a Gebruiksrechten or ObjectInformatieObject
        """
        assert object_type in [
            "gebruiksrechten",
            "oio",
        ], "'object_type' can be only 'gebruiksrechten' or 'oio'"

        now = datetime.datetime.now()
        year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
        month_folder = self.get_or_create_folder(str(now.month), year_folder)
        day_folder = self.get_or_create_folder(str(now.day), month_folder)
        object_folder = self.get_or_create_folder(object_type.capitalize(), day_folder)

        properties = {
            mapper(key, type=object_type): value
            for key, value in data.items()
            if mapper(key, type=object_type)
        }

        properties.setdefault("cmis:objectTypeId", f"D:drc:{object_type}")
        properties.setdefault("cmis:name", get_random_string())

        soap_envelope = make_soap_envelope(
            repository_id=self.main_repo_id,
            folder_id=object_folder.objectId,
            properties=properties,
            cmis_action="createDocument",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml(),
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(
            xml_response, "createDocument"
        )[0]
        new_object_id = extracted_data["properties"]["objectId"]["value"]

        # Request all the properties of the newly created object
        soap_envelope = make_soap_envelope(
            repository_id=self.main_repo_id,
            object_id=new_object_id,
            cmis_action="getObject",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]

        if object_type == "oio":
            return ObjectInformatieObject(extracted_data)
        elif object_type == "gebruiksrechten":
            return Gebruiksrechten(extracted_data)

    def get_content_object(
        self, uuid: Union[str, UUID], object_type: str
    ) -> Union[Gebruiksrechten, ObjectInformatieObject]:
        """Get the gebruiksrechten/oio with specified uuid

        :param uuid: string or UUID, identifier that when combined with 'workspace://SpacesStore/' and the version
        number gives the cmis:objectId
        :param object_type: string, either "gebruiksrechten" or "oio"
        :return: Either a Gebruiksrechten or ObjectInformatieObject
        """

        assert object_type in [
            "gebruiksrechten",
            "oio",
        ], "'object_type' can be only 'gebruiksrechten' or 'oio'"

        query = CMISQuery(
            "SELECT * FROM drc:%s WHERE cmis:objectId = 'workspace://SpacesStore/%s;1.0'"
        )

        soap_envelope = make_soap_envelope(
            repository_id=self.main_repo_id,
            statement=query(object_type, str(uuid)),
            cmis_action="query",
        )

        soap_response = self.request(
            "DiscoveryService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        num_items = extract_num_items(xml_response)

        object_title = object_type.capitalize()
        error_string = f"{object_title} document met identificatie {uuid} bestaat niet in het CMIS connection"
        does_not_exist = DocumentDoesNotExistError(error_string)

        if num_items == 0:
            raise does_not_exist

        extracted_data = extract_object_properties_from_xml(xml_response, "query")[0]

        if object_type == "oio":
            return ObjectInformatieObject(extracted_data)
        elif object_type == "gebruiksrechten":
            return Gebruiksrechten(extracted_data)

    def delete_content_object(self, uuid: Union[str, UUID], object_type: str):
        """Delete the gebruiksrechten/objectinformatieobject with specified uuid

        :param uuid: string or UUID, identifier that when combined with 'workspace://SpacesStore/' and the version
        number gives the cmis:objectId
        :param object_type: string, either "gebruiksrechten" or "oio"
        :return: Either a Gebruiksrechten or ObjectInformatieObject
        """

        content_object = self.get_content_object(uuid, object_type=object_type)
        content_object.delete_object()

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
        document_folder = self.get_or_create_folder("Documents", day_folder)

        properties = Document.build_properties(
            data, new=True, identification=identification
        )

        soap_envelope = make_soap_envelope(
            repository_id=self.main_repo_id,
            folder_id=document_folder.objectId,
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
        soap_envelope = make_soap_envelope(
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
                pwc.versionLabel == "pwc"
            ), "checkout result must be a private working copy"
            if pwc.lock:
                raise already_locked

            # store the lock value on the PWC so we can compare it later
            pwc.update_properties({mapper("lock"): lock})
        except CmisUpdateConflictException as exc:
            raise already_locked from exc

    def unlock_document(self, uuid: str, lock: str, force: bool = False):
        cmis_doc = self.get_document(uuid)
        pwc = cmis_doc.get_private_working_copy()

        if constant_time_compare(pwc.lock, lock) or force:
            pwc.update_properties({mapper("lock"): ""})
            return pwc.checkin("Updated via Documenten API")

        raise CMISClientException(
            detail=_("Lock did not match"), update=True, code="unlock-failed"
        )

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
            pwc.update_properties(diff_properties, content)
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc

        return pwc

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

        soap_envelope = make_soap_envelope(
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
            "SELECT * FROM drc:document WHERE drc:document__identificatie = '%s'"
        )

        soap_envelope = make_soap_envelope(
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
