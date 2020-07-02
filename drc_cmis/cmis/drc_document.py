import logging
import mimetypes
from datetime import date
from io import BytesIO
from typing import List

from drc_cmis.client.mapper import (
    CONNECTION_MAP,
    DOCUMENT_MAP,
    GEBRUIKSRECHTEN_MAP,
    OBJECTINFORMATIEOBJECT_MAP,
    REVERSE_CONNECTION_MAP,
    REVERSE_DOCUMENT_MAP,
    mapper,
)
from drc_cmis.client.utils import get_random_string

from .utils import CMISRequest

logger = logging.getLogger(__name__)


class CMISBaseObject(CMISRequest):
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.properties = dict(data.get("properties", {}))

    def reload(self):
        logger.debug("CMIS: DRC_DOCUMENT: reload")
        params = {
            "objectId": self.objectId,
            "cmisselector": "object",
        }

        json_response = self.get_request(self.root_folder_url, params=params)
        self.data = json_response
        self.properties = json_response.get("properties")

    def get_object_parents(self):
        logger.debug("CMIS: DRC_DOCUMENT: get_object_parents")
        params = {
            "objectId": self.objectId,
            "cmisselector": "parents",
        }

        json_response = self.get_request(self.root_folder_url, params=params)
        return self.get_all_objects(json_response, Folder)

    def move(self, sourceFolder, targetFolder):
        data = {
            "objectId": self.objectId,
            "cmisaction": "move",
            "sourceFolderId": sourceFolder.objectId,
            "targetFolderId": targetFolder.objectId,
        }
        logger.debug(f"From: {sourceFolder.name} To: {targetFolder.name}")
        logger.debug(
            f"From: {sourceFolder.objectTypeId} To: {targetFolder.objectTypeId}"
        )
        # invoke the URL
        json_response = self.post_request(self.root_folder_url, data=data)
        self.data = json_response
        self.properties = json_response.get("properties")
        return self


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
        logger.debug(
            "Building CMIS properties, document identification: %s",
            identification or "(not set)",
        )

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

    def checkout(self):
        logger.debug("CMIS: DRC_DOCUMENT: checkout")
        data = {"objectId": self.objectId, "cmisaction": "checkOut"}
        json_response = self.post_request(self.root_folder_url, data=data)
        return Document(json_response)

    def update_properties(self, properties):
        logger.debug("CMIS: DRC_DOCUMENT: update_properties")
        data = {
            "objectId": self.objectId,
            "cmisaction": "update",
        }
        prop_count = 0
        for prop_key, prop_value in properties.items():
            # Skip property because update is not allowed
            if prop_key == "cmis:objectTypeId":
                continue

            if isinstance(prop_value, date):
                prop_value = prop_value.strftime("%Y-%m-%dT%H:%I:%S.000Z")

            data["propertyId[%s]" % prop_count] = prop_key
            data["propertyValue[%s]" % prop_count] = prop_value
            prop_count += 1

        # invoke the URL
        json_response = self.post_request(self.root_folder_url, data=data)
        self.data = json_response
        self.properties = json_response.get("properties")

        return self

    def get_private_working_copy(self) -> "Document":
        """
        Retrieve the private working copy version of a document.
        """
        logger.debug("Fetching the PWC for the current document (UUID '%s')", self.uuid)
        # http://docs.oasis-open.org/cmis/CMIS/v1.1/os/CMIS-v1.1-os.html#x1-5590004
        params = {
            "cmisselector": "object",  # get the object rather than the content
            "objectId": self.versionSeriesCheckedOutId,
        }
        data = self.get_request(self.root_folder_url, params)
        return type(self)(data)

    def checkin(self, checkin_comment, major=True):
        logger.debug("CMIS: DRC_DOCUMENT: checkin")
        props = {
            "objectId": self.objectId,
            "cmisaction": "checkIn",
            "checkinComment": checkin_comment,
            "major": major,
        }

        # invoke the URL
        json_response = self.post_request(self.root_folder_url, props)
        return Document(json_response)

    def set_content_stream(self, content_file):
        logger.debug("CMIS: DRC_DOCUMENT: set_content_stream")
        data = {
            "objectId": self.objectId,
            "cmisaction": "setContent",
        }

        mimetype = None
        # need to determine the mime type
        if not mimetype and hasattr(content_file, "name"):
            mimetype, _encoding = mimetypes.guess_type(content_file.name)

        if not mimetype:
            mimetype = "application/binary"

        files = {self.name: (self.name, content_file, mimetype)}

        json_response = self.post_request(self.root_folder_url, data=data, files=files)
        return Document(json_response)

    def get_content_stream(self) -> BytesIO:
        logger.debug("CMIS: DRC_DOCUMENT: get_content_stream")
        params = {
            "objectId": self.objectId,
            "cmisaction": "content",
        }
        file_content = self.get_request(self.root_folder_url, params=params)
        return BytesIO(file_content)

    @classmethod
    def get_all_versions(cls, document: "Document") -> List["Document"]:
        """
        Retrieve all versions for a given document.

        Versions are ordered by most-recent first based on cmis:creationDate. If there
        is a PWC, it shall be the first object.

        http://docs.oasis-open.org/cmis/CMIS/v1.1/errata01/os/CMIS-v1.1-errata01-os-complete.html#x1-3440006
        """

        params = {"objectId": document.objectId, "cmisselector": "versions"}
        all_versions = document.get_request(document.root_folder_url, params=params)
        return [cls(data) for data in all_versions]

    def destroy(self) -> None:
        """
        Permanently delete the object from the CMIS store, with all its versions.

        By default, all versions should be deleted according to the CMIS standard. If
        the document is currently locked (i.e. there is a private working copy), we need
        to cancel that checkout first.
        """
        if self.isVersionSeriesCheckedOut:
            pwc = self.get_private_working_copy()
            cancel_checkout_data = {
                "cmisaction": "cancelCheckout",
                "objectId": pwc.objectId,
            }
            self.post_request(self.root_folder_url, data=cancel_checkout_data)

        data = {"objectId": self.objectId, "cmisaction": "delete"}
        self.post_request(self.root_folder_url, data=data)


