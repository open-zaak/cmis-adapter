import datetime
import logging
import uuid
from io import BytesIO
from typing import List, Optional, Union
from uuid import UUID

from django.utils.crypto import constant_time_compare

from drc_cmis.browser.drc_document import (
    CMISContentObject,
    Document,
    Folder,
    Gebruiksrechten,
    ObjectInformatieObject,
    ZaakFolder,
    ZaakTypeFolder,
)
from drc_cmis.browser.request import Request
from drc_cmis.browser.utils import create_json_request_body
from drc_cmis.client import CMISClient
from drc_cmis.utils.exceptions import (
    CmisInvalidArgumentException,
    CmisUpdateConflictException,
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockedException,
    DocumentSizeMismatchException,
    FolderDoesNotExistError,
    GetFirstException,
    LockDidNotMatchException,
)
from drc_cmis.utils.mapper import mapper
from drc_cmis.utils.query import CMISQuery
from drc_cmis.utils.utils import (
    build_query_filters,
    extract_latest_version,
    get_random_string,
)

logger = logging.getLogger(__name__)


class CMISDRCClient(CMISClient):
    """CMIS client for Browser binding (CMIS 1.1)"""

    document_type = Document
    gebruiksrechten_type = Gebruiksrechten
    oio_type = ObjectInformatieObject
    folder_type = Folder
    zaakfolder_type = ZaakFolder
    zaaktypefolder_type = ZaakTypeFolder

    _request = None
    _repository_info = None

    def get_request(self, url, params=None):
        if not self._request:
            self._request = Request()
        return self._request.get_request(url, self.user, self.password, params)

    def post_request(self, url, data, headers=None, files=None):
        if not self._request:
            self._request = Request()
        return self._request.post_request(
            url, data, self.user, self.password, headers, files
        )

    @property
    def vendor(self) -> str:
        return self.repository_info["vendorName"]

    @property
    def base_url(self):
        return self.config.client_url

    @property
    def time_zone(self):
        return self.config.time_zone

    @property
    def root_folder_url(self):
        return f"{self.base_url}/root"

    @property
    def user(self):
        return self.config.client_user

    @property
    def password(self):
        return self.config.client_password

    @property
    def repository_info(self) -> dict:
        if not self._repository_info:
            logger.debug(
                "CMIS_ADAPTER: get_repository_info: GET request url: %s", self.base_url
            )

            response = self.get_request(self.base_url)

            logger.debug("CMIS_ADAPTER: get_repository_info: response: %s", response)
            self._repository_info = response["-default-"]

        return self._repository_info

    @property
    def root_folder_id(self) -> str:
        """Returns the objectId of the root folder"""
        return self.repository_info["rootFolderId"]

    def get_first_result(self, json, return_type):
        if len(json.get("results")) == 0:
            raise GetFirstException()

        return return_type(json.get("results")[0])

    def get_all_results(self, json, return_type):
        results = []
        for item in json.get("results"):
            results.append(return_type(item))
        return results

    def get_all_objects(self, json, return_type):
        objects = []
        for item in json:
            objects.append(return_type(item.get("object")))
        return objects

    # generic querying
    def query(
        self, return_type_name: str, lhs: List[str] = None, rhs: List[str] = None
    ):
        return_type = self.get_return_type(return_type_name)
        table = return_type.table
        where = (" WHERE " + " AND ".join(lhs)) if lhs else ""
        query = CMISQuery("SELECT * FROM %s%s" % (table, where))
        statement = query(*rhs) if rhs else query()

        body = {"cmisaction": "query", "statement": statement}
        logger.debug("CMIS_ADAPTER: query: request data: %s", body)
        response = self.post_request(self.base_url, body)
        logger.debug("CMIS_ADAPTER: query: response: %s", response)

        return self.get_all_results(response, return_type)

    def create_folder(self, name: str, parent_id: str, properties: dict = None):
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

        logger.debug("CMIS_ADAPTER: create_folder: request data: %s", data)

        json_response = self.post_request(self.root_folder_url, data=data)
        logger.debug("CMIS_ADAPTER: create_folder: response data: %s", json_response)

        return Folder(json_response)

    def get_folder(self, object_id: str) -> Folder:
        """Retrieve folder with objectId given"""

        query = CMISQuery("SELECT * FROM cmis:folder WHERE cmis:objectId = '%s'")

        body = {"cmisaction": "query", "statement": query(object_id)}
        logger.debug("CMIS_ADAPTER: get_folder: request data: %s", body)
        json_response = self.post_request(self.base_url, body)
        logger.debug("CMIS_ADAPTER: get_folder: response data: %s", json_response)

        try:
            return self.get_first_result(json_response, Folder)
        except GetFirstException:
            error_string = (
                f"Folder met objectId '{object_id}' bestaat niet in het CMIS connection"
            )
            raise FolderDoesNotExistError(error_string)

    def copy_gebruiksrechten(
        self, source_object: Gebruiksrechten, destination_folder: Folder
    ) -> Gebruiksrechten:
        """Copy a gebruiksrechten to a folder

        :param source_object: Gebruiksrechten, the gebruiksrechten to copy
        :param destination_folder: Folder, the folder in which to place the copied gebruiksrechten
        :return: the copied object
        """
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
                mapper("uuid", type="gebruiksrechten"): str(uuid.uuid4()),
            }
        )

        data = create_json_request_body(destination_folder, properties)
        logger.debug("CMIS_ADAPTER: copy_gebruiksrechten: request data: %s", data)

        json_response = self.post_request(self.root_folder_url, data=data)
        logger.debug(
            "CMIS_ADAPTER: copy_gebruiksrechten: response data: %s", json_response
        )

        return Gebruiksrechten(json_response)

    def copy_document(self, document: Document, destination_folder: Folder) -> Document:
        """Copy document to a folder

        :param document: Document, the document to copy
        :param destination_folder: Folder, the folder in which to place the copied document
        :return: the copied document
        """

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
                "drc:document__uuid": str(uuid.uuid4()),
            }
        )

        # Update the cmis:name to make it more unique
        file_name = f"{document.titel}-{get_random_string()}"
        properties["cmis:name"] = file_name

        data = create_json_request_body(destination_folder, properties)
        logger.debug("CMIS_ADAPTER: copy_document: request data: %s", data)

        content = document.get_content_stream()
        json_response = self.post_request(self.root_folder_url, data=data)
        logger.debug("CMIS_ADAPTER: copy_document: response data: %s", json_response)

        cmis_doc = Document(json_response)
        content.seek(0)

        return cmis_doc.set_content_stream(content, filename=document.bestandsnaam)

    def create_content_object(
        self, data: dict, object_type: str, destination_folder: Folder = None
    ) -> CMISContentObject:
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
            other_folder = self.get_or_create_other_folder()
            destination_folder = self.get_or_create_folder("Related data", other_folder)

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
            "propertyId[1]": f"drc:{object_type}__uuid",
            "propertyValue[1]": str(uuid.uuid4()),
        }

        json_data["propertyId[2]"] = "cmis:objectTypeId"
        if "cmis:objectTypeId" in properties.keys():
            json_data["propertyValue[2]"] = properties.pop("cmis:objectTypeId")
        else:
            json_data[
                "propertyValue[2]"
            ] = f"{self.get_object_type_id_prefix(object_type)}drc:{object_type}"

        prop_count = 3
        for prop_key, prop_value in properties.items():
            if isinstance(prop_value, datetime.date):
                prop_value = prop_value.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            json_data[f"propertyId[{prop_count}]"] = prop_key
            json_data[f"propertyValue[{prop_count}]"] = prop_value
            prop_count += 1

        logger.debug("CMIS_ADAPTER: create_content_object: request data: %s", json_data)
        json_response = self.post_request(self.root_folder_url, data=json_data)
        logger.debug(
            "CMIS_ADAPTER: create_content_object: response data: %s", json_response
        )

        if object_type == "gebruiksrechten":
            return Gebruiksrechten(json_response)
        elif object_type == "oio":
            return ObjectInformatieObject(json_response)

    def get_content_object(
        self, drc_uuid: Union[str, UUID], object_type: str
    ) -> CMISContentObject:
        """Get the gebruiksrechten/oio with specified uuid

        :param drc_uuid: string or UUID, the value of drc:oio__uuid or drc:gebruiksrechten__uuid
        :param object_type: string, either "gebruiksrechten" or "oio"
        :return: Either a Gebruiksrechten or ObjectInformatieObject
        """

        assert object_type in [
            "gebruiksrechten",
            "oio",
        ], "'object_type' can be only 'gebruiksrechten' or 'oio'"

        query = CMISQuery("SELECT * FROM drc:%s WHERE drc:%s__uuid = '%s'")

        data = {
            "cmisaction": "query",
            "statement": query(object_type, object_type, str(drc_uuid)),
        }
        logger.debug("CMIS_ADAPTER: get_content_object: request data: %s", data)

        json_response = self.post_request(self.base_url, data)
        logger.debug(
            "CMIS_ADAPTER: get_content_object: response data: %s", json_response
        )

        try:
            return self.get_first_result(
                json_response, self.get_return_type(object_type)
            )
        except GetFirstException:
            object_title = object_type.capitalize()
            error_string = f"{object_title} met uuid {drc_uuid} bestaat niet in het CMIS connection"
            raise DocumentDoesNotExistError(error_string)

    def create_document(
        self,
        identification: str,
        bronorganisatie: str,
        data: dict,
        content: BytesIO = None,
        check_if_already_exists: bool = True,
    ) -> Document:
        """Create a cmis document.

        :param identification: string, A unique identifier for the document.
        :param bronorganisatie: string, The identifier of the organisation.
        :param data: dict, A dict with all the data that needs to be saved on the document.
        :param content: BytesIO, The content of the document.
        :return: document
        """
        if identification and bronorganisatie:
            self.check_document_exists(identification, bronorganisatie)

        data.setdefault("versie", 1)
        data.setdefault(
            "object_type_id",
            f"{self.get_object_type_id_prefix('document')}drc:document",
        )
        data["bronorganisatie"] = bronorganisatie
        data["identificatie"] = identification

        if content is None:
            content = BytesIO()

        # Create Document in default folder
        other_folder = self.get_or_create_other_folder()

        properties = Document.build_properties(data, new=True)

        json_data = create_json_request_body(other_folder, properties)
        logger.debug("CMIS_ADAPTER: create_document: request data: %s", json_data)

        json_response = self.post_request(self.root_folder_url, data=json_data)
        logger.debug("CMIS_ADAPTER: create_document: response data: %s", json_response)
        cmis_doc = Document(json_response)
        content.seek(0)
        return cmis_doc.set_content_stream(content, filename=data.get("bestandsnaam"))

    def lock_document(self, drc_uuid: str, lock: str):
        """
        Check out the CMIS document and store the lock value for check in/unlock.
        """
        cmis_doc = self.get_document(drc_uuid)

        already_locked = DocumentLockedException(
            "Document was already checked out", code="double_lock"
        )

        try:
            pwc = cmis_doc.checkout()
        except CmisInvalidArgumentException:
            raise already_locked

        if pwc.lock:
            raise already_locked

        try:
            # store the lock value on the PWC so we can compare it later
            pwc.update_properties({mapper("lock"): lock})
        except CmisUpdateConflictException as exc:
            raise already_locked from exc

    def unlock_document(
        self, drc_uuid: str, lock: str, force: bool = False
    ) -> Document:
        """Unlock a document with objectId workspace://SpacesStore/<uuid>"""
        cmis_doc = self.get_document(drc_uuid)
        pwc = cmis_doc.get_private_working_copy()

        # If bestandsomvang is explicitly defined, but does not match the actual size
        # of the content, that means that the upload has not been completed yet ->
        # the document cannot be unlocked yet
        if (
            not force
            and pwc.bestandsomvang
            and pwc.bestandsomvang != pwc.contentStreamLength
        ):
            raise DocumentSizeMismatchException(
                "`Document.bestandsomvang` does not match the actual size of the uploaded document."
            )

        if constant_time_compare(pwc.lock, lock) or force:
            pwc.update_properties({mapper("lock"): ""})
            new_doc = pwc.checkin("Updated via Documenten API")
            return new_doc

        raise LockDidNotMatchException("Lock did not match", code="unlock-failed")

    def get_document(
        self, drc_uuid: Optional[str], via_identification=None, filters=None
    ):
        """
        Given a cmis document instance.

        :param drc_uuid: str, the drc:document__uuid
        :return: :class:`AtomPubDocument` object, the latest version of this document
        """
        assert (
            not via_identification
        ), "Support for 'via_identification' is being dropped"

        error_string = f"Document met drc:document__uuid {drc_uuid} bestaat niet in het CMIS connection"
        does_not_exist = DocumentDoesNotExistError(error_string)

        # shortcut - no reason in going over the wire
        if uuid is None:
            raise does_not_exist

        # this always selects the latest version, and if there is a pwc, also the pwc is returned
        query = CMISQuery(
            "SELECT * FROM drc:document WHERE drc:document__uuid = '%s' %s"
        )

        filter_string = build_query_filters(
            filters, filter_string="AND ", strip_end=True
        )
        data = {
            "cmisaction": "query",
            "statement": query(drc_uuid, filter_string),
        }
        logger.debug("CMIS_ADAPTER: get_document: request data: %s", data)
        json_response = self.post_request(self.base_url, data)
        logger.debug("CMIS_ADAPTER: get_document: response data: %s", json_response)

        return extract_latest_version(self.document_type, json_response.get("results"))

    def check_document_exists(
        self, identification: Union[str, UUID], bronorganisatie: str
    ):
        """Check if a document with the same (identificatie, bronorganisatie) already exists in the repository"""

        cmis_identificatie = mapper("identificatie", type="document")
        cmis_bronorganisatie = mapper("bronorganisatie", type="document")

        query = CMISQuery(
            f"SELECT * FROM drc:document WHERE {cmis_identificatie} = '%s' AND {cmis_bronorganisatie} = '%s'"
        )

        data = {
            "cmisaction": "query",
            "statement": query(str(identification), bronorganisatie),
        }
        logger.debug("CMIS_ADAPTER: check_document_exists: request data: %s", data)
        json_response = self.post_request(self.base_url, data)
        logger.debug(
            "CMIS_ADAPTER: check_document_exists: response data: %s", json_response
        )
        if json_response["numItems"] > 0:
            raise DocumentExistsError(
                "Een document met dezelfde identificatie en bronorganisatie al bestaat."
            )
