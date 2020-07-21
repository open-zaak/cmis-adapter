import logging
from typing import List

from cmislib.domain import CmisId

from client.mapper import (
    DOCUMENT_MAP,
    CONNECTION_MAP,
    REVERSE_CONNECTION_MAP,
    REVERSE_DOCUMENT_MAP,
    mapper,
)
from client.query import CMISQuery
from client.utils import get_random_string
from cmis.soap_request import SOAPCMISRequest
from cmis.utils import (
    get_xml_doc,
    extract_xml_from_soap,
    extract_properties_from_xml,
    extract_folders_from_xml,
    extract_num_items,
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

    def get_private_working_copy(self) -> "Document":
        """Checkout the private working copy of the document"""
        properties = {"objectId": self.versionSeriesCheckedOutId}

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            properties=properties,
            cmis_action="checkOut",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )
        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_properties_from_xml(xml_response, "createFolder")[0]
        return type(self)(extracted_data)

    def update_properties(self, properties: dict) -> "Document":

        properties["objectId"] = self.objectId

        soap_envelope = get_xml_doc(
            repository_id=self.main_repo_id,
            properties=properties,
            cmis_action="updateProperties",
        )

        soap_response = self.request(
            "ObjectService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)
        extracted_data = extract_properties_from_xml(xml_response, "updateProperties")[
            0
        ]
        # TODO this may need re-fetching the updated document
        return type(self)(extracted_data)


class Folder(CMISBaseObject):
    def __getattr__(self, name):
        if name in self.properties:
            return self.properties[name]["value"]

        convert_name = f"cmis:{name}"
        if convert_name in self.properties:
            return self.properties[convert_name]["value"]

        # raise AttributeError(f"No property '{convert_name}'")     #FIXME this may fail silently!

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

        extracted_data = extract_folders_from_xml(xml_response)
        return [type(self)(folder) for folder in extracted_data]
