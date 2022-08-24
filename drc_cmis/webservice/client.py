import logging
import re
import uuid
from io import BytesIO
from typing import BinaryIO, List, Optional, Tuple, Union
from uuid import UUID

from django.conf import settings
from django.utils.crypto import constant_time_compare

from cmislib.domain import CmisId

from drc_cmis.client import CMISClient
from drc_cmis.utils.exceptions import (
    CmisRepositoryDoesNotExist,
    CmisRuntimeException,
    CmisUpdateConflictException,
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockedException,
    DocumentNotLockedException,
    DocumentSizeMismatchException,
    FolderDoesNotExistError,
    LockDidNotMatchException,
)
from drc_cmis.utils.mapper import mapper, reverse_mapper
from drc_cmis.utils.query import CMISQuery
from drc_cmis.utils.utils import (
    build_query_filters,
    extract_latest_version,
    get_random_string,
)
from drc_cmis.webservice.data_models import (
    EnkelvoudigInformatieObject,
    Gebruiksrechten as GebruiksRechtDoc,
    Oio,
    QueriableUrl,
    get_cmis_type,
    get_type,
)
from drc_cmis.webservice.drc_document import (
    CMISBaseObject,
    CMISContentObject,
    Document,
    Folder,
    Gebruiksrechten,
    ObjectInformatieObject,
    ZaakFolder,
    ZaakTypeFolder,
)
from drc_cmis.webservice.request import SOAPRequest
from drc_cmis.webservice.utils import (
    extract_object_properties_from_xml,
    extract_repository_ids_from_xml,
    extract_xml_from_soap,
    make_soap_envelope,
    pretty_xml,
    shrink_url,
)

from .fetcher import repo_info_fetcher

logger = logging.getLogger(__name__)


