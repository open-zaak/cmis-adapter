import logging
import uuid
from io import BytesIO
from typing import List

from drc_cmis.client.mapper import (
    CONNECTION_MAP,
    DOCUMENT_MAP,
    REVERSE_CONNECTION_MAP,
    REVERSE_DOCUMENT_MAP,
    mapper,
)
from drc_cmis.client.query import CMISQuery
from drc_cmis.client.utils import get_random_string
from drc_cmis.cmis.soap_request import SOAPCMISRequest
from drc_cmis.cmis.utils import (
    extract_content,
    extract_num_items,
    extract_object_properties_from_xml,
    extract_xml_from_soap,
    get_xml_doc,
)

logger = logging.getLogger(__name__)


class CMISBaseObject(SOAPCMISRequest):
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.properties = dict(data.get("properties", {}))


class Document(CMISBaseObject):
    table = "drc:document"
    object_type_id = f"D:{table}"

    def __getattr__(self, name: str):
        try:
            return super(SOAPCMISRequest, self).__getattribute__(name)
        except AttributeError:
            pass

        convert_string = f"drc:{name}"
        if name in DOCUMENT_MAP:
            convert_string = DOCUMENT_MAP.get(name)
        elif name in CONNECTION_MAP:
            convert_string = CONNECTION_MAP.get(name)
        elif (
            convert_string not in REVERSE_CONNECTION_MAP
            and convert_string not in REVERSE_DOCUMENT_MAP
        ):
            convert_string = f"cmis:{name}"

        if convert_string not in self.properties:
            raise AttributeError(f"No property '{convert_string}'")

        return self.properties[convert_string]["value"]

    @classmethod
    def build_properties(
        cls, data: dict, new: bool = True, identification: str = ""
    ) -> dict:

        props = {}
        for key, value in data.items():
            prop_name = mapper(key, type="document")
            if not prop_name:
                logger.debug("No property name found for key '%s'", key)
                continue
            props[prop_name] = value

        if new:
            props.setdefault("cmis:objectTypeId", cls.object_type_id)

            # increase likelihood of uniqueness of title by appending a random string
            title, suffix = data.get("titel"), get_random_string()
            if title is not None:
                props["cmis:name"] = f"{title}-{suffix}"

            # make sure the identification is set, but _only_ for newly created documents.
            # identificatie is immutable once the document is created
            if identification:
                prop_name = mapper("identificatie")
                props[prop_name] = identification

        # can't or shouldn't be written
        props.pop(mapper("uuid"), None)

        return props

    def checkout(self) -> "Document":
        """Checkout a private working copy of the document"""

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            cmis_action="checkOut",
            object_id=str(self.objectId),
        )

        soap_response = self.request(
            "VersioningService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(xml_response, "checkOut")[0]
        pwd_id = extracted_data["properties"]["objectId"]["value"]

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id, object_id=pwd_id, cmis_action="getObject",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        # Maybe catch the exception for now and retrieve all the versions, then get the last one?
        extracted_data = extract_object_properties_from_xml(
            xml_response, "getObject")[0]

        return type(self)(extracted_data)

    def update_properties(self, properties: dict) -> "Document":

        properties["objectId"] = self.objectId

        # Check if the content of the document needs updating
        content_id = None
        attachments = None
        if properties.get("inhoud") is not None:
            content_id = str(uuid.uuid4())
            attachments = [(content_id, properties.pop("inhoud"))]

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            properties=properties,
            cmis_action="updateProperties",
            content_id=content_id,
        )

        soap_response = self.request(
            "ObjectService",
            soap_envelope=soap_envelope.toxml(),
            attachments=attachments,
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_object_properties_from_xml(
            xml_response, "updateProperties"
        )[0]
        # TODO this may need re-fetching the updated document
        return type(self)(extracted_data)

    def get_content_stream(self) -> BytesIO:
        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            object_id=self.objectId,
            cmis_action="getContentStream",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        # FIXME find a better way to do this
        return extract_content(soap_response)


class Folder(CMISBaseObject):
    def __getattr__(self, name):
        try:
            return super(SOAPCMISRequest, self).__getattribute__(name)
        except AttributeError:
            pass

        if name in self.properties:
            return self.properties[name]["value"]

        convert_name = f"cmis:{name}"
        if convert_name in self.properties:
            return self.properties[convert_name]["value"]

        raise AttributeError(f"No property '{convert_name}'")

    def get_children_folders(self) -> List:
        """Get all the folders in the current folder"""

        query = CMISQuery(f"SELECT * FROM cmis:folder WHERE IN_FOLDER('%s')")

        soap_envelope = get_xml_doc(
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

    #TODO
    def delete_tree(self):
        pass
