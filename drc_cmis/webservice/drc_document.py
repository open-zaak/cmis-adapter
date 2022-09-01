import datetime
import logging
import uuid
from io import BytesIO
from typing import List, Optional, Union

from django.conf import settings

import pytz
from furl import furl

from drc_cmis.mixins import RearrangeFilesOnDeleteMixin
from drc_cmis.models import CMISConfig
from drc_cmis.utils.exceptions import CmisRuntimeException, DocumentDoesNotExistError
from drc_cmis.utils.mapper import (
    DOCUMENT_MAP,
    GEBRUIKSRECHTEN_MAP,
    OBJECTINFORMATIEOBJECT_MAP,
    ZAAK_MAP,
    ZAAKTYPE_MAP,
    mapper,
)
from drc_cmis.utils.query import CMISQuery
from drc_cmis.utils.utils import extract_latest_version, get_random_string
from drc_cmis.webservice.data_models import (
    EnkelvoudigInformatieObject,
    Folder as _Folder,
    Gebruiksrechten as GebruiksrechtenDoc,
    Oio as OioDoc,
    QueriableUrl,
    ZaakFolderData,
    ZaakTypeFolderData,
    get_cmis_type,
    get_type,
)
from drc_cmis.webservice.utils import (
    expand_url,
    extract_content,
    extract_object_properties_from_xml,
    extract_xml_from_soap,
    make_soap_envelope,
    pretty_xml,
    shrink_url,
)

logger = logging.getLogger(__name__)


class CMISBaseObject:
    name_map = None
    type_name = None
    type_class = None

    def __init__(self, data):
        super().__init__()

        from drc_cmis.webservice.client import SOAPCMISClient

        self.data = data
        self.properties = dict(data.get("properties", {}))
        self.client = SOAPCMISClient()

    def __getattr__(self, name: str):
        def resolve_attribute(name: str) -> str:
            if name in self.properties:
                return self.properties[name]["value"]

            convert_name = f"cmis:{name}"
            if convert_name in self.properties:
                return self.properties[convert_name]["value"]

            convert_name = f"drc:{name}"
            if self.name_map is not None and name in self.name_map:
                convert_name = self.name_map.get(name)

            if convert_name not in self.properties:
                raise AttributeError(f"No property '{convert_name}'")

            return self.properties[convert_name]["value"]

        value = resolve_attribute(name)

        if (
            get_type(self.type_class, name) == QueriableUrl
            and settings.CMIS_URL_MAPPING_ENABLED
            and value is not None
        ):
            return expand_url(value)

        return value

    @classmethod
    def build_properties(cls, data: dict) -> dict:
        """Construct property dictionary.

        The structure of the dictionary is (where ``property_name``, ``property_value``
        and ``property_type`` are the name, value and type of the property):

            .. code-block:: python

                properties = {
                    "property_name": {
                        "value": property_value,
                        "type": property_type,
                    }
                }
        """
        config = CMISConfig.objects.get()

        props = {}
        for key, value in data.items():
            prop_name = mapper(key, type=cls.type_name)
            if not prop_name:
                logger.debug("CMIS_ADAPTER: No property name found for key '%s'", key)
                continue
            if value is not None:
                prop_type = get_cmis_type(cls.type_class, key)

                if (
                    get_type(cls.type_class, key) == QueriableUrl
                    and settings.CMIS_URL_MAPPING_ENABLED
                ):
                    value = shrink_url(value)
                elif isinstance(value, datetime.datetime):
                    value = value.astimezone(pytz.timezone(config.time_zone)).strftime(
                        "%Y-%m-%dT%H:%M:%S.000Z"
                    )
                elif isinstance(value, datetime.date):
                    # In CMIS, there is no propertyDate, only propertyDateTime.
                    # So dates need to be in the datetime format
                    value = value.strftime("%Y-%m-%dT00:00:00.000Z")
                props[prop_name] = {"value": str(value), "type": prop_type}

        return props