class SOAPCMISClient(CMISClient):
    """CMIS client for Web service binding (CMIS 1.0)"""

    document_type = Document
    gebruiksrechten_type = Gebruiksrechten
    oio_type = ObjectInformatieObject
    folder_type = Folder
    zaakfolder_type = ZaakFolder
    zaaktypefolder_type = ZaakTypeFolder

    _main_repo_id = None
    _repository_info = None
    _request = None

    def request(
        self,
        path: str,
        soap_envelope: str,
        attachments: Optional[List[Tuple[str, BinaryIO]]] = None,
        keep_binary: bool = False,
    ) -> Union[str, bytes]:
        """Make request with MTOM attachment.

        :param path: string, path where to post the request
        :param soap_envelope: string, XML which can contain zero or more references to attachments
        (in the form of `cid:<contentId>`)
        :param attachments: list of tuples, each tuple contains the content ID used in the XML (string) and the I/O
        stream for the attachment.
        :param keep_binary: whether to keep the body of the response as binary or convert it to a string.
        :return: string or bytes, the content of the response
        """
        if not self._request:
            self._request = SOAPRequest(self.base_url)
        return self._request.request(
            path, soap_envelope, attachments=attachments, keep_binary=keep_binary
        )

    @property
    def user(self):
        return self.config.client_user

    @property
    def password(self):
        return self.config.client_password

    @property
    def base_url(self):
        """Return the base URL

        For example, for Alfresco running locally the base URL for SOAP requests is
        http://localhost:8082/alfresco/cmisws
        """
        return self.config.client_url

    @property
    def main_repo_id(self) -> str:
        """Get ID of the CMS main repository"""
        return self.get_main_repo_id()

    def get_main_repo_id(self, cache: bool = True) -> str:
        configured_main_repo_id = self.config.main_repo_id
        if configured_main_repo_id and cache:
            return configured_main_repo_id

        if self._main_repo_id is None:
            # Retrieving the IDs of all repositories in the CMS
            soap_envelope = make_soap_envelope(
                auth=(self.user, self.password), cmis_action="getRepositories"
            )

            logger.debug(soap_envelope.toprettyxml())

            soap_response = self.request(
                "RepositoryService", soap_envelope=soap_envelope.toxml()
            )

            xml_response = extract_xml_from_soap(soap_response)
            logger.debug(pretty_xml(xml_response))

            all_repositories_ids = extract_repository_ids_from_xml(xml_response)

            # If no main repository ID is configured, take the ID of the first repository returned.
            if configured_main_repo_id == "":
                self._main_repo_id = all_repositories_ids[0]
            else:
                if configured_main_repo_id not in all_repositories_ids:
                    raise CmisRepositoryDoesNotExist(
                        "The configured repository ID does not exist."
                    )

                self._main_repo_id = configured_main_repo_id

        return self._main_repo_id

    @property
    def repository_info(self) -> dict:
        if not self._repository_info:
            self._repository_info = self.fetch_repository_info()
        return self._repository_info

    def fetch_repository_info(self) -> dict:
        """Fetch the repository info and cache it"""
        logger.debug("Fetching information for repository %s", self.main_repo_id)
        return repo_info_fetcher.fetch(
            self.main_repo_id, self.base_url, self.user, self.password
        )

    @property
    def root_folder_id(self) -> str:
        """Get the ID of the folder where all folders/documents will be created"""
        return self.repository_info["root_folder_id"]

    @property
    def vendor(self) -> str:
        return self.repository_info["vendorName"]

    def query(
        self, return_type_name: str, lhs: List[str] = None, rhs: List[str] = None
    ) -> List[CMISBaseObject]:
        """Perform an SQL query in the DMS

        :param return_type_name: string, either Folder, Document, Oio or Gebruiksrechten
        :param lhs: list of strings, with the LHS of the SQL query
        :param rhs: list of strings, with the RHS of the SQL query
        :return: type, either Folder, Document, Oio or Gebruiksrechten
        """

        return_type = self.get_return_type(return_type_name)

        processed_rhs = rhs
        # Any query that filters based on URL fields needs to be converted to use the short URL version
        if settings.CMIS_URL_MAPPING_ENABLED and lhs is not None and rhs is not None:
            processed_rhs = []

            # Join all the queries and find which fields are used to filter
            joined_lhs = " ".join(lhs)
            column_names = re.findall(r"([a-z]+?:.+?__[a-z]+)", joined_lhs)

            for index, item_rhs in enumerate(rhs):
                column_name = column_names[index]
                property_name = reverse_mapper(
                    column_name, type=return_type_name.lower()
                )
                if (
                    property_name is not None
                    and get_type(return_type.type_class, property_name) == QueriableUrl
                    and item_rhs != ""
                ):
                    processed_rhs.append(shrink_url(item_rhs))
                else:
                    processed_rhs.append(item_rhs)

        table = return_type.table
        where = (" WHERE " + " AND ".join(lhs)) if lhs else ""
        query = CMISQuery("SELECT * FROM %s%s" % (table, where))
        statement = query(*processed_rhs) if processed_rhs else query()

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            statement=statement,
            cmis_action="query",
        )

        logger.debug(soap_envelope.toprettyxml())

        try:
            soap_response = self.request(
                "DiscoveryService", soap_envelope=soap_envelope.toxml()
            )
        # Corsa raises an error if the query retrieves 0 results
        except CmisRuntimeException as exc:
            if "objectNotFound" in exc.message:
                return []
            else:
                raise exc

        xml_response = extract_xml_from_soap(soap_response)

        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "query")

        return [return_type(cmis_object) for cmis_object in extracted_data]

    def create_folder(self, name: str, parent_id: str, data: dict = None) -> Folder:
        """Create a new folder inside a parent

        :param name: string, name of the new folder to create
        :param parent_id: string, cmis:objectId of the parent folder
        :param data: dict, contains the properties of the folder to create.
            The names of the properties are already converted to cmis names (e.g. drc:zaaktype__url)
        :return: Folder, the created folder
        """

        object_type_id = CmisId("cmis:folder")

        properties = {
            "cmis:objectTypeId": {"value": object_type_id, "type": "propertyId"},
            "cmis:name": {"value": name, "type": "propertyString"},
        }

        if data is not None:
            properties.update(data)

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            folder_id=parent_id,
            properties=properties,
            cmis_action="createFolder",
        )

        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(
            xml_response, "createFolder"
        )[0]

        # Creating a folder only returns the objectId
        folder_id = extracted_data["properties"]["objectId"]["value"]

        return self.get_folder(folder_id)

    def get_folder(self, object_id: str) -> Folder:
        """Retrieve folder with given objectId"""

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=object_id,
            cmis_action="getObject",
        )

        logger.debug(soap_envelope.toprettyxml())

        try:
            soap_response = self.request(
                "ObjectService", soap_envelope=soap_envelope.toxml()
            )
        except CmisRuntimeException as exc:
            if "objectNotFound" in exc.message:
                error_string = f"Folder met objectId '{object_id}' bestaat niet in het CMIS connection"
                raise FolderDoesNotExistError(error_string)
            else:
                raise exc

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]
        return Folder(extracted_data)

    def copy_document(self, document: Document, destination_folder: Folder) -> Document:
        """Copy document to a folder

        :param document: Document, the document to copy
        :param destination_folder: Folder, the folder in which to place the copied document
        :return: the copied document
        """

        # copy the properties from the source document
        drc_properties = {}
        drc_url_properties = {}
        for property_name, property_details in document.properties.items():
            if (
                "cmis:" not in property_name and property_details["value"] is not None
            ) or property_name == "cmis:objectTypeId":
                drc_property_name = reverse_mapper(property_name, type="document")

                # Urls are handled separately, because they are already in the 'short' form
                if (
                    get_type(EnkelvoudigInformatieObject, drc_property_name)
                    == QueriableUrl
                ):
                    drc_url_properties[property_name] = {
                        "value": property_details["value"],
                        "type": "propertyString",
                    }
                else:
                    drc_properties[drc_property_name] = property_details["value"]

        cmis_properties = Document.build_properties(drc_properties, new=False)

        cmis_properties.update(
            **{
                "cmis:objectTypeId": {
                    "value": document.objectTypeId,
                    "type": "propertyId",
                },
                mapper("titel", type="document"): {
                    "value": f"{document.titel} - copy",
                    "type": "propertyString",
                },
                "drc:kopie_van": {
                    "value": document.uuid,
                    "type": "propertyString",
                },  # Keep tack of where this is copied from.
                "drc:document__uuid": {
                    "value": str(uuid.uuid4()),
                    "type": "propertyString",
                },
                **drc_url_properties,
            }
        )

        # Update the cmis:name to make it more unique
        file_name = f"{document.titel}-{get_random_string()}"
        cmis_properties["cmis:name"] = {"value": file_name, "type": "propertyString"}

        # Create copy document
        content_id = str(uuid.uuid4())
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            folder_id=destination_folder.objectId,
            properties=cmis_properties,
            cmis_action="createDocument",
            content_id=content_id,
            content_filename=drc_properties.get("bestandsnaam"),
        )

        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
            attachments=[(content_id, document.get_content_stream())],
        )

        # Creating the document only returns its ID
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(
            xml_response, "createDocument"
        )[0]
        copy_document_id = extracted_data["properties"]["objectId"]["value"]

        return document.get_document(copy_document_id)

    def copy_gebruiksrechten(
        self, source_object: Gebruiksrechten, destination_folder: Folder
    ) -> Gebruiksrechten:
        """Copy a gebruiksrechten to a folder

        :param source_object: Gebruiksrechten, the gebruiksrechten to copy
        :param destination_folder: Folder, the folder in which to place the copied gebruiksrechten
        :return: the copied object
        """

        # copy the properties from the source document
        drc_properties = {}
        drc_url_properties = {}
        for property_name, property_details in source_object.properties.items():
            if (
                "cmis:" not in property_name and property_details["value"] is not None
            ) or property_name == "cmis:objectTypeId":
                drc_property_name = reverse_mapper(
                    property_name, type="gebruiksrechten"
                )

                # Urls are handled separately, because they are already in the 'short' form
                if get_type(GebruiksRechtDoc, drc_property_name) == QueriableUrl:
                    drc_url_properties[property_name] = {
                        "value": property_details["value"],
                        "type": "propertyString",
                    }
                else:
                    drc_properties[drc_property_name] = property_details["value"]

        cmis_properties = Gebruiksrechten.build_properties(drc_properties)

        cmis_properties.update(
            **{
                "cmis:objectTypeId": {
                    "value": source_object.objectTypeId,
                    "type": "propertyId",
                },
                mapper("kopie_van", type="gebruiksrechten"): {
                    "value": source_object.objectId,
                    "type": "propertyString",  # Keep tack of where this is copied from.
                },
                "cmis:name": {"value": get_random_string(), "type": "propertyString"},
                "drc:gebruiksrechten__uuid": {
                    "value": str(uuid.uuid4()),
                    "type": "propertyString",
                },
                **drc_url_properties,
            }
        )

        # Create copy gebruiksrechten
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            folder_id=destination_folder.objectId,
            properties=cmis_properties,
            cmis_action="createDocument",
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
        )

        # Creating the document only returns its ID
        xml_response = extract_xml_from_soap(soap_response)

        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(
            xml_response, "createDocument"
        )[0]
        copy_gebruiksrechten_id = extracted_data["properties"]["objectId"]["value"]

        # Request all the properties of the newly created object
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=copy_gebruiksrechten_id,
            cmis_action="getObject",
        )

        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]

        return Gebruiksrechten(extracted_data)

    def create_content_object(
        self, data: dict, object_type: str, destination_folder: Folder = None
    ) -> CMISContentObject:
        """Create a Gebruiksrechten or a ObjectInformatieObject

        :param data: dict, properties of the object to create
        :param object_type: string, either "gebruiksrechten" or "oio"
        :param destination_folder: Folder, the folder in which to place the object
        :return: Either a Gebruiksrechten or ObjectInformatieObject
        """
        assert object_type in [
            "gebruiksrechten",
            "oio",
        ], "'object_type' can be only 'gebruiksrechten' or 'oio'"

        if object_type == "oio":
            return_type = ObjectInformatieObject
            data_class = Oio
        elif object_type == "gebruiksrechten":
            return_type = Gebruiksrechten
            data_class = GebruiksRechtDoc

        if destination_folder is None:
            other_folder = self.get_or_create_other_folder()
            destination_folder = self.get_or_create_folder("Related data", other_folder)

        properties = return_type.build_properties(data)

        properties.setdefault(
            "cmis:objectTypeId",
            {
                "value": f"{self.get_object_type_id_prefix(object_type)}drc:{object_type}",
                "type": "propertyId",
            },
        )
        properties.setdefault(
            "cmis:name", {"value": get_random_string(), "type": "propertyString"}
        )
        properties.setdefault(
            mapper("uuid", type=object_type),
            {"value": str(uuid.uuid4()), "type": get_cmis_type(data_class, "uuid")},
        )

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            folder_id=destination_folder.objectId,
            properties=properties,
            cmis_action="createDocument",
        )

        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
        )

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(
            xml_response, "createDocument"
        )[0]
        new_object_id = extracted_data["properties"]["objectId"]["value"]

        # Request all the properties of the newly created object
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=new_object_id,
            cmis_action="getObject",
        )

        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]

        return return_type(extracted_data)

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

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            statement=query(object_type, object_type, str(drc_uuid)),
            cmis_action="query",
        )

        logger.debug(soap_envelope.toprettyxml())

        error_string = (
            f"{object_type.capitalize()} {object_type} met identificatie drc:{object_type}__uuid {drc_uuid} "
            f"bestaat niet in het CMIS connection"
        )
        does_not_exist = DocumentDoesNotExistError(error_string)

        try:
            soap_response = self.request(
                "DiscoveryService", soap_envelope=soap_envelope.toxml()
            )
        # Corsa raises an error if the query retrieves 0 results
        except CmisRuntimeException as exc:
            if "objectNotFound" in exc.message:
                raise does_not_exist
            else:
                raise exc

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "query")
        if len(extracted_data) == 0:
            raise does_not_exist

        if object_type == "oio":
            return ObjectInformatieObject(extracted_data[0])
        elif object_type == "gebruiksrechten":
            return Gebruiksrechten(extracted_data[0])

    def create_document(
        self,
        identification: str,
        bronorganisatie: str,
        data: dict,
        content: BytesIO = None,
        check_if_already_exists: bool = True,
    ) -> Document:
        """Create a custom Document (with the EnkelvoudigInformatieObject properties)

        :param identification: string, the document ``identificatie``
        :param bronorganisatie: string, The identifier of the organisation.
        :param data: dict, the properties of the document
        :param content: BytesIO, the content of the document
        :param check_if_already_exists: Bool, whether to check if the document with given identificatie/bronorganisatie
        already exists in the DMS.
        :return: Document, the document created
        """

        if check_if_already_exists and identification and bronorganisatie:
            self.check_document_exists(identification, bronorganisatie)

        data.setdefault("versie", "1")
        data.setdefault(
            "object_type_id",
            f"{self.get_object_type_id_prefix('document')}drc:document",
        )
        data["bronorganisatie"] = bronorganisatie
        data["identificatie"] = identification

        content_id = str(uuid.uuid4())
        if content is None:
            content = BytesIO()

        # Create Document in default folder
        other_folder = self.get_or_create_other_folder()

        properties = Document.build_properties(data, new=True)

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            folder_id=other_folder.objectId,
            properties=properties,
            cmis_action="createDocument",
            content_id=content_id,
            content_filename=data.get("bestandsnaam"),
        )

        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
            attachments=[(content_id, content)],
        )

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        # Creating the document only returns its ID
        extracted_data = extract_object_properties_from_xml(
            xml_response, "createDocument"
        )[0]
        new_document_id = extracted_data["properties"]["objectId"]["value"]

        # Request all the properties of the newly created document
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=new_document_id,
            cmis_action="getObject",
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]

        return Document(extracted_data)

    def lock_document(self, drc_uuid: str, lock: str):
        """Lock a EnkelvoudigInformatieObject with given drc:document__uuid

        :param drc_uuid: string, the value of drc:document__uuid
        :param lock: string, value of the lock
        """
        cmis_doc = self.get_document(drc_uuid)

        already_locked = DocumentLockedException(
            "Document was already checked out", code="double_lock"
        )

        try:
            pwc = cmis_doc.checkout()
            if pwc.lock:
                raise already_locked

            # store the lock value on the PWC so we can compare it later
            lock_property = {
                mapper("lock"): {
                    "value": lock,
                    "type": get_cmis_type(EnkelvoudigInformatieObject, "lock"),
                }
            }
            pwc.update_properties(lock_property)
        except CmisUpdateConflictException as exc:
            raise already_locked from exc

    def unlock_document(
        self, drc_uuid: str, lock: str, force: bool = False
    ) -> Document:
        """Unlock a document with given uuid

        :param drc_uuid: string, the value of drc:document__uuid
        :param lock: string, value of the lock
        :param force: bool, whether to force the unlocking
        :return: Document, the unlocked document
        """
        cmis_doc = self.get_document(drc_uuid)

        if not cmis_doc.isVersionSeriesCheckedOut:
            raise DocumentNotLockedException(
                "Document is not checked out and/or locked."
            )

        # If bestandsomvang is explicitly defined, but does not match the actual size
        # of the content, that means that the upload has not been completed yet ->
        # the document cannot be unlocked yet
        if (
            not force
            and cmis_doc.bestandsomvang
            and cmis_doc.bestandsomvang != cmis_doc.contentStreamLength
        ):
            raise DocumentSizeMismatchException(
                "`Document.bestandsomvang` does not match the actual size of the uploaded document."
            )

        if constant_time_compare(cmis_doc.lock, lock) or force:
            lock_property = {
                mapper("lock"): {
                    "value": "",
                    "type": get_cmis_type(EnkelvoudigInformatieObject, "lock"),
                }
            }
            cmis_doc.update_properties(lock_property)
            return cmis_doc.checkin("Updated via Documenten API")

        raise LockDidNotMatchException("Lock did not match", code="unlock-failed")

    # FIXME filters are useless because uuid is unique
    def get_document(self, drc_uuid: str, filters: Optional[dict] = None) -> Document:
        """Retrieve a document in the main repository with given uuid (drc:document__uuid)

        If the document series is checked out, it returns the private working copy

        :param drc_uuid: string, value of the cmis property drc:document__uuid
        :param filters: dict, filters to find the document
        :return: Document, latest document version
        """
        error_string = f"Document met drc:document__uuid {drc_uuid} bestaat niet in het CMIS connection"
        does_not_exist = DocumentDoesNotExistError(error_string)

        if drc_uuid is None:
            raise does_not_exist

        # This always selects the latest version, and if there is a pwc,
        # Alfresco returns both the pwc and the latest major version, while Corsa only returns the pwc.
        query = CMISQuery(
            "SELECT * FROM drc:document WHERE drc:document__uuid = '%s' %s"
        )

        filter_string = build_query_filters(
            filters, filter_string="AND ", strip_end=True
        )

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            statement=query(drc_uuid, filter_string),
            cmis_action="query",
        )
        logger.debug(soap_envelope.toprettyxml())

        try:
            soap_response = self.request(
                "DiscoveryService", soap_envelope=soap_envelope.toxml()
            )
        # Corsa raises an error if the query retrieves 0 results
        except CmisRuntimeException as exc:
            if "objectNotFound" in exc.message:
                raise does_not_exist
            else:
                raise exc
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "query")
        return extract_latest_version(self.document_type, extracted_data)

    def check_document_exists(
        self, identification: Union[str, UUID], bronorganisatie: str
    ) -> None:
        """Check if a document with the same (identificatie, bronorganisatie) already exists in the repository

        :param identification: string, document ``identificatie``
        :param bronorganisatie: string, document ``bronorganisatie``
        """
        cmis_identificatie = mapper("identificatie", type="document")
        cmis_bronorganisatie = mapper("bronorganisatie", type="document")

        query = CMISQuery(
            f"SELECT * FROM drc:document WHERE {cmis_identificatie} = '%s' AND {cmis_bronorganisatie} = '%s'"
        )

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            statement=query(str(identification), bronorganisatie),
            cmis_action="query",
        )
        logger.debug(soap_envelope.toprettyxml())

        try:
            soap_response = self.request(
                "DiscoveryService", soap_envelope=soap_envelope.toxml()
            )
        except CmisRuntimeException as exc:
            # Corsa raises an error if the query gives no results, while Alfresco a 200
            if "objectNotFound" in exc.message:
                return
            else:
                raise exc

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "query")

        if len(extracted_data) > 0:
            raise DocumentExistsError(
                "Een document met dezelfde identificatie en bronorganisatie al bestaat."
            )
