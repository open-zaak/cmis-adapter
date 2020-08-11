import datetime
import logging
import uuid
from io import BytesIO
from typing import List, Optional, Union

from drc_cmis.utils.exceptions import CmisRuntimeException
from drc_cmis.utils.mapper import (
    DOCUMENT_MAP,
    GEBRUIKSRECHTEN_MAP,
    OBJECTINFORMATIEOBJECT_MAP,
    ZAAK_MAP,
    ZAAKTYPE_MAP,
    mapper,
)
from drc_cmis.utils.query import CMISQuery
from drc_cmis.utils.utils import get_random_string
from drc_cmis.webservice.data_models import (
    EnkelvoudigInformatieObject,
    Gebruiksrechten as GebruiksrechtenDoc,
    ZaakFolderData,
    ZaakTypeFolderData,
    get_cmis_type,
)
from drc_cmis.webservice.request import SOAPCMISRequest
from drc_cmis.webservice.utils import (
    extract_content,
    extract_num_items,
    extract_object_properties_from_xml,
    extract_xml_from_soap,
    make_soap_envelope,
)

logger = logging.getLogger(__name__)


class CMISBaseObject(SOAPCMISRequest):
    name_map = None
    type_name = None
    type_class = None

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.properties = dict(data.get("properties", {}))

    def __getattr__(self, name: str):
        try:
            return super(SOAPCMISRequest, self).__getattribute__(name)
        except AttributeError:
            pass

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

        props = {}
        for key, value in data.items():
            prop_name = mapper(key, type=cls.type_name)
            if not prop_name:
                logger.debug("No property name found for key '%s'", key)
                continue
            if value is not None:
                prop_type = get_cmis_type(cls.type_class, key)
                if isinstance(value, datetime.date) or isinstance(value, datetime.date):
                    value = value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                props[prop_name] = {"value": str(value), "type": prop_type}

        return props


