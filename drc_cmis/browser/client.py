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
    ZaakFolder,
    ZaakTypeFolder,
)
from drc_cmis.browser.request import CMISRequest
from drc_cmis.browser.utils import create_json_request_body
from drc_cmis.client import CMISClient
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


class CMISDRCClient(CMISClient, CMISRequest):
    """CMIS client for Browser binding (CMIS 1.1)"""

    document_type = Document
    gebruiksrechten_type = Gebruiksrechten
    oio_type = ObjectInformatieObject
    folder_type = Folder
    zaakfolder_type = ZaakFolder
    zaaktypefolder_type = ZaakTypeFolder

    @property
    def base_folder(self) -> Folder:
        if not self._base_folder:
            if self.base_folder_name == "":
                self._base_folder = self.get_folder(self.root_folder_id)
            else:
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
            self._root_folder_id = repository_info["-default-"]["rootFolderId"]

        return self._root_folder_id

    @property
    def vendor(self) -> str:
        repo_info = self.get_request(self.base_url)
        return repo_info["-default-"]["vendorName"]

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

    def create_folder(self, name: str, parent_id: str, properties: dict = None):
        logger.debug("CMIS: DRC_DOCUMENT: create_folder")
        data = {
            "objectId": parent_id,
            "cmisaction": "createFolder",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": name,
            "propertyId[1]": "cmis:objectTypeId",
            "propertyValue[1]": "cmis:folder",
        }

        if properties is not None:
            prop_count = 2
            for prop, value in properties.items():
                data[f"propertyId[{prop_count}]"] = prop
                data[f"propertyValue[{prop_count}]"] = value
                prop_count += 1

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

    def copy_gebruiksrechten(
        self, source_object: Gebruiksrechten, destination_folder: Folder
    ) -> Gebruiksrechten:
        """Copy a gebruiksrechten to a folder

        :param source_object: Gebruiksrechten, the gebruiksrechten to copy
        :param destination_folder: Folder, the folder in which to place the copied gebruiksrechten
        :return: the copied object
        """
        logger.debug("Gebruiksrechten (Browser binding): make_copy")

        # copy the properties from the source object
        properties = {
            property_name: property_details["value"]
            for property_name, property_details in source_object.properties.items()
            if "cmis:" not in property_name
        }

        file_name = get_random_string()

        properties.update(
            **{
                "cmis:objectTypeId": source_object.objectTypeId,
                "cmis:name": file_name,
                mapper(
                    "kopie_van", type="gebruiksrechten"
                ): source_object.objectId,  # Keep tack of where this is copied from.
            }
        )

        data = create_json_request_body(destination_folder, properties)

        json_response = self.post_request(self.root_folder_url, data=data)
        return Gebruiksrechten(json_response)

    def copy_document(self, document: Document, destination_folder: Folder) -> Document:
        """Copy document to a folder

        :param document: Document, the document to copy
        :param destination_folder: Folder, the folder in which to place the copied document
        :return: the copied document
        """
        logger.debug("Document (Browser binding): make_copy")

        # copy the properties from the source document
        properties = {
            property_name: property_details["value"]
            for property_name, property_details in document.properties.items()
            if "cmis:" not in property_name
        }

        properties.update(
            **{
                "cmis:objectTypeId": document.objectTypeId,
                mapper("titel", type="document"): f"{document.titel} - copy",
                "drc:kopie_van": document.uuid,  # Keep tack of where this is copied from.
            }
        )

        # Update the cmis:name to make it more unique
        file_name = f"{document.titel}-{get_random_string()}"
        properties["cmis:name"] = file_name

        data = create_json_request_body(destination_folder, properties)

        content = document.get_content_stream()
        json_response = self.post_request(self.root_folder_url, data=data)
        cmis_doc = Document(json_response)
        content.seek(0)

        return cmis_doc.set_content_stream(content)

    def create_content_object(
        self, data: dict, object_type: str, destination_folder: Folder = None
    ) -> Union[Gebruiksrechten, ObjectInformatieObject]:
        """Create a Gebruiksrechten or a ObjectInformatieObject

        :param data: dict, properties of the object to create
        :param object_type: string, either "gebruiksrechten" or "oio"
        :param destination_folder: Folder, a folder where to create the object. If not provided,
            the object will be placed in a temporary folder.
        :return: Either a Gebruiksrechten or ObjectInformatieObject
        """
        assert object_type in [
            "gebruiksrechten",
            "oio",
        ], "'object_type' can be only 'gebruiksrechten' or 'oio'"

        if destination_folder is None:
            now = timezone.now()
            year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
            month_folder = self.get_or_create_folder(str(now.month), year_folder)
            day_folder = self.get_or_create_folder(str(now.day), month_folder)
            destination_folder = self.get_or_create_folder("Related data", day_folder)

        properties = {
            mapper(key, type=object_type): value
            for key, value in data.items()
            if mapper(key, type=object_type)
        }

        json_data = {
            "objectId": destination_folder.objectId,
            "cmisaction": "createDocument",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": get_random_string(),
        }

        json_data["propertyId[1]"] = "cmis:objectTypeId"
        if "cmis:objectTypeId" in properties.keys():
            json_data["propertyValue[1]"] = properties.pop("cmis:objectTypeId")
        else:
            json_data[
                "propertyValue[1]"
            ] = f"{self.get_object_type_id_prefix(object_type)}drc:{object_type}"

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

    def create_document(
        self, identification: str, data: dict, content: BytesIO = None,
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
        data.setdefault(
            "object_type_id",
            f"{self.get_object_type_id_prefix('document')}drc:document",
        )

        if content is None:
            content = BytesIO()

        # Create Document in default folder
        year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
        month_folder = self.get_or_create_folder(str(now.month), year_folder)
        day_folder = self.get_or_create_folder(str(now.day), month_folder)

        properties = Document.build_properties(
            data, new=True, identification=identification
        )

        data = create_json_request_body(day_folder, properties)

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