class Gebruiksrechten(CMISBaseObject):
    table = "drc:gebruiksrechten"

    def __getattr__(self, name):
        """
        :param name: Name of the attribute to retrieve
        :type name: string
        :return: the attribute (Note: date times are returned as timestamps)
        """
        convert_string = f"drc:{name}"
        if name in GEBRUIKSRECHTEN_MAP:
            # Properties characteristic only of this Gebruiksrechten type
            convert_string = GEBRUIKSRECHTEN_MAP.get(name)
        else:
            # General alresco properties
            convert_string = f"cmis:{name}"
        return self.properties.get(convert_string, {}).get("value")

    def delete_gebruiksrechten(self):
        data = {"objectId": self.objectId, "cmisaction": "delete"}
        json_response = self.post_request(self.root_folder_url, data=data)
        return json_response


class ObjectInformatieObject(CMISBaseObject):
    table = "drc:oio"

    def __getattr__(self, name):
        """
        :param name: Name of the attribute to retrieve
        :type name: string
        :return: the attribute (Note: date times are returned as timestamps)
        """
        convert_string = f"drc:{name}"
        if name in OBJECTINFORMATIEOBJECT_MAP:
            # Properties characteristic only of this ObjectInformatieObject type
            convert_string = OBJECTINFORMATIEOBJECT_MAP.get(name)
        else:
            # General alresco properties
            convert_string = f"cmis:{name}"
        return self.properties.get(convert_string, {}).get("value")

    def delete_oio(self):
        data = {"objectId": self.objectId, "cmisaction": "delete"}
        json_response = self.post_request(self.root_folder_url, data=data)
        return json_response


