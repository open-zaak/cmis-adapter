import logging
from json.decoder import JSONDecodeError
from typing import BinaryIO, Optional
from xml.dom import minidom

import requests
from cmislib.atompub_binding import CMIS_NS, CMISRA_NS, getElementNameAndValues
from cmislib.util import parsePropValue

from drc_cmis.client.exceptions import (
    CmisBaseException,
    CmisInvalidArgumentException,
    CmisNotSupportedException,
    CmisNoValidResponse,
    CmisObjectNotFoundException,
    CmisPermissionDeniedException,
    CmisRuntimeException,
    CmisUpdateConflictException,
    GetFirstException,
)

logger = logging.getLogger(__name__)


class CMISRequest:
    @property
    def config(self):
        """
        Lazily load the config so that no DB queries are done while Django is starting.
        """
        from drc_cmis.models import CMISConfig

        return CMISConfig.get_solo()

    @property
    def base_url(self):
        return self.config.client_url

    @property
    def root_folder_url(self):
        return f"{self.base_url}/root"

    @property
    def base_folder(self):
        return f"{self.config.base_folder}"

    @property
    def user(self):
        return self.config.client_user

    @property
    def password(self):
        return self.config.client_password

    def get_request(self, url, params=None):
        logger.debug(f"GET: {url} | {params}")
        headers = {"Accept": "application/json"}
        response = requests.get(
            url, params=params, auth=(self.user, self.password), headers=headers
        )
        if not response.ok:
            raise Exception("Error with the query")

        if response.headers.get("Content-Type").startswith("application/json"):
            return response.json()
        return response.content

    def post_request(self, url, data, headers=None, files=None):
        logger.debug(f"POST: {url} | {data}")
        if headers is None:
            headers = {"Accept": "application/json"}
        response = requests.post(
            url,
            data=data,
            auth=(self.user, self.password),
            files=files,
            headers=headers,
        )
        if not response.ok:
            error = response.json()
            if response.status_code == 401:
                raise CmisPermissionDeniedException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 400:
                raise CmisInvalidArgumentException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 404:
                raise CmisObjectNotFoundException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 403:
                raise CmisPermissionDeniedException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 405:
                raise CmisNotSupportedException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 409:
                raise CmisUpdateConflictException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 500:
                raise CmisRuntimeException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            else:
                raise CmisBaseException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )

        try:
            if response.headers.get("Content-Type").startswith("application/json"):
                return response.json()
            else:
                return response.content.decode("UTF-8")
        except JSONDecodeError:
            if not response.text:
                return None
            raise CmisNoValidResponse(
                status=response.status_code,
                url=url,
                message=response.text,
                code="invalid_response",
            )

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


def extract_properties_from_xml(xml_data, cmis_action=None):
    """
    Function adapted from cmislib. It parses a XML response and extracts properties to a dictionary.
    The dictionary has format

    {"properties":
        {"property_name_1": {"value": "property_value_1"}, "property_name_2": {"value": "property_value_2"}}
    }
    so that it is in the same format as when the browser binding is used.
    For each document/folder in the response, a dictionary is created.
    All the dictionaries are then combined to a list.

    :param xml_data: binary XML data
    :return: list of dictionaries with the properties.
    """
    parsed_xml = minidom.parseString(xml_data)

    all_objects = []

    if cmis_action is None:
        for propertiesElement in parsed_xml.getElementsByTagNameNS(
            CMIS_NS, "properties"
        ):
            extracted_properties = {}
            for node in [
                e
                for e in propertiesElement.childNodes
                if e.nodeType == e.ELEMENT_NODE and e.namespaceURI == CMIS_NS
            ]:

                propertyName = node.attributes["propertyDefinitionId"].value
                if (
                    node.childNodes
                    and node.getElementsByTagNameNS(CMIS_NS, "value")[0]
                    and node.getElementsByTagNameNS(CMIS_NS, "value")[0].childNodes
                ):
                    valNodeList = node.getElementsByTagNameNS(CMIS_NS, "value")
                    if len(valNodeList) == 1:
                        propertyValue = parsePropValue(
                            valNodeList[0].childNodes[0].data, node.localName
                        )
                    else:
                        propertyValue = []
                        for valNode in valNodeList:
                            propertyValue.append(
                                parsePropValue(
                                    valNode.childNodes[0].data, node.localName
                                )
                            )
                else:
                    propertyValue = None
                extracted_properties[propertyName] = {"value": propertyValue}

            for node in [
                e
                for e in parsed_xml.childNodes
                if e.nodeType == e.ELEMENT_NODE and e.namespaceURI == CMISRA_NS
            ]:
                propertyName = node.nodeName
                if node.childNodes:
                    propertyValue = node.firstChild.nodeValue
                else:
                    propertyValue = None
                extracted_properties[propertyName] = {"value": propertyValue}

            all_objects.append({"properties": extracted_properties})
    else:
        extracted_properties = {}

        for node in parsed_xml.getElementsByTagName(f"{cmis_action}Response"):
            for child_node in node.childNodes:
                node_name = child_node.nodeName
                if child_node.firstChild is not None:
                    extracted_properties[node_name] = {
                        "value": child_node.firstChild.nodeValue
                    }

        for property_node in parsed_xml.getElementsByTagName("ns2:properties"):
            for child_node in property_node.childNodes:
                try:
                    property_name = child_node.attributes["propertyDefinitionId"].value
                except KeyError:
                    continue

                node_values = child_node.getElementsByTagName("ns2:value")
                if len(node_values) == 0:
                    extracted_properties[property_name] = {"value": None}
                else:
                    extracted_properties[property_name] = {
                        "value": node_values[0].childNodes[0].data
                    }

        all_objects.append({"properties": extracted_properties})

    return all_objects


