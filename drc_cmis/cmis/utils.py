import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from json.decoder import JSONDecodeError
from typing import List, Optional
from xml.dom import minidom

import requests
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


def extract_object_properties_from_xml(xml_data: str, cmis_action: str) -> List[dict]:
    """Extract properties returned in a XML SOAP response.

    Function adapted from cmislib. It parses a XML response and extracts properties to a dictionary.
    The dictionary has format

    {"properties":
        {"property_name_1": {"value": "property_value_1"}, "property_name_2": {"value": "property_value_2"}}
    }

    so that it is in the same format as when the browser binding is used.
    For each document/folder in the response, a dictionary is created.
    All the dictionaries are then combined to a list.

    :param xml_data: string, XML data
    :param cmis_action: string, name of the CMIS action that was used in the request, e.g. createDocument
    :return: list of dictionaries with the properties.
    """

    def extract_properties(xml_node: minidom.Element) -> dict:
        """Extract properties in the <ns2:properties> tag of the provided node

        :param xml_node: minidom.Element, parsed XML node
        :return: dict, with the extracted properties.
        """
        properties = {}
        for property_node in xml_node.getElementsByTagName("ns2:properties"):
            for child_node in property_node.childNodes:
                try:
                    property_name = child_node.attributes["propertyDefinitionId"].value
                except KeyError:
                    continue

                node_values = child_node.getElementsByTagName("ns2:value")
                if len(node_values) == 0 or len(node_values[0].childNodes) == 0:
                    properties[property_name] = {"value": None}
                else:
                    properties[property_name] = {
                        "value": parsePropValue(
                            node_values[0].childNodes[0].data, child_node.localName
                        )
                    }
        return properties

    parsed_xml = minidom.parseString(xml_data)

    all_objects = []

    # When creating documents and folders this extracts the objectId
    for action_node in parsed_xml.getElementsByTagName(f"{cmis_action}Response"):
        for child_node in action_node.childNodes:
            node_name = child_node.nodeName

            if node_name == "objectId":
                extracted_properties = {
                    node_name: {"value": child_node.firstChild.nodeValue}
                }
                all_objects.append({"properties": extracted_properties})
            if node_name == "object":
                extracted_properties = extract_properties(child_node)
                all_objects.append({"properties": extracted_properties})
            if node_name == "objects":
                if len(child_node.getElementsByTagName("objects")) > 0:
                    for object_nodes in child_node.childNodes:
                        if len(object_nodes.getElementsByTagName("ns2:properties")) > 0:
                            extracted_properties = extract_properties(object_nodes)
                            all_objects.append({"properties": extracted_properties})
                elif len(child_node.getElementsByTagName("ns2:properties")) > 0:
                    extracted_properties = extract_properties(child_node)
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


def extract_num_items(xml_data: str) -> int:
    """Extract the number of items in the SOAP XML returned by a query"""
    parsed_xml = minidom.parseString(xml_data)
    folder_id_node = parsed_xml.getElementsByTagName("numItems")[0]
    return int(folder_id_node.firstChild.nodeValue)


def extract_content_stream_properties_from_xml(xml_data: str) -> dict:
    parsed_xml = minidom.parseString(xml_data)

    properties = {}
    for content_stream_node in parsed_xml.getElementsByTagName("contentStream"):
        for prop_node in content_stream_node.childNodes:
            if prop_node.nodeName == "stream":
                value = prop_node.firstChild.attributes["href"].nodeValue
            else:
                value = prop_node.firstChild.nodeValue
            properties[prop_node.nodeName] = value

    return properties


# FIXME find a better way to do this
def extract_content(soap_response_body: str) -> BytesIO:
    xml_response = extract_xml_from_soap(soap_response_body)
    extracted_data = extract_content_stream_properties_from_xml(xml_response)

    # After the filename comes the file content
    last_header = (
        f"Content-Disposition: attachment;name=\"{extracted_data['filename']}\""
    )
    idx_content = soap_response_body.find(last_header) + len(last_header)
    content_with_boundary = soap_response_body[idx_content:]
    content = re.search("\r\n\r\n(.+?)\r\n--uuid:.+?--", content_with_boundary).group(1)

    return BytesIO(content.encode())


