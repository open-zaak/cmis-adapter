import datetime

from drc_cmis.browser.drc_document import Folder


def create_json_request_body(target_folder: Folder, properties: dict) -> dict:
    """Create the body of the JSON request from the target folder and the document properties

    The target properties are already converted to CMIS names.
    """
    data = {
        "objectId": target_folder.objectId,
        "cmisaction": "createDocument",
        "propertyId[0]": "cmis:name",
        "propertyValue[0]": properties.pop("cmis:name"),
    }

    data["propertyId[1]"] = "cmis:objectTypeId"
    if "cmis:objectTypeId" in properties.keys():
        data["propertyValue[1]"] = properties.pop("cmis:objectTypeId")
    else:
        data["propertyValue[1]"] = "drc:document"

    prop_count = 2
    for prop_key, prop_value in properties.items():
        if isinstance(prop_value, datetime.date) or isinstance(
            prop_value, datetime.datetime
        ):
            prop_value = prop_value.strftime("%Y-%m-%dT%H:%M:%S")

        data[f"propertyId[{prop_count}]"] = prop_key
        data[f"propertyValue[{prop_count}]"] = prop_value
        prop_count += 1

    return data