def extract_repository_id_from_xml(xml_data: str) -> str:
    parsed_xml = minidom.parseString(xml_data)

    repository_id_node = parsed_xml.getElementsByTagName("repositoryId")[0]
    return repository_id_node.firstChild.nodeValue


def extract_root_folder_id_from_xml(xml_data: str) -> str:
    parsed_xml = minidom.parseString(xml_data)

    folder_id_node = parsed_xml.getElementsByTagName("ns2:rootFolderId")[0]
    return folder_id_node.firstChild.nodeValue


def get_xml_doc(
    cmis_action: str,
    repository_id: Optional[str] = None,
    properties: Optional[dict] = None,
    object_id: Optional[str] = None,
    folder_id: Optional[str] = None,
    content_id: Optional[str] = None,
):

    xml_doc = minidom.Document()

    # Main soap entry element
    entry_element = xml_doc.createElement("soapenv:Envelope")
    entry_element.setAttribute(
        "xmlns:soapenv", "http://schemas.xmlsoap.org/soap/envelope/"
    )
    entry_element.setAttribute(
        "xmlns:ns", "http://docs.oasis-open.org/ns/cmis/messaging/200908/"
    )
    entry_element.setAttribute(
        "xmlns:ns1", "http://docs.oasis-open.org/ns/cmis/core/200908/"
    )
    xml_doc.appendChild(entry_element)

    # Creates the security header
    header_element = xml_doc.createElement("soapenv:Header")
    security_header = xml_doc.createElement("Security")
    security_header.setAttribute(
        "xmlns",
        "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    )

    # Time stamp
    time_stamp_tag = xml_doc.createElement("Timestamp")

    created_tag = xml_doc.createElement("Created")
    created_text = xml_doc.createTextNode("2013-07-31T11:11:56Z")
    created_tag.appendChild(created_text)
    time_stamp_tag.appendChild(created_tag)

    expires_tag = xml_doc.createElement("Expires")
    expires_text = xml_doc.createTextNode("2013-08-01T11:11:56Z")
    expires_tag.appendChild(expires_text)
    time_stamp_tag.appendChild(expires_tag)

    security_header.appendChild(time_stamp_tag)

    # Username token
    username_token_tag = xml_doc.createElement("UsernameToken")

    username_tag = xml_doc.createElement("Username")
    username_text = xml_doc.createTextNode("admin")
    username_tag.appendChild(username_text)
    username_token_tag.appendChild(username_tag)

    password_tag = xml_doc.createElement("Password")
    password_text = xml_doc.createTextNode("admin")
    password_tag.appendChild(password_text)
    username_token_tag.appendChild(password_tag)

    security_header.appendChild(username_token_tag)

    header_element.appendChild(security_header)
    entry_element.appendChild(header_element)

    ## Body of the document
    body_element = xml_doc.createElement("soapenv:Body")

    # The name of the next tag is the name of the CMIS action to perform (e.g. createFolder)
    action_element = xml_doc.createElement(f"ns:{cmis_action}")

    # Repository ID
    if repository_id is not None:
        repo_element = xml_doc.createElement("ns:repositoryId")
        repo_text = xml_doc.createTextNode(repository_id)
        repo_element.appendChild(repo_text)
        action_element.appendChild(repo_element)

    # All the properties
    if properties is not None:
        properties_element = xml_doc.createElement("ns:properties")
        for prop_name, prop_value in properties.items():
            prop_type = property_name_type_map.get(prop_name)

            property_element = xml_doc.createElement(prop_type)
            property_element.setAttribute("propertyDefinitionId", prop_name)

            value_element = xml_doc.createElement("ns1:value")
            value_text = xml_doc.createTextNode(prop_value)
            value_element.appendChild(value_text)
            property_element.appendChild(value_element)

            properties_element.appendChild(property_element)
        action_element.appendChild(properties_element)

    body_element.appendChild(action_element)

    # Folder ID
    if folder_id is not None:
        folder_element = xml_doc.createElement("ns:folderId")
        folder_text = xml_doc.createTextNode(folder_id)
        folder_element.appendChild(folder_text)
        action_element.appendChild(folder_element)

    # ObjectId
    if object_id is not None:
        object_id_element = xml_doc.createElement("ns:objectId")
        object_id_text = xml_doc.createTextNode(object_id)
        object_id_element.appendChild(object_id_text)
        action_element.appendChild(object_id_element)

    # File content
    if content_id is not None:
        content_element = xml_doc.createElement("ns:contentStream")
        mimetype_element = xml_doc.createElement("ns:mimeType")
        mimetype_txt = xml_doc.createTextNode("application/octet-stream")
        mimetype_element.appendChild(mimetype_txt)
        content_element.appendChild(mimetype_element)

        stream_element = xml_doc.createElement("ns:stream")
        include_element = xml_doc.createElement("inc:Include")
        include_element.setAttribute(
            "xmlns:inc", "http://www.w3.org/2004/08/xop/include"
        )
        include_element.setAttribute(
            "href", f"cid:{content_id}"
        )
        stream_element.appendChild(include_element)
        content_element.appendChild(stream_element)

        action_element.appendChild(content_element)

    entry_element.appendChild(body_element)

    return xml_doc


def extract_xml_from_soap(soap_response):
    begin_xml = soap_response.find("<soap:Envelope")
    end_xml = soap_response.find("</soap:Envelope>") + len("</soap:Envelope>")

    return soap_response[begin_xml:end_xml]


property_name_type_map = {
    "cmis:contentStreamLength": "ns1:property",
    "cmis:versionLabel": "ns1:propertyDecimal",
    "cmis:objectTypeId": "ns1:propertyId",
    "cmis:name": "ns1:propertyString",
    "drc:document__integriteitwaarde": "ns1:propertyString",
    "drc:document__titel": "ns1:propertyString",
    "drc:document__bestandsnaam": "ns1:propertyString",
    "drc:document__formaat": "ns1:propertyString",
    "drc:document__ondertekeningsoort": "ns1:propertyString",
    "drc:document__beschrijving": "ns1:propertyString",
    "drc:document__identificatie": "ns1:propertyString",
    "drc:document__verzenddatum": "ns1:propertyDateTime",
    "drc:document__taal": "ns1:propertyString",
    "drc:document__indicatiegebruiksrecht": "ns1:propertyString",
    "drc:document__verwijderd": "ns1:propertyBoolean",
    "drc:document__status": "ns1:propertyString",
    "drc:document__ontvangstdatum": "ns1:propertyDateTime",
    "drc:document__informatieobjecttype": "ns1:propertyString",
    "drc:document__auteur": "ns1:propertyString",
    "drc:document__vertrouwelijkaanduiding": "ns1:propertyString",
    "drc:document__integriteitalgoritme": "ns1:propertyString",
    "drc:document__begin_registratie": "ns1:propertyDateTime",
    "drc:document__ondertekeningdatum": "ns1:propertyDateTime",
    "drc:document__bronorganisatie": "ns1:propertyString",
    "drc:document__integriteitdatum": "ns1:propertyDateTime",
    "drc:document__link": "ns1:propertyString",
    "drc:document__creatiedatum": "ns1:propertyDateTime",
    "drc:document__versie": "ns1:propertyDecimal",
    "drc:document__lock": "ns1:propertyString",
}