class CMISContentObject(CMISBaseObject):
    def delete_object(self):
        """Delete all versions of an object"""

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            object_id=self.objectId,
            cmis_action="deleteObject",
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

    def get_parent_folders(self) -> List["Folder"]:
        """Get all the parent folders of an object"""

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            object_id=self.objectId,
            cmis_action="getObjectParents",
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "NavigationService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(
            xml_response, "getObjectParents"
        )
        return [Folder(data) for data in extracted_data]

    def move_object(self, target_folder: "Folder") -> "CMISContentObject":
        """Move a document to the specified folder"""

        source_folder = self.get_parent_folders()[0]

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            object_id=self.objectId,
            target_folder_id=target_folder.objectId,
            source_folder_id=source_folder.objectId,
            cmis_action="moveObject",
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))
        extracted_data = extract_object_properties_from_xml(xml_response, "moveObject")[
            0
        ]

        return type(self)(extracted_data)

    def _update_properties(self, properties: dict) -> dict:
        """
        Update properties and return the properties of the updated object.

        :param properties: dict, new properties to update
        :return: dict, properties of the updated object
        """
        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            properties=properties,
            cmis_action="updateProperties",
            object_id=self.objectId,
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))
        extracted_data = extract_object_properties_from_xml(
            xml_response, "updateProperties"
        )[0]

        return extracted_data

    def get_content_object(
        self, object_id: str, object_type: type
    ) -> "CMISContentObject":
        """Get a content object with specified objectId

        :param object_id: string, objectId of the content object
        :param object_type: type, type of the object to return
        :return: CMISContentObject
        """
        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            object_id=object_id,
            cmis_action="getObject",
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))
        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]

        return object_type(extracted_data)