def make_soap_envelope(
    cmis_action: str,
    repository_id: Optional[str] = None,
    properties: Optional[dict] = None,
    statement: Optional[str] = None,
    object_id: Optional[str] = None,
    folder_id: Optional[str] = None,
    content_id: Optional[str] = None,
    major: Optional[str] = None,
    checkin_comment: Optional[str] = None,
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
    created_text = xml_doc.createTextNode(datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    created_tag.appendChild(created_text)
    time_stamp_tag.appendChild(created_tag)

    expires_tag = xml_doc.createElement("Expires")
    expires_text = xml_doc.createTextNode(
        (datetime.now() + timedelta(1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
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

    # Body of the document
    body_element = xml_doc.createElement("soapenv:Body")

    # The name of the next tag is the name of the CMIS action to perform (e.g. createFolder)
    action_element = xml_doc.createElement(f"ns:{cmis_action}")

    # Repository ID
    if repository_id is not None:
        repo_element = xml_doc.createElement("ns:repositoryId")
        repo_text = xml_doc.createTextNode(str(repository_id))
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

    # For query requests, there is a SQL statement
    if statement is not None:
        query_element = xml_doc.createElement("ns:statement")
        query_text = xml_doc.createTextNode(statement)
        query_element.appendChild(query_text)
        action_element.appendChild(query_element)

    body_element.appendChild(action_element)

    # Folder ID
    if folder_id is not None:
        folder_element = xml_doc.createElement("ns:folderId")
        folder_text = xml_doc.createTextNode(str(folder_id))
        folder_element.appendChild(folder_text)
        action_element.appendChild(folder_element)

    # ObjectId
    if object_id is not None:
        object_id_element = xml_doc.createElement("ns:objectId")
        object_id_text = xml_doc.createTextNode(str(object_id))
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
        include_element.setAttribute("href", f"cid:{content_id}")
        stream_element.appendChild(include_element)
        content_element.appendChild(stream_element)

        action_element.appendChild(content_element)

    if major is not None:
        major_element = xml_doc.createElement("ns:major")
        major_text = xml_doc.createTextNode(major)
        major_element.appendChild(major_text)
        action_element.appendChild(major_element)

    if checkin_comment is not None:
        comment_element = xml_doc.createElement("ns:checkinComment")
        comment_text = xml_doc.createTextNode(checkin_comment)
        comment_element.appendChild(comment_text)
        action_element.appendChild(comment_element)

    entry_element.appendChild(body_element)

    return xml_doc


def extract_xml_from_soap(soap_response):
    begin_xml = soap_response.find("<soap:Envelope")
    end_xml = soap_response.find("</soap:Envelope>") + len("</soap:Envelope>")

    return soap_response[begin_xml:end_xml]


def build_query_filters(
    filters: dict,
    object_type: str = None,
    filter_string: str = "",
    strip_end: bool = False,
):
    """Build filters for SQL query"""
    from drc_cmis.client.mapper import mapper

    if filters:
        for key, value in filters.items():
            if object_type is None:
                if mapper(key):
                    key = mapper(key)
                elif mapper(key, type="connection"):
                    key = mapper(key, type="connection")
                elif mapper(key, type="gebruiksrechten"):
                    key = mapper(key, type="gebruiksrechten")
                elif mapper(key, type="oio"):
                    key = mapper(key, type="oio")
            else:
                key = mapper(key, type=object_type)

            if value and value in ["NULL", "NOT NULL"]:
                filter_string += f"{key} IS {value} AND "
            elif isinstance(value, Decimal):
                filter_string += f"{key} = {value} AND "
            elif isinstance(value, list):
                if len(value) == 0:
                    continue
                filter_string += "( "
                for item in value:
                    sub_filter_string = build_query_filters({key: item}, strip_end=True)
                    filter_string += f"{sub_filter_string} OR "
                filter_string = filter_string[:-3]
                filter_string += " ) AND "
            elif value:
                filter_string += f"{key} = '{value}' AND "

    if strip_end and filter_string[-4:] == "AND ":
        filter_string = filter_string[:-4]

    return filter_string


# FIXME Use the actual mapper
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
    "drc:oio__object_type": "ns1:propertyString",
    "drc:oio__besluit": "ns1:propertyString",
    "drc:oio__zaak": "ns1:propertyString",
    "drc:oio__informatieobject": "ns1:propertyString",
    "drc:gebruiksrechten__einddatum": "ns1:propertyDateTime",
    "drc:gebruiksrechten__omschrijving_voorwaarden": "ns1:propertyString",
    "drc:gebruiksrechten__informatieobject": "ns1:propertyString",
    "drc:gebruiksrechten__startdatum": "ns1:propertyDateTime",
}
