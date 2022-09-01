import logging
import mimetypes
import re
import uuid
from datetime import timedelta
from io import BytesIO
from typing import List, Optional, Tuple
from xml.dom import minidom

from django.utils import timezone

from cmislib.util import parsePropValue

from drc_cmis.models import UrlMapping
from drc_cmis.utils.utils import get_random_string

logger = logging.getLogger(__name__)


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
            if node_name == "objects" or node_name == "parents":
                if len(child_node.getElementsByTagName("objects")) > 0:
                    for object_nodes in child_node.childNodes:
                        if len(object_nodes.getElementsByTagName("ns2:properties")) > 0:
                            extracted_properties = extract_properties(object_nodes)
                            all_objects.append({"properties": extracted_properties})
                elif len(child_node.getElementsByTagName("ns2:properties")) > 0:
                    extracted_properties = extract_properties(child_node)
                    all_objects.append({"properties": extracted_properties})

    return all_objects


def extract_repository_ids_from_xml(xml_data: str) -> List:
    parsed_xml = minidom.parseString(xml_data)

    repository_id_nodes = parsed_xml.getElementsByTagName("repositoryId")
    return [node.firstChild.nodeValue for node in repository_id_nodes]


def extract_repo_info_from_xml(xml_data: str) -> dict:
    parsed_xml = minidom.parseString(xml_data)

    properties = {}

    for info_node in parsed_xml.getElementsByTagName("repositoryInfo"):
        for property_node in info_node.childNodes:
            property_name = property_node.nodeName.lstrip("ns2:")
            property_value = property_node.firstChild.nodeValue
            if property_value is not None:
                properties[property_name] = property_value

    folder_id_node = parsed_xml.getElementsByTagName("ns2:rootFolderId")[0]
    properties["root_folder_id"] = folder_id_node.firstChild.nodeValue

    return properties


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
def extract_content(soap_response_body: bytes) -> BytesIO:
    match = re.search(
        "Content-Disposition: attachment;.+?\r\n\r\n(.+?)\r\n--uuid:.+?--".encode(
            "utf-8"
        ),
        soap_response_body,
        re.DOTALL,
    )
    content = match.group(1) if match else b""
    return BytesIO(content)


