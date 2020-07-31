import datetime
import logging
from io import BytesIO
from typing import List, Optional, Union
from uuid import UUID

from django.utils import timezone
from django.utils.crypto import constant_time_compare

from cmislib.exceptions import UpdateConflictException

from drc_cmis.browser.drc_document import (
    Document,
    Folder,
    Gebruiksrechten,
    ObjectInformatieObject,
)
from drc_cmis.browser.request import CMISRequest
from drc_cmis.utils.exceptions import (
    CmisUpdateConflictException,
    DocumentConflictException,
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockConflictException,
    DocumentLockedException,
    DocumentNotLockedException,
    FolderDoesNotExistError,
    GetFirstException,
    LockDidNotMatchException,
)
from drc_cmis.utils.mapper import mapper
from drc_cmis.utils.query import CMISQuery
from drc_cmis.utils.utils import build_query_filters, get_random_string

logger = logging.getLogger(__name__)


class CMISDRCClient(CMISRequest):
    """CMIS client for Browser binding (CMIS 1.1)"""

    _main_repo_id = None
    _root_folder_id = None
    _base_folder = None

    @property
    def base_folder(self) -> Folder:
        if not self._base_folder:
            base = self.get_request(self.root_folder_url)
            for folder_response in base.get("objects"):
                folder = Folder(folder_response["object"])
                if folder.name == self.base_folder_name:
                    self._base_folder = folder
                    break
            if not self._base_folder:
                self._base_folder = self.create_folder(
                    name=self.base_folder_name, parent_id=self.root_folder_id
                )
        return self._base_folder

    @property
    def root_folder_id(self) -> str:
        """Returns the objectId of the root folder"""
        if self._root_folder_id is None:
            repository_info = self.get_request(self.base_url)
            self._root_folder_id = f"workspace://SpacesStore/{repository_info['-default-']['rootFolderId']}"

        return self._root_folder_id

    def get_return_type(self, type_name: str) -> type:
        error_message = f"No class {type_name} exists for this client."
        type_name = type_name.lower()
        assert type_name in [
            "folder",
            "document",
            "gebruiksrechten",
            "oio",
        ], error_message

        if type_name == "folder":
            return Folder
        elif type_name == "document":
            return Document
        elif type_name == "gebruiksrechten":
            return Gebruiksrechten
        elif type_name == "oio":
            return ObjectInformatieObject

    # generic querying
    def query(self, return_type_name: str, lhs: List[str], rhs: List[str]):
        return_type = self.get_return_type(return_type_name)
        table = return_type.table
        where = (" WHERE " + " AND ".join(lhs)) if lhs else ""
        query = CMISQuery("SELECT * FROM %s%s" % (table, where))

        body = {"cmisaction": "query", "statement": query(*rhs)}
        response = self.post_request(self.base_url, body)
        logger.debug(response)
        return self.get_all_results(response, return_type)

    def get_all_versions(self, document: Document) -> List[Document]:
        return document.get_all_versions()

    def get_or_create_folder(self, name: str, parent: Folder) -> Folder:
        """
        Get or create the folder with :param:`name` in :param:`parent`.

        :param name: string, the name of the folder to create.
        :param parent: Folder, parent folder to create the folder in as subfolder.
        :return: Folder, the folder that was retrieved or created.
        """
        logger.debug("CMIS_CLIENT: _get_or_create_folder")

        children_folders = parent.get_children_folders()
        for folder in children_folders:
            if folder.name == name:
                return folder

        return self.create_folder(name, parent.objectId)

    def create_folder(self, name, parent_id):
        logger.debug("CMIS: DRC_DOCUMENT: create_folder")
        data = {
            "objectId": parent_id,
            "cmisaction": "createFolder",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": name,
            "propertyId[1]": "cmis:objectTypeId",
            "propertyValue[1]": "cmis:folder",
        }

        json_response = self.post_request(self.root_folder_url, data=data)
        return Folder(json_response)

    def get_folder(self, uuid: str) -> Folder:
        """Retrieve folder with objectId constructed with the uuid given"""

        query = CMISQuery(
            "SELECT * FROM cmis:folder WHERE cmis:objectId = 'workspace://SpacesStore/%s'"
        )

        body = {"cmisaction": "query", "statement": query(uuid)}
        json_response = self.post_request(self.base_url, body)

        try:
            return self.get_first_result(json_response, Folder)
        except GetFirstException:
            error_string = f"Folder met objectId 'workspace://SpacesStore/{uuid}' bestaat niet in het CMIS connection"
            raise FolderDoesNotExistError(error_string)

    def delete_cmis_folders_in_base(self):
        self.base_folder.delete_tree()

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

        now = timezone.now()
        year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
        month_folder = self.get_or_create_folder(str(now.month), year_folder)
        day_folder = self.get_or_create_folder(str(now.day), month_folder)
        object_folder = self.get_or_create_folder(object_type.capitalize(), day_folder)

        properties = {
            mapper(key, type=object_type): value
            for key, value in data.items()
            if mapper(key, type=object_type)
        }

        json_data = {
            "objectId": object_folder.objectId,
            "cmisaction": "createDocument",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": get_random_string(),
        }

        json_data["propertyId[1]"] = "cmis:objectTypeId"
        if "cmis:objectTypeId" in properties.keys():
            json_data["propertyValue[1]"] = properties.pop("cmis:objectTypeId")
        else:
            json_data["propertyValue[1]"] = f"D:drc:{object_type}"

        prop_count = 2
        for prop_key, prop_value in properties.items():
            if isinstance(prop_value, datetime.date):
                prop_value = prop_value.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            json_data[f"propertyId[{prop_count}]"] = prop_key
            json_data[f"propertyValue[{prop_count}]"] = prop_value
            prop_count += 1

        json_response = self.post_request(self.root_folder_url, data=json_data)

        if object_type == "gebruiksrechten":
            return Gebruiksrechten(json_response)
        elif object_type == "oio":
            return ObjectInformatieObject(json_response)

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

        data = {"cmisaction": "query", "statement": query(object_type, str(uuid))}

        json_response = self.post_request(self.base_url, data)

        try:
            return self.get_first_result(
                json_response, self.get_return_type(object_type)
            )
        except GetFirstException:
            object_title = object_type.capitalize()
            error_string = (
                f"{object_title} met uuid {uuid} bestaat niet in het CMIS connection"
            )
            raise DocumentDoesNotExistError(error_string)

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
        """Create a cmis document.

        :param identification: string, A unique identifier for the document.
        :param data: dict, A dict with all the data that needs to be saved on the document.
        :param content: BytesIO, The content of the document.
        :return: document
        """
        logger.debug("CMIS_CLIENT: create_document")
        self.check_document_exists(identification)

        now = timezone.now()
        data.setdefault("versie", 1)

        if content is None:
            content = BytesIO()

        year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
        month_folder = self.get_or_create_folder(str(now.month), year_folder)
        day_folder = self.get_or_create_folder(str(now.day), month_folder)
        document_folder = self.get_or_create_folder("Documents", day_folder)

        properties = Document.build_properties(
            data, new=True, identification=identification
        )

        data = {
            "objectId": document_folder.objectId,
            "cmisaction": "createDocument",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": properties.pop("cmis:name"),
        }

        data["propertyId[1]"] = "cmis:objectTypeId"
        if "cmis:objectTypeId" in properties.keys():
            data["propertyValue[1]"] = properties.pop("cmis:objectTypeId")
        else:
            data["propertyValue[1]"] = "drc:document"

        prop_count = 2
        for prop_key, prop_value in properties.items():
            if isinstance(prop_value, datetime.date) or isinstance(
                prop_value, datetime.datetime
            ):
                prop_value = prop_value.strftime("%Y-%m-%dT%H:%M:%S")

            data[f"propertyId[{prop_count}]"] = prop_key
            data[f"propertyValue[{prop_count}]"] = prop_value
            prop_count += 1

        json_response = self.post_request(self.root_folder_url, data=data)
        cmis_doc = Document(json_response)
        content.seek(0)
        return cmis_doc.set_content_stream(content)

    def lock_document(self, uuid: str, lock: str):
        """
        Check out the CMIS document and store the lock value for check in/unlock.
        """
        logger.debug("CMIS checkout of document %s (lock value %s)", uuid, lock)
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

        logger.debug(
            "CMIS checkout of document %s with lock value %s succeeded", uuid, lock
        )

    def unlock_document(self, uuid: str, lock: str, force: bool = False) -> Document:
        """Unlock a document with objectId workspace://SpacesStore/<uuid>"""
        logger.debug(f"CMIS_BACKEND: unlock_document {uuid} start with: {lock}")
        cmis_doc = self.get_document(uuid)
        pwc = cmis_doc.get_private_working_copy()

        if constant_time_compare(pwc.lock, lock) or force:
            pwc.update_properties({mapper("lock"): ""})
            new_doc = pwc.checkin("Updated via Documenten API")
            logger.debug("Unlocked document with UUID %s (forced: %s)", uuid, force)
            return new_doc

        raise LockDidNotMatchException("Lock did not match", code="unlock-failed")

    def update_document(
        self, uuid: str, lock: str, data: dict, content=None
    ) -> Document:
        logger.debug("Updating document with UUID %s", uuid)
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

        if content is not None:
            pwc.set_content_stream(content)

        return pwc

    def get_document(self, uuid: Optional[str], via_identification=None, filters=None):
        """
        Given a cmis document instance.

        :param uuid: UUID of the document as used in the endpoint URL
        :return: :class:`AtomPubDocument` object, the latest version of this document
        """
        logger.debug("CMIS_CLIENT: get_cmis_document")
        assert (
            not via_identification
        ), "Support for 'via_identification' is being dropped"

        error_string = (
            f"Document met identificatie {uuid} bestaat niet in het CMIS connection"
        )
        does_not_exist = DocumentDoesNotExistError(error_string)

        # shortcut - no reason in going over the wire
        if uuid is None:
            raise does_not_exist

        # this always selects the latest version
        query = CMISQuery("SELECT * FROM drc:document WHERE cmis:objectId = '%s' %s")

        filter_string = build_query_filters(
            filters, filter_string="AND ", strip_end=True
        )
        data = {
            "cmisaction": "query",
            "statement": query(uuid, filter_string),
        }
        json_response = self.post_request(self.base_url, data)

        try:
            return self.get_first_result(json_response, Document)
        except GetFirstException as exc:
            raise does_not_exist from exc

    def delete_document(self, uuid: str) -> None:
        """Delete all versions of a document with objectId workspace://SpacesStore/<uuid>"""
        document = self.get_document(uuid=uuid)
        document.delete_object()

    def check_document_exists(self, identification: Union[str, UUID]):
        """Query by identification (``identificatie``) if a document is in the repository"""

        # FIXME: should be both bronorganisatie and identification check, not just identification
        logger.debug("CMIS_CLIENT: _check_document_exists")

        column = mapper("identificatie", type="document")
        query = CMISQuery(f"SELECT * FROM drc:document WHERE {column} = '%s'")

        data = {"cmisaction": "query", "statement": query(str(identification))}
        json_response = self.post_request(self.base_url, data)
        if json_response["numItems"] > 0:
            error_string = f"Document identificatie {identification} is niet uniek."
            raise DocumentExistsError(error_string)
