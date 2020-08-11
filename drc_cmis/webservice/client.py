import datetime
import uuid
from io import BytesIO
from typing import List, Optional, Union
from uuid import UUID

from django.utils.crypto import constant_time_compare

from cmislib.domain import CmisId
from cmislib.exceptions import UpdateConflictException

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
    LockDidNotMatchException,
)
from drc_cmis.utils.mapper import mapper, reverse_mapper
from drc_cmis.utils.query import CMISQuery
from drc_cmis.utils.utils import build_query_filters, get_random_string
from drc_cmis.webservice.data_models import (
    EnkelvoudigInformatieObject,
    Gebruiksrechten as GebruiksRechtDoc,
    Oio,
    get_cmis_type,
)
from drc_cmis.webservice.drc_document import (
    Document,
    Folder,
    Gebruiksrechten,
    ObjectInformatieObject,
    ZaakFolder,
    ZaakTypeFolder,
)
from drc_cmis.webservice.request import SOAPCMISRequest
from drc_cmis.webservice.utils import (
    extract_num_items,
    extract_object_properties_from_xml,
    extract_repo_info_from_xml,
    extract_xml_from_soap,
    make_soap_envelope,
)


class SOAPCMISClient(CMISClient, SOAPCMISRequest):
    """CMIS client for Web service binding (CMIS 1.0)"""

    document_type = Document
    gebruiksrechten_type = Gebruiksrechten
    oio_type = ObjectInformatieObject
    folder_type = Folder
    zaakfolder_type = ZaakFolder
    zaaktypefolder_type = ZaakTypeFolder

    @property
    def base_folder(self) -> Folder:
        """Return the base folder"""

        if self._base_folder is None:
            # If no base folder has been specified, all the documents/folders will be created in the root folder
            if self.base_folder_name == "":
                # root_folder_id is in the form workspace://SpacesStore/<uuid>
                self._base_folder = self.get_folder(
                    uuid=self.root_folder_id.split("/")[-1]
                )
            else:
                query = CMISQuery("SELECT * FROM cmis:folder WHERE IN_FOLDER('%s')")

                soap_envelope = make_soap_envelope(
                    auth=(self.user, self.password),
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

    def get_repository_info(self) -> dict:
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            cmis_action="getRepositoryInfo",
        )

        soap_response = self.request(
            "RepositoryService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        return extract_repo_info_from_xml(xml_response)

    @property
    def vendor(self) -> str:
        repo_info = self.get_repository_info()
        return repo_info["vendorName"]

    def query(
        self, return_type_name: str, lhs: List[str], rhs: List[str]
    ) -> List[Union[Document, Gebruiksrechten, ObjectInformatieObject]]:
        """Perform an SQL query in the DMS

        :param return_type_name: string, either Folder, Document, Oio or Gebruiksrechten
        :param lhs: list of strings, with the LHS of the SQL query
        :param rhs: list of strings, with the RHS of the SQL query
        :return: type, either Folder, Document, Oio or Gebruiksrechten
        """
        return_type = self.get_return_type(return_type_name)
        table = return_type.table
        where = (" WHERE " + " AND ".join(lhs)) if lhs else ""
        query = CMISQuery("SELECT * FROM %s%s" % (table, where))

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            statement=query(*rhs),
            cmis_action="query",
        )

        soap_response = self.request(
            "DiscoveryService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
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

    def get_folder(self, uuid: str) -> Folder:
        """Retrieve folder with objectId constructed with the uuid given"""

        query = CMISQuery(
            "SELECT * FROM cmis:folder WHERE cmis:objectId = 'workspace://SpacesStore/%s'"
        )

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            statement=query(uuid),
            cmis_action="query",
        )

        soap_response = self.request(
            "DiscoveryService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        num_items = extract_num_items(xml_response)
        if num_items == 0:
            error_string = f"Folder met objectId 'workspace://SpacesStore/{uuid}' bestaat niet in het CMIS connection"
            does_not_exist = FolderDoesNotExistError(error_string)
            raise does_not_exist

        extracted_data = extract_object_properties_from_xml(xml_response, "query")[0]
        return Folder(extracted_data)

    def copy_document(self, document: Document, destination_folder: Folder) -> Document:
        """Copy document to a folder

        :param document: Document, the document to copy
        :param destination_folder: Folder, the folder in which to place the copied document
        :return: the copied document
        """

        # copy the properties from the source document
        drc_properties = {}
        for property_name, property_details in document.properties.items():
            if (
                "cmis:" not in property_name and property_details["value"] is not None
            ) or property_name == "cmis:objectTypeId":
                drc_properties[
                    reverse_mapper(property_name, type="document")
                ] = property_details["value"]

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
        )

        soap_response = self.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
            attachments=[(content_id, document.get_content_stream())],
        )

        # Creating the document only returns its ID
        xml_response = extract_xml_from_soap(soap_response)
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
        for property_name, property_details in source_object.properties.items():
            if (
                "cmis:" not in property_name and property_details["value"] is not None
            ) or property_name == "cmis:objectTypeId":
                drc_properties[
                    reverse_mapper(property_name, type="gebruiksrechten")
                ] = property_details["value"]

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

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml(),
        )

        # Creating the document only returns its ID
        xml_response = extract_xml_from_soap(soap_response)
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

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]

        return Gebruiksrechten(extracted_data)

    def create_content_object(
        self, data: dict, object_type: str, destination_folder: Folder = None
    ) -> Union[Gebruiksrechten, ObjectInformatieObject]:
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
            now = datetime.datetime.now()
            year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
            month_folder = self.get_or_create_folder(str(now.month), year_folder)
            day_folder = self.get_or_create_folder(str(now.day), month_folder)
            destination_folder = self.get_or_create_folder("Related data", day_folder)

        properties = {}
        for key, value in data.items():
            if mapper(key, type=object_type):
                prop_type = get_cmis_type(data_class, key)
                prop_name = mapper(key, type=object_type)
                if prop_type == "propertyDateTime":
                    if isinstance(value, datetime.datetime) or isinstance(
                        value, datetime.date
                    ):
                        value = value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                properties[prop_name] = {"value": value, "type": prop_type}

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

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            folder_id=destination_folder.objectId,
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
            auth=(self.user, self.password),
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

        return return_type(extracted_data)

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
            auth=(self.user, self.password),
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

    def create_document(
        self, identification: str, data: dict, content: BytesIO = None
    ) -> Document:
        """Create a custom Document (with the EnkelvoudigInformatieObject properties)

        :param identification: string, the document ``identificatie``
        :param data: dict, the properties of the document
        :param content: BytesIO, the content of the document
        :return: Document, the document created
        """

        self.check_document_exists(identification)

        now = datetime.datetime.now()
        data.setdefault("versie", "1")
        data.setdefault(
            "object_type_id",
            f"{self.get_object_type_id_prefix('document')}drc:document",
        )

        content_id = str(uuid.uuid4())
        if content is None:
            content = BytesIO()

        # Create Document in default folder
        year_folder = self.get_or_create_folder(str(now.year), self.base_folder)
        month_folder = self.get_or_create_folder(str(now.month), year_folder)
        day_folder = self.get_or_create_folder(str(now.day), month_folder)

        properties = Document.build_properties(
            data, new=True, identification=identification
        )

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
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
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
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
        """Lock a EnkelvoudigInformatieObject with objectId workspace://SpacesStore/<uuid>

        :param uuid: string, uuid used to create the objectId
        :param lock: string, value of the lock
        """
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
            lock_property = {
                mapper("lock"): {
                    "value": lock,
                    "type": get_cmis_type(EnkelvoudigInformatieObject, "lock"),
                }
            }
            pwc.update_properties(lock_property)
        except CmisUpdateConflictException as exc:
            raise already_locked from exc

    def unlock_document(self, uuid: str, lock: str, force: bool = False) -> Document:
        """Unlock a document with objectId workspace://SpacesStore/<uuid>

        :param uuid: string, uuid used to create the objectId
        :param lock: string, value of the lock
        :param force: bool, whether to force the unlocking
        :return: Document, the unlocked document
        """
        cmis_doc = self.get_document(uuid)
        pwc = cmis_doc.get_private_working_copy()

        if constant_time_compare(pwc.lock, lock) or force:
            lock_property = {
                mapper("lock"): {
                    "value": "",
                    "type": get_cmis_type(EnkelvoudigInformatieObject, "lock"),
                }
            }
            pwc.update_properties(lock_property)
            return pwc.checkin("Updated via Documenten API")

        raise LockDidNotMatchException("Lock did not match", code="unlock-failed")

    def update_document(
        self, uuid: str, lock: str, data: dict, content: Optional[BytesIO] = None
    ) -> Document:
        """Update a Document (with the EnkelvoudigInformatieObject properties)

        :param uuid: string, the uuid that combined with workspace://SpacesStore/<uuid> gives the objectId
        :param lock: string, value of the lock
        :param data: dict, the new properties of the document
        :param content: BytesIO, the new content of the document
        :return: Document, the updated document
        """
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

    def get_document(self, uuid: str, filters: Optional[dict] = None) -> Document:
        """Retrieve a document in the main repository with objectId workspace://SpacesStore/<uuid>

        :param uuid: string, uuid used to create the objectId
        :param filters: dict, filters to find the document
        :return: Document, the first document found
        """
        error_string = f"Document met objectId workspace://SpacesStore/{uuid} bestaat niet in het CMIS connection"
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
            auth=(self.user, self.password),
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
        """Query by identification if a document is in the repository

        :param identification: string, document ``identificatie``
        """
        query = CMISQuery(
            "SELECT * FROM drc:document WHERE drc:document__identificatie = '%s'"
        )

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
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