def make_soap_envelope(
    cmis_action: str,
    auth: Tuple[str, str],
    repository_id: Optional[str] = None,
    properties: Optional[dict] = None,
    statement: Optional[str] = None,
    object_id: Optional[str] = None,
    folder_id: Optional[str] = None,
    content_id: Optional[str] = None,
    content_filename: Optional[str] = None,
    major: Optional[str] = None,
    checkin_comment: Optional[str] = None,
    source_folder_id: Optional[str] = None,
    target_folder_id: Optional[str] = None,
    continue_on_failure: Optional[str] = None,
) -> minidom.Document:
    """Create SOAP envelope from data provided

    :param cmis_action: string, the cmis action to perform
    :param auth: tuple, (username, password) for the DMS
    :param repository_id: ID of the main repository (e.g. 8ca7d93b-2286-44b7-bfce-487211e6e9af)
    :param properties: dictionary, properties of the object to create/update
    :param statement: str, SQL statement used in query requests
    :param object_id: str, ID of the node on which to act (e.g.
        workspace://SpacesStore/2bdd4f3d-851f-499b-99ec-142b82ce3c0d)
    :param folder_id: str, ID of a folder (e.g. needed when creating documents)
    :param content_id: str, ID of the content of a document (as the content will be a MTOM attachment)
    :param content_filename: str, name of the file that will be a MTOM attachment. Includes files extension.
    :param major: str, true or false whether the document being checked in is a major version
    :param checkin_comment: str, comment when checking in a document
    :param source_folder_id: str, folder objectId from which to copy a document
    :param target_folder_id: str, folder objectId to which to copy a document
    :param continue_on_failure: str, whether to continue deleting after an error in the deleteTree call
    :return: minidom document
    """

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
    security_header = xml_doc.createElement("wsse:Security")
    security_header.setAttribute(
        "xmlns:wsse",
        "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    )
    security_header.setAttribute(
        "xmlns:wsu",
        "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
    )
    security_header_id = uuid.uuid4().hex

    # Username token
    username_token = xml_doc.createElement("wsse:UsernameToken")
    username_token.setAttribute(
        "wsu:Id",
        f"UsernameToken-{security_header_id}",
    )
    username_tag = xml_doc.createElement("wsse:Username")
    username_text = xml_doc.createTextNode(auth[0])
    username_tag.appendChild(username_text)
    username_token.appendChild(username_tag)

    password_tag = xml_doc.createElement("wsse:Password")
    password_tag.setAttribute(
        "Type",
        "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText",
    )
    password_text = xml_doc.createTextNode(auth[1])
    password_tag.appendChild(password_text)
    username_token.appendChild(password_tag)

    security_header.appendChild(username_token)

    header_element.appendChild(security_header)
    entry_element.appendChild(header_element)

    # Time stamp
    time_stamp_tag = xml_doc.createElement("wsu:Timestamp")
    time_stamp_tag.setAttribute(
        "wsu:Id",
        f"TS-{security_header_id}",
    )

    created_tag = xml_doc.createElement("wsu:Created")
    created_text = xml_doc.createTextNode(timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    created_tag.appendChild(created_text)
    time_stamp_tag.appendChild(created_tag)

    expires_tag = xml_doc.createElement("wsu:Expires")
    expires_text = xml_doc.createTextNode(
        (timezone.now() + timedelta(1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    expires_tag.appendChild(expires_text)
    time_stamp_tag.appendChild(expires_tag)

    security_header.appendChild(time_stamp_tag)

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
        for prop_name, prop_dict in properties.items():
            property_element = xml_doc.createElement(f"ns1:{prop_dict['type']}")
            property_element.setAttribute("propertyDefinitionId", prop_name)

            value = prop_dict["value"]
            if value is not None:
                value_element = xml_doc.createElement("ns1:value")
                value_text = xml_doc.createTextNode(value)
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
        filename = content_filename or get_random_string()
        mimetype, _encoding = mimetypes.guess_type(filename)

        content_element = xml_doc.createElement("ns:contentStream")
        mimetype_element = xml_doc.createElement("ns:mimeType")
        mimetype_txt = xml_doc.createTextNode(mimetype or "application/octet-stream")
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

        filename_element = xml_doc.createElement("ns:filename")
        filename_text = xml_doc.createTextNode(filename)
        filename_element.appendChild(filename_text)
        content_element.appendChild(filename_element)

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

    if source_folder_id is not None:
        source_folder_element = xml_doc.createElement("ns:sourceFolderId")
        source_folder_text = xml_doc.createTextNode(source_folder_id)
        source_folder_element.appendChild(source_folder_text)
        action_element.appendChild(source_folder_element)

    if target_folder_id is not None:
        target_folder_element = xml_doc.createElement("ns:targetFolderId")
        target_folder_text = xml_doc.createTextNode(target_folder_id)
        target_folder_element.appendChild(target_folder_text)
        action_element.appendChild(target_folder_element)

    if continue_on_failure is not None:
        continue_element = xml_doc.createElement("ns:continueOnFailure")
        continue_text = xml_doc.createTextNode(continue_on_failure)
        continue_element.appendChild(continue_text)
        action_element.appendChild(continue_element)

    entry_element.appendChild(body_element)

    return xml_doc


def extract_xml_from_soap(soap_response, binary=False):
    soap_envelope_start = "<soap:Envelope"
    soap_envelope_end = "</soap:Envelope>"
    if binary:
        soap_envelope_start = soap_envelope_start.encode("UTF-8")
        soap_envelope_end = soap_envelope_end.encode("UTF-8")

    begin_xml = soap_response.find(soap_envelope_start)
    end_xml = soap_response.find(soap_envelope_end) + len(soap_envelope_end)

    return soap_response[begin_xml:end_xml]


def pretty_xml(xml_envelope: str) -> str:
    dom = minidom.parseString(xml_envelope)
    return dom.toprettyxml()


class NoURLMappingException(Exception):
    pass


class URLTooLongException(Exception):
    pass


def shrink_url(long_url: str) -> str:
    """Replace patterns in the long URL with the shorter one in the mapping"""
    matching_pattern = find_matching_pattern(long_url, "long_pattern")
    mapping = UrlMapping.objects.get(long_pattern=matching_pattern)

    short_url = long_url.replace(mapping.long_pattern, mapping.short_pattern)

    if len(short_url) > 100:
        raise URLTooLongException

    return long_url.replace(mapping.long_pattern, mapping.short_pattern)


def expand_url(short_url: str) -> str:
    """Replace patterns in the short URL with the longer one in the mapping"""

    matching_pattern = find_matching_pattern(short_url, "short_pattern")
    mapping = UrlMapping.objects.get(short_pattern=matching_pattern)

    return short_url.replace(mapping.short_pattern, mapping.long_pattern)


def find_matching_pattern(url: str, field: str = None) -> str:
    from drc_cmis.models import CMISConfig

    if field is None:
        field = "long_pattern"

    config = CMISConfig.get_solo()

    patterns = config.urlmapping_set.values_list(field, flat=True)

    matching_patterns = []
    for pattern in patterns:
        if pattern in url:
            matching_patterns.append(pattern)

    if len(matching_patterns) == 0:
        raise NoURLMappingException
    elif len(matching_patterns) > 1:
        return sorted(matching_patterns, key=len, reverse=True)[0]
    else:
        return matching_patterns[0]