class CMISContentObject(CMISBaseObject):
    def delete_object(self):
        """Delete all versions of an object"""

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=self.objectId,
            cmis_action="deleteObject",
        )

        self.request("ObjectService", soap_envelope=soap_envelope.toxml())

    def get_parent_folders(self) -> List["Folder"]:
        """Get all the parent folders of an object"""

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=self.objectId,
            cmis_action="getObjectParents",
        )

        soap_response = self.request(
            "NavigationService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)

        extracted_data = extract_object_properties_from_xml(
            xml_response, "getObjectParents"
        )
        return [Folder(data) for data in extracted_data]

    def move_object(self, target_folder: "Folder") -> "CMISContentObject":
        """Move a document to the specified folder"""

        source_folder = self.get_parent_folders()[0]

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=self.objectId,
            target_folder_id=target_folder.objectId,
            source_folder_id=source_folder.objectId,
            cmis_action="moveObject",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(xml_response, "moveObject")[
            0
        ]

        return type(self)(extracted_data)


class Document(CMISContentObject):
    table = "drc:document"
    name_map = DOCUMENT_MAP
    type_name = "document"

    @classmethod
    def build_properties(
        cls, data: dict, new: bool = True, identification: str = ""
    ) -> dict:
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

        props = {}
        for key, value in data.items():
            prop_name = mapper(key, type="document")
            if not prop_name:
                logger.debug("No property name found for key '%s'", key)
                continue
            if value is not None:
                prop_type = get_cmis_type(EnkelvoudigInformatieObject, key)
                if isinstance(value, datetime.date) or isinstance(value, datetime.date):
                    value = value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                elif isinstance(value, bool):
                    value = str(value).lower()
                props[prop_name] = {"value": str(value), "type": prop_type}
            # When a Gebruiksrechten object is deleted, the field in the Document needs to be None.
            elif key == "indicatie_gebruiksrecht":
                prop_type = get_cmis_type(EnkelvoudigInformatieObject, key)
                props[prop_name] = {"value": "", "type": prop_type}

        if new:
            # increase likelihood of uniqueness of title by appending a random string
            title, suffix = data.get("titel"), get_random_string()
            if title is not None:
                props["cmis:name"] = {
                    "value": f"{title}-{suffix}",
                    "type": get_cmis_type(EnkelvoudigInformatieObject, "name"),
                }

            # make sure the identification is set, but _only_ for newly created documents.
            # identificatie is immutable once the document is created
            if identification:
                prop_name = mapper("identificatie")
                prop_type = get_cmis_type(EnkelvoudigInformatieObject, "identificatie")
                props[prop_name] = {"value": str(identification), "type": prop_type}

        # can't or shouldn't be written
        props.pop(mapper("uuid"), None)

        return props

    def get_document(self, object_id: str) -> "Document":
        """Get latest version of a document with specified objectId

        :param object_id: string, objectId of the document
        :return: Document
        """
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=object_id,
            cmis_action="getObject",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(xml_response, "getObject")[
            0
        ]

        return type(self)(extracted_data)

    def checkout(self) -> "Document":
        """Checkout a private working copy of the document"""

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            cmis_action="checkOut",
            object_id=str(self.objectId),
        )

        # FIXME temporary solution due to alfresco raising a 500 AFTER locking the document
        try:
            soap_response = self.request(
                "VersioningService", soap_envelope=soap_envelope.toxml()
            )
            xml_response = extract_xml_from_soap(soap_response)
            extracted_data = extract_object_properties_from_xml(
                xml_response, "checkOut"
            )[0]
            pwc_id = extracted_data["properties"]["objectId"]["value"]
        except CmisRuntimeException:
            pwc_document = self.get_private_working_copy()
            pwc_id = pwc_document.objectId

        return self.get_document(pwc_id)

    def checkin(self, checkin_comment: str, major: bool = True) -> "Document":
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            cmis_action="checkIn",
            object_id=str(self.objectId),
            major=str(major).lower(),
            checkin_comment=checkin_comment,
        )

        soap_response = self.request(
            "VersioningService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(xml_response, "checkIn")[0]
        doc_id = extracted_data["properties"]["objectId"]["value"]

        return self.get_document(doc_id)

    def get_all_versions(self) -> List["Document"]:
        object_id = self.objectId.split(";")[0]
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            cmis_action="getAllVersions",
            object_id=object_id,
        )
        soap_response = self.request(
            "VersioningService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
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

    def update_properties(
        self, properties: dict, content: Optional[BytesIO] = None
    ) -> "Document":
        # Check if the content of the document needs updating
        if content is not None:
            self.set_content_stream(content)

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            properties=properties,
            cmis_action="updateProperties",
            object_id=self.objectId,
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml(),
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(
            xml_response, "updateProperties"
        )[0]
        return self.get_document(extracted_data["properties"]["objectId"]["value"])

    def get_content_stream(self) -> BytesIO:
        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=self.objectId,
            cmis_action="getContentStream",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        # FIXME find a better way to do this
        return extract_content(soap_response)

    def set_content_stream(self, content: BytesIO):
        content_id = str(uuid.uuid4())
        attachments = [(content_id, content)]

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            object_id=self.objectId,
            cmis_action="setContentStream",
            content_id=content_id,
        )

        self.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
            attachments=attachments,
        )

    def delete_object(self):
        """
        Permanently delete the object from the CMIS store, with all its versions.

        By default, all versions should be deleted according to the CMIS standard. If
        the document is currently locked (i.e. there is a private working copy), we need
        to cancel that checkout first.
        """
        pwc = self.get_private_working_copy()
        if pwc is not None:
            soap_envelope = make_soap_envelope(
                auth=(self.user, self.password),
                repository_id=self.main_repo_id,
                object_id=pwc.objectId,
                cmis_action="cancelCheckOut",
            )

            self.request(
                "VersioningService", soap_envelope=soap_envelope.toxml(),
            )

        return super().delete_object()


class Gebruiksrechten(CMISContentObject):
    table = "drc:gebruiksrechten"
    name_map = GEBRUIKSRECHTEN_MAP
    type_name = "gebruiksrechten"
    type_class = GebruiksrechtenDoc


class ObjectInformatieObject(CMISContentObject):
    table = "drc:oio"
    name_map = OBJECTINFORMATIEOBJECT_MAP


class Folder(CMISBaseObject):
    table = "cmis:folder"

    def get_children_folders(self) -> List:
        """Get all the folders in the current folder"""

        query = CMISQuery("SELECT * FROM cmis:folder WHERE IN_FOLDER('%s')")

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            statement=query(str(self.objectId)),
            cmis_action="query",
        )

        soap_response = self.request(
            "DiscoveryService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        num_items = extract_num_items(xml_response)
        if num_items == 0:
            return []

        extracted_data = extract_object_properties_from_xml(xml_response, "query")
        return [type(self)(folder) for folder in extracted_data]

    def delete_tree(self):
        """Delete the folder and all its contents"""

        soap_envelope = make_soap_envelope(
            auth=(self.user, self.password),
            repository_id=self.main_repo_id,
            folder_id=self.objectId,
            cmis_action="deleteTree",
        )

        self.request("ObjectService", soap_envelope=soap_envelope.toxml())


class ZaakTypeFolder(CMISBaseObject):
    table = "drc:zaaktypefolder"
    name_map = ZAAKTYPE_MAP
    type_name = "zaaktype"
    type_class = ZaakTypeFolderData


class ZaakFolder(CMISBaseObject):
    table = "drc:zaakfolder"
    name_map = ZAAK_MAP
    type_name = "zaak"
    type_class = ZaakFolderData
