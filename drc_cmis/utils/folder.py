import re
from collections import namedtuple
from typing import List

from django.core.exceptions import ValidationError

PathElement = namedtuple("PathElement", ["folder_name", "object_type"])
PathElementTemplate = namedtuple("PathElementTemplate", ["folder_name", "required"])

YEAR_PATH_ELEMENT_TEMPLATE = PathElementTemplate(
    folder_name="{{ year }}",
    required=False,
)
MONTH_PATH_ELEMENT_TEMPLATE = PathElementTemplate(
    folder_name="{{ month }}",
    required=False,
)
DAY_PATH_ELEMENT_TEMPLATE = PathElementTemplate(
    folder_name="{{ day }}",
    required=False,
)
ZAAKTYPE_PATH_ELEMENT_TEMPLATE = PathElementTemplate(
    folder_name="{{ zaaktype }}",
    required=True,
)
ZAAK_PATH_ELEMENT_TEMPLATE = PathElementTemplate(
    folder_name="{{ zaak }}",
    required=True,
)
VERZOEK_PATH_ELEMENT_TEMPLATE = PathElementTemplate(
    folder_name="{{ verzoek }}",
    required=True,
)


def get_folder_structure(path: str) -> List[PathElement]:
    """Parse a folder path string into path elements.

    A path element example is::

        {
            "folder_name": "Some string",
            "object_type": "cmis:folder"
        }

    :param path: The folder path string
    :return: A `list` of path elements.
    """
    result = []
    folder_pattern = re.compile(r"([^\[]+)(\[[^\]]+\])?")

    for folder in path.strip("/").split("/"):
        if not folder:
            raise ValidationError("Empty path element found. Check for double slashes.")

        folder_match = re.match(folder_pattern, folder).groups()
        if folder_match is None or len(folder_match) != 2:
            raise ValidationError(
                "Invalid path element: %(value)s", params={"value": folder}
            )

        result.append(
            PathElement(
                folder_name=folder_match[0],
                object_type=folder_match[1][1:-1] if folder_match[1] else None,
            )
        )

    return result
