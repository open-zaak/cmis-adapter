from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from drc_cmis.utils import folder
from drc_cmis.utils.folder import get_folder_structure


def folder_path_validator(
    path: str, path_element_templates: list = None, required: bool = True
):
    allowed_folder_templates = {pet.folder_name for pet in path_element_templates}
    required_folder_names = {
        pet.folder_name for pet in path_element_templates if pet.required
    }
    count = 0

    for pe in get_folder_structure(path):
        count += 1

        if "{{" in pe.folder_name and pe.folder_name not in allowed_folder_templates:
            raise ValidationError(
                "Invalid templated path element: %(value)s",
                params={"value": pe.folder_name},
            )
        if pe.folder_name in required_folder_names:
            required_folder_names -= {pe.folder_name}

    if len(required_folder_names) != 0:
        raise ValidationError(
            "Required path elements are missing: %(value)s",
            params={"value": ", ".join(required_folder_names)},
        )

    if required and count == 0:
        raise ValidationError("At minimum, one folder is required.")


def zaak_folder_path_validator(path: str):
    path_element_templates = [
        folder.YEAR_PATH_ELEMENT_TEMPLATE,
        folder.MONTH_PATH_ELEMENT_TEMPLATE,
        folder.DAY_PATH_ELEMENT_TEMPLATE,
        folder.ZAAKTYPE_PATH_ELEMENT_TEMPLATE,
        folder.ZAAK_PATH_ELEMENT_TEMPLATE,
    ]
    folder_path_validator(path, path_element_templates)


def verzoek_folder_path_validator(path: str):
    path_element_templates = [
        folder.YEAR_PATH_ELEMENT_TEMPLATE,
        folder.MONTH_PATH_ELEMENT_TEMPLATE,
        folder.DAY_PATH_ELEMENT_TEMPLATE,
        folder.VERZOEK_PATH_ELEMENT_TEMPLATE,
    ]
    folder_path_validator(path, path_element_templates)


def other_folder_path_validator(path: str):
    path_element_templates = [
        folder.YEAR_PATH_ELEMENT_TEMPLATE,
        folder.MONTH_PATH_ELEMENT_TEMPLATE,
        folder.DAY_PATH_ELEMENT_TEMPLATE,
    ]
    folder_path_validator(path, path_element_templates)


def url_mapping_validator(pattern: str):
    parsed_url = urlparse(pattern)

    if parsed_url.scheme == "":
        raise ValidationError(
            _("The pattern should start with the protocol (e.g. http:// or https://).")
        )

    if parsed_url.netloc == "":
        raise ValidationError(_("The pattern include a domain name."))
