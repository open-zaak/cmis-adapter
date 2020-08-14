import datetime
import logging
import mimetypes
import uuid
from datetime import date
from io import BytesIO
from typing import List, Optional, Union

from django.utils import timezone

import pytz

from drc_cmis.utils.mapper import (
    DOCUMENT_MAP,
    GEBRUIKSRECHTEN_MAP,
    OBJECTINFORMATIEOBJECT_MAP,
    ZAAK_MAP,
    ZAAKTYPE_MAP,
    mapper,
)
from drc_cmis.utils.utils import get_random_string

from .request import CMISRequest

logger = logging.getLogger(__name__)


class CMISBaseObject(CMISRequest):
    name_map = None
    type_name = None
    type_class = None

    def __init__(self, data):
        super().__init__()
        self.data = data

        # Convert any timestamps to datetime objects
        properties = data.get("properties", {})
        for prop_name, prop_details in properties.items():
            if prop_details["type"] == "datetime" and prop_details["value"] is not None:
                prop_details["value"] = timezone.make_aware(
                    datetime.datetime.fromtimestamp(int(prop_details["value"]) / 1000),
                    pytz.timezone(self.time_zone),
                )

        self.properties = properties

    def __getattr__(self, name: str):
        try:
            return super(CMISRequest, self).__getattribute__(name)
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
        """Construct property dictionary."""

        props = {}
        for key, value in data.items():
            prop_name = mapper(key, type=cls.type_name)
            if not prop_name:
                logger.debug("No property name found for key '%s'", key)
                continue
            if value is not None:
                if isinstance(value, datetime.date) or isinstance(value, datetime.date):
                    value = value.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                props[prop_name] = str(value)

        return props


class CMISContentObject(CMISBaseObject):
    def delete_object(self):
        """Delete all versions of an object"""
        data = {"objectId": self.objectId, "cmisaction": "delete"}
        json_response = self.post_request(self.root_folder_url, data=data)
        return json_response

    def get_parent_folders(self) -> List["Folder"]:
        """Get the parent folders of an object.

        An object has multiple parent folders if it has been multifiled.
        """
        logger.debug("CMIS: DRC_DOCUMENT: get_object_parents")
        params = {
            "objectId": self.objectId,
            "cmisselector": "parents",
        }

        json_response = self.get_request(self.root_folder_url, params=params)
        return self.get_all_objects(json_response, Folder)

    def move_object(self, target_folder: "Folder"):
        source_folder = self.get_parent_folders()[0]

        data = {
            "objectId": self.objectId,
            "cmisaction": "move",
            "sourceFolderId": source_folder.objectId,
            "targetFolderId": target_folder.objectId,
        }

        logger.debug(f"From: {source_folder.name} To: {target_folder.name}")
        logger.debug(
            f"From: {source_folder.objectTypeId} To: {target_folder.objectTypeId}"
        )
        # invoke the URL
        json_response = self.post_request(self.root_folder_url, data=data)
        self.data = json_response
        self.properties = json_response.get("properties")
        return self


class Document(CMISContentObject):
    table = "drc:document"
    name_map = DOCUMENT_MAP

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

        # For documents that are not new, the uuid shouldn't be written
        props.pop(mapper("uuid"), None)

        if new:
            # increase likelihood of uniqueness of title by appending a random string
            title, suffix = data.get("titel"), get_random_string()
            if title is not None:
                props["cmis:name"] = f"{title}-{suffix}"

            # make sure the identification is set, but _only_ for newly created documents.
            # identificatie is immutable once the document is created
            if identification:
                prop_name = mapper("identificatie")
                props[prop_name] = identification

            # For new documents, the uuid needs to be set
            props[mapper("uuid", type="document")] = str(uuid.uuid4())

        return props

    def checkout(self):
        logger.debug("CMIS: DRC_DOCUMENT: checkout")
        data = {"objectId": self.objectId, "cmisaction": "checkOut"}
        json_response = self.post_request(self.root_folder_url, data=data)
        return Document(json_response)

    def update_properties(self, properties: dict, content: Optional[BytesIO] = None):
        logger.debug("CMIS: DRC_DOCUMENT: update_properties")

        if content is not None:
            self.set_content_stream(content)

        data = {"objectId": self.objectId, "cmisaction": "update"}
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

    def get_private_working_copy(self) -> Union["Document", None]:
        """
        Retrieve the private working copy version of a document.
        """
        logger.debug("Fetching the PWC for the current document (UUID '%s')", self.uuid)

        if self.versionSeriesCheckedOutId is None:
            all_versions = self.get_all_versions()
            for document in all_versions:
                if document.versionLabel == "pwc":
                    return document
        else:
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
        data = {"objectId": self.objectId, "cmisaction": "setContent"}

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
        params = {"objectId": self.objectId, "cmisaction": "content"}
        file_content = self.get_request(self.root_folder_url, params=params)
        return BytesIO(file_content)

    def get_all_versions(self) -> List["Document"]:
        """
        Retrieve all versions for a given document.

        Versions are ordered by most-recent first based on cmis:creationDate. If there
        is a PWC, it shall be the first object.

        http://docs.oasis-open.org/cmis/CMIS/v1.1/errata01/os/CMIS-v1.1-errata01-os-complete.html#x1-3440006
        """

        params = {"objectId": self.objectId, "cmisselector": "versions"}
        all_versions = self.get_request(self.root_folder_url, params=params)
        return [Document(data) for data in all_versions]

    def delete_object(self) -> None:
        """
        Permanently delete the object from the CMIS store, with all its versions.

        By default, all versions should be deleted according to the CMIS standard. If
        the document is currently locked (i.e. there is a private working copy), we need
        to cancel that checkout first.
        """
        pwc = self.get_private_working_copy()
        if pwc is not None:
            cancel_checkout_data = {
                "cmisaction": "cancelCheckout",
                "objectId": pwc.objectId,
            }
            self.post_request(self.root_folder_url, data=cancel_checkout_data)

        return super().delete_object()


class Gebruiksrechten(CMISContentObject):
    table = "drc:gebruiksrechten"
    name_map = GEBRUIKSRECHTEN_MAP
    type_name = "gebruiksrechten"


class ObjectInformatieObject(CMISContentObject):
    table = "drc:oio"
    name_map = OBJECTINFORMATIEOBJECT_MAP
    type_name = "oio"


class Folder(CMISBaseObject):
    table = "cmis:folder"

    def get_children_folders(self):
        logger.debug("CMIS: DRC_DOCUMENT: get_children")
        data = {
            "cmisaction": "query",
            "statement": f"SELECT * FROM cmis:folder WHERE IN_FOLDER('{self.objectId}')",
        }
        json_response = self.post_request(self.base_url, data=data)
        return self.get_all_results(json_response, Folder)

    def delete_tree(self, **kwargs):
        data = {"objectId": self.objectId, "cmisaction": "deleteTree"}
        self.post_request(self.root_folder_url, data=data)


class ZaakTypeFolder(CMISBaseObject):
    table = "drc:zaaktypefolder"
    name_map = ZAAKTYPE_MAP
    type_name = "zaaktype"


class ZaakFolder(CMISBaseObject):
    table = "drc:zaakfolder"
    name_map = ZAAK_MAP
    type_name = "zaak"