class Document(CMISContentObject):
    table = "drc:document"
    name_map = DOCUMENT_MAP
    type_name = "document"
    type_class = EnkelvoudigInformatieObject

    @classmethod
    def build_properties(cls, data: dict, new: bool = True) -> dict:
        """Construct property dictionary.

        The structure of the dictionary is (where ``property_name``, ``property_value``
        and ``property_type`` are the name, value and type of the property):

            .. code-block:: python

                properties = {
                    "property_name": {
                        "value": property_value,
                        "type": property_type,
                    }
                }
        """

        config = CMISConfig.objects.get()

        props = {}
        for key, value in data.items():
            prop_name = mapper(key, type="document")
            if not prop_name:
                logger.debug("CMIS_ADAPTER: No property name found for key '%s'", key)
                continue
            if value is not None:
                prop_type = get_cmis_type(EnkelvoudigInformatieObject, key)

                if (
                    settings.CMIS_URL_MAPPING_ENABLED
                    and get_type(EnkelvoudigInformatieObject, key) == QueriableUrl
                    and value != ""
                ):
                    value = shrink_url(value)
                elif isinstance(value, datetime.datetime):
                    value = value.astimezone(pytz.timezone(config.time_zone)).strftime(
                        "%Y-%m-%dT%H:%M:%S.000Z"
                    )
                elif isinstance(value, datetime.date):
                    # In CMIS, there is no propertyDate, only propertyDateTime.
                    # So dates need to be in the datetime format
                    value = value.strftime("%Y-%m-%dT00:00:00.000Z")
                elif isinstance(value, bool):
                    value = str(value).lower()

                props[prop_name] = {"value": str(value), "type": prop_type}
            # When a Gebruiksrechten object is deleted, the field in the Document needs to be None.
            elif key == "indicatie_gebruiksrecht":
                prop_type = get_cmis_type(EnkelvoudigInformatieObject, key)
                props[prop_name] = {"value": "", "type": prop_type}
            elif key == "bestandsomvang" and value is None:
                prop_type = get_cmis_type(EnkelvoudigInformatieObject, key)
                props[prop_name] = {"value": None, "type": prop_type}

        # For documents that are not new, the uuid shouldn't be written
        props.pop(mapper("uuid"), None)

        if new:
            # increase likelihood of uniqueness of title by appending a random string
            title, suffix = data.get("titel"), get_random_string()
            if title is not None:
                props["cmis:name"] = {
                    "value": f"{title}-{suffix}",
                    "type": get_cmis_type(EnkelvoudigInformatieObject, "name"),
                }

            # For new documents, the uuid needs to be set
            prop_name = mapper("uuid")
            prop_type = get_cmis_type(EnkelvoudigInformatieObject, "uuid")
            new_uuid = str(uuid.uuid4())
            props[prop_name] = {"value": new_uuid, "type": prop_type}

            # The identification needs to be set ONLY for newly created documents.
            # identificatie is immutable once the document is created
            prop_name = mapper("identificatie")
            if not props.get(prop_name, {}).get("value"):
                prop_type = get_cmis_type(EnkelvoudigInformatieObject, "identificatie")
                props[prop_name] = {"value": new_uuid, "type": prop_type}

        return props

    def get_document(self, object_id: str) -> "Document":
        """Get latest version of a document with specified objectId

        The objectId contains the specific version in Alfresco

        :param object_id: string, objectId of the document
        :return: Document
        """
        return self.get_content_object(object_id=object_id, object_type=type(self))

    def checkout(self) -> "Document":
        """Checkout a private working copy of the document"""

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            cmis_action="checkOut",
            object_id=str(self.objectId),
        )
        logger.debug(soap_envelope.toprettyxml())

        # FIXME temporary solution due to alfresco raising a 500 AFTER locking the document
        try:
            soap_response = self.client.request(
                "VersioningService", soap_envelope=soap_envelope.toxml()
            )
            xml_response = extract_xml_from_soap(soap_response)
            logger.debug(pretty_xml(xml_response))
            extracted_data = extract_object_properties_from_xml(
                xml_response, "checkOut"
            )[0]
            pwc_id = extracted_data["properties"]["objectId"]["value"]
        except CmisRuntimeException:
            pwc_document = self.get_latest_version()
            pwc_id = pwc_document.objectId

        return self.get_document(pwc_id)

    def checkin(self, checkin_comment: str, major: bool = True) -> "Document":
        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            cmis_action="checkIn",
            object_id=str(self.objectId),
            major=str(major).lower(),
            checkin_comment=checkin_comment,
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "VersioningService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "checkIn")[0]
        doc_id = extracted_data["properties"]["objectId"]["value"]

        return self.get_document(doc_id)

    def get_all_versions(self) -> List["Document"]:
        object_id = self.objectId.split(";")[0]
        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            cmis_action="getAllVersions",
            object_id=object_id,
        )
        logger.debug(soap_envelope.toprettyxml())
        soap_response = self.client.request(
            "VersioningService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))
        extracted_data = extract_object_properties_from_xml(
            xml_response, "getAllVersions"
        )
        return [Document(data) for data in extracted_data]

    def get_private_working_copy(self) -> Union["Document", None]:
        """Get the version of the document with version label 'pwc'"""
        documents = self.get_all_versions()

        for document in documents:
            if document.versionLabel == "pwc":
                return document

    def update_content(self, content: BytesIO, filename: Optional[str] = None):
        self.set_content_stream(content, filename)

    def update_properties(self, properties: dict) -> "Document":

        updated_properties = self._update_properties(properties)
        return self.get_document(updated_properties["properties"]["objectId"]["value"])

    def get_content_stream(self) -> BytesIO:
        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            object_id=self.objectId,
            cmis_action="getContentStream",
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "ObjectService", soap_envelope=soap_envelope.toxml(), keep_binary=True
        )

        xml_response = extract_xml_from_soap(soap_response, binary=True)
        logger.debug(pretty_xml(xml_response))

        # FIXME find a better way to do this
        return extract_content(soap_response)

    def set_content_stream(self, content: BytesIO, filename: Optional[str] = None):
        content_id = str(uuid.uuid4())
        attachments = [(content_id, content)]

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            object_id=self.objectId,
            cmis_action="setContentStream",
            content_id=content_id,
            content_filename=filename,
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
            attachments=attachments,
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

    def delete_object(self):
        """
        Permanently delete the object from the CMIS store, with all its versions.

        By default, all versions should be deleted according to the CMIS standard. If
        the document is currently locked (i.e. there is a private working copy), we need
        to cancel that checkout first.
        """
        latest_version = self.get_latest_version()

        if latest_version.isVersionSeriesCheckedOut:
            soap_envelope = make_soap_envelope(
                auth=(self.client.user, self.client.password),
                repository_id=self.client.main_repo_id,
                object_id=latest_version.objectId,
                cmis_action="cancelCheckOut",
            )
            logger.debug(soap_envelope.toprettyxml())

            soap_response = self.client.request(
                "VersioningService",
                soap_envelope=soap_envelope.toxml(),
            )
            xml_response = extract_xml_from_soap(soap_response)
            logger.debug(pretty_xml(xml_response))

            refreshed_document = self.get_latest_version()
            return refreshed_document.delete_object()

        return super().delete_object()

    def get_latest_version(self):
        """Get the latest version or the PWC"""

        # This always selects the latest version, and if there is a pwc,
        # Alfresco returns both the pwc and the latest major version, while Corsa only returns the pwc.
        query = CMISQuery("SELECT * FROM drc:document WHERE drc:document__uuid = '%s'")

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            statement=query(self.uuid),
            cmis_action="query",
        )
        logger.debug(soap_envelope.toprettyxml())

        try:
            soap_response = self.client.request(
                "DiscoveryService", soap_envelope=soap_envelope.toxml()
            )
        # Corsa raises an error for queries that return no results
        except CmisRuntimeException as exc:
            if "objectNotFound" in exc.message:
                error_string = f"Object met objectId '{self.objectId}' bestaat niet in het CMIS connection"
                raise DocumentDoesNotExistError(error_string)
            else:
                raise exc
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))
        extracted_data = extract_object_properties_from_xml(xml_response, "query")
        return extract_latest_version(type(self), extracted_data)