class Folder(CMISBaseObject):
    def __getattr__(self, name):
        return self.properties.get(f"cmis:{name}", {}).get("value")

    def get_children(self):
        logger.debug("CMIS: DRC_DOCUMENT: get_children")
        data = {
            "cmisaction": "query",
            "statement": f"SELECT * FROM cmis:folder WHERE IN_FOLDER('{self.objectId}')",
        }
        json_response = self.post_request(self.base_url, data=data)
        return self.get_all_results(json_response, Folder)

    def create_folder(self, name, properties={}, **kwargs):
        logger.debug("CMIS: DRC_DOCUMENT: create_folder")
        data = {
            "objectId": self.objectId,
            "cmisaction": "createFolder",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": name,
        }

        data["propertyId[1]"] = "cmis:objectTypeId"
        if "cmis:objectTypeId" in properties.keys():
            data["propertyValue[1]"] = properties.pop("cmis:objectTypeId")
        else:
            data["propertyValue[1]"] = "cmis:folder"

        prop_count = 2
        for prop, value in properties.items():
            data[f"propertyId[{prop_count}]"] = prop
            data[f"propertyValue[{prop_count}]"] = value
            prop_count += 1

        json_response = self.post_request(self.root_folder_url, data=data)
        return Folder(json_response)

    def create_document(self, name, properties, content_file=None, **kwargs):
        logger.debug("CMIS: DRC_DOCUMENT: create_document")
        data = {
            "objectId": self.objectId,
            "cmisaction": "createDocument",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": name,
        }

        data["propertyId[1]"] = "cmis:objectTypeId"
        if "cmis:objectTypeId" in properties.keys():
            data["propertyValue[1]"] = properties.pop("cmis:objectTypeId")
        else:
            data["propertyValue[1]"] = "drc:document"

        prop_count = 2
        for prop_key, prop_value in properties.items():
            if isinstance(prop_value, date):
                prop_value = prop_value.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            data[f"propertyId[{prop_count}]"] = prop_key
            data[f"propertyValue[{prop_count}]"] = prop_value
            prop_count += 1

        json_response = self.post_request(self.root_folder_url, data=data)
        cmis_doc = Document(json_response)
        return cmis_doc.set_content_stream(content_file)

    def create_gebruiksrechten(self, name, properties):
        data = {
            "objectId": self.objectId,
            "cmisaction": "createDocument",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": name,
        }

        data["propertyId[1]"] = "cmis:objectTypeId"
        if "cmis:objectTypeId" in properties.keys():
            data["propertyValue[1]"] = properties.pop("cmis:objectTypeId")
        else:
            data["propertyValue[1]"] = "D:drc:gebruiksrechten"

        prop_count = 2
        for prop_key, prop_value in properties.items():
            if isinstance(prop_value, date):
                prop_value = prop_value.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            data[f"propertyId[{prop_count}]"] = prop_key
            data[f"propertyValue[{prop_count}]"] = prop_value
            prop_count += 1

        json_response = self.post_request(self.root_folder_url, data=data)
        return Gebruiksrechten(json_response)

    def create_oio(self, name, properties):
        data = {
            "objectId": self.objectId,
            "cmisaction": "createDocument",
            "propertyId[0]": "cmis:name",
            "propertyValue[0]": name,
        }

        data["propertyId[1]"] = "cmis:objectTypeId"
        if "cmis:objectTypeId" in properties.keys():
            data["propertyValue[1]"] = properties.pop("cmis:objectTypeId")
        else:
            data["propertyValue[1]"] = "D:drc:oio"

        prop_count = 2
        for prop_key, prop_value in properties.items():
            if isinstance(prop_value, date):
                prop_value = prop_value.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            data[f"propertyId[{prop_count}]"] = prop_key
            data[f"propertyValue[{prop_count}]"] = prop_value
            prop_count += 1

        json_response = self.post_request(self.root_folder_url, data=data)
        return ObjectInformatieObject(json_response)

    def delete_tree(self, **kwargs):
        data = {"objectId": self.objectId, "cmisaction": "deleteTree"}
        self.post_request(self.root_folder_url, data=data)