class Gebruiksrechten(CMISContentObject):
    table = "drc:gebruiksrechten"
    name_map = GEBRUIKSRECHTEN_MAP
    type_name = "gebruiksrechten"
    type_class = GebruiksrechtenDoc

    def update_properties(self, properties: dict) -> "Gebruiksrechten":
        """
        Update the properties of an existing gebruiksrechten.

        :param properties: dict, the new properties
        :return: Updated gebruiksrechten
        """
        updated_properties = self._update_properties(properties)

        return self.get_content_object(
            object_id=updated_properties["properties"]["objectId"]["value"],
            object_type=type(self),
        )


class ObjectInformatieObject(RearrangeFilesOnDeleteMixin, CMISContentObject):
    table = "drc:oio"
    name_map = OBJECTINFORMATIEOBJECT_MAP
    type_name = "oio"
    type_class = OioDoc

    def _get_related_document(self) -> Optional[Document]:
        """Get the document referred to by the OIO

        This is the document in the Zaak folder that is referred to by the OIO. It can be a copy of the original
        document. This means that we can't just filter the documents on drc:document__uuid, but we also need
        to consider drc:kopie_van
        """
        related_documents = self.zaakfolder.get_children_documents(
            convert_to_document_type=False
        )
        informatieobject_url = furl(self.informatieobject)
        informatieobject_uuid = informatieobject_url.path.segments[-1]

        for document in related_documents:
            if (
                document["properties"]["drc:document__uuid"]["value"]
                == informatieobject_uuid
                or document["properties"]["drc:kopie_van"]["value"]
                == informatieobject_uuid
            ):
                return Document(document)
        else:
            logger.error(
                "Could not find the document %s in zaakfolder %s before deleting the OIO.",
                self.informatieobject,
                self.zaakfolder.name,
            )

    def _get_gebruiksrechten(self) -> Optional["Gebruiksrechten"]:
        gebruiksrechten_files = self.client.query(
            "gebruiksrechten",
            lhs=["drc:gebruiksrechten__informatieobject = '%s'"],
            rhs=[self.informatieobject],
        )
        if gebruiksrechten_files:
            related_data_folder = self.get_parent_folders()[0]

            # The gebruiksrechten file would be in the same folder as the OIO
            for file in gebruiksrechten_files:
                parent_folder = file.get_parent_folders()[0]
                if parent_folder.objectId == related_data_folder.objectId:
                    return file
            else:
                logger.error(
                    "No gebruiksrechten file found in the 'Related data' folder of zaakfolder %s for document %s.",
                    self.zaakfolder.name,
                    self.informatieobject,
                )


class Folder(CMISBaseObject):
    table = "cmis:folder"
    type_name = "folder"
    type_class = _Folder

    def get_children_folders(self, child_type: dict = None) -> List:
        """Get all the folders in the current folder

        :param child_type: dict, With keys "value" and "type". The value contains the object type ID of
        the children folders to retrieve.
        """

        if child_type is not None:
            object_type_id = child_type["value"]
            # Alfresco case: the object type ID has an extra prefix (F:drc:zaakfolder, instead of drc:zaakfolder)
            # The prefix needs to be removed for the query
            if len(object_type_id.split(":")) > 2:
                object_type_id = ":".join(object_type_id.split(":")[1:])
        else:
            object_type_id = "cmis:folder"

        query = CMISQuery(f"SELECT * FROM {object_type_id} WHERE cmis:parentId = '%s'")

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            statement=query(str(self.objectId)),
            cmis_action="query",
        )
        logger.debug(soap_envelope.toprettyxml())

        try:
            soap_response = self.client.request(
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
        return [type(self)(folder) for folder in extracted_data]

    def get_child_folder(
        self, name: str, child_type: dict = None
    ) -> Optional["Folder"]:
        """Get a folder in the current folder that has a specific name

        :param name: str, the cmis:name of the folder to retrieve
        :param child_type: dict, With keys "value" and "type". The value contains the object type ID of
        the children folders to retrieve.
        """
        if child_type is not None:
            object_type_id = child_type["value"]
            # Alfresco case: the object type ID has an extra prefix (F:drc:zaakfolder, instead of drc:zaakfolder)
            # The prefix needs to be removed for the query
            if len(object_type_id.split(":")) > 2:
                object_type_id = ":".join(object_type_id.split(":")[1:])
        else:
            object_type_id = "cmis:folder"

        query = CMISQuery(
            f"SELECT * FROM {object_type_id} WHERE cmis:parentId = '%s' AND cmis:name = '%s'"
        )

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            statement=query(str(self.objectId), name),
            cmis_action="query",
        )
        logger.debug(soap_envelope.toprettyxml())

        try:
            soap_response = self.client.request(
                "DiscoveryService", soap_envelope=soap_envelope.toxml()
            )
        # Corsa raises an error if the query retrieves 0 results
        except CmisRuntimeException as exc:
            if "objectNotFound" in exc.message:
                return None
            else:
                raise exc
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "query")
        if len(extracted_data) == 0:
            return None
        return type(self)(extracted_data[0])

    def delete_tree(self):
        """Delete the folder and all its contents"""

        # With Corsa, locked documents cause an error, so 'continue_on_failure' is needed
        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            folder_id=self.objectId,
            cmis_action="deleteTree",
            continue_on_failure="true",
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

    def get_children_documents(
        self, convert_to_document_type: bool = True
    ) -> List[Union[Document, dict]]:

        soap_envelope = make_soap_envelope(
            auth=(self.client.user, self.client.password),
            repository_id=self.client.main_repo_id,
            cmis_action="getChildren",
            folder_id=self.objectId,
        )
        logger.debug(soap_envelope.toprettyxml())

        soap_response = self.client.request(
            "NavigationService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        logger.debug(pretty_xml(xml_response))

        extracted_data = extract_object_properties_from_xml(xml_response, "getChildren")
        documents = []
        document_objecttype_id = (
            f"{self.client.get_object_type_id_prefix(Document.type_name)}drc:document"
        )
        for object_data in extracted_data:
            if (
                object_data["properties"]["cmis:objectTypeId"]["value"]
                == document_objecttype_id
            ):
                if convert_to_document_type:
                    documents.append(Document(object_data))
                else:
                    documents.append(object_data)

        return documents


class ZaakTypeFolder(Folder):
    table = "drc:zaaktypefolder"
    name_map = ZAAKTYPE_MAP
    type_name = "zaaktype"
    type_class = ZaakTypeFolderData


class ZaakFolder(Folder):
    table = "drc:zaakfolder"
    name_map = ZAAK_MAP
    type_name = "zaak"
    type_class = ZaakFolderData
