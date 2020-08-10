import json
import os

from django.apps import AppConfig
from django.conf import settings

from drc_cmis.utils import mapper
from drc_cmis.utils.mapper import (
    DOCUMENT_MAP,
    GEBRUIKSRECHTEN_MAP,
    OBJECTINFORMATIEOBJECT_MAP,
    ZAAK_MAP,
    ZAAKTYPE_MAP,
)


class CMISConfig(AppConfig):
    name = "drc_cmis"
    verbose_name = "CMIS"
    app_name = "cmis"

    def ready(self):
        maps = {
            "ZAAKTYPE_MAP": ZAAKTYPE_MAP,
            "ZAAK_MAP": ZAAK_MAP,
            "DOCUMENT_MAP": DOCUMENT_MAP,
            "GEBRUIKSRECHTEN_MAP": GEBRUIKSRECHTEN_MAP,
            "OBJECTINFORMATIEOBJECT_MAP": OBJECTINFORMATIEOBJECT_MAP,
        }

        mapper_file_path = settings.CMIS_MAPPER_FILE

        with open(mapper_file_path, "r") as f:
            loaded_cmis_maps = json.load(f)

        for map_name, map_values in loaded_cmis_maps.items():
            for key, value in map_values.items():
                if map_name in maps and key in maps[map_name]:
                    maps[map_name][key] = value  # Add some validation

        errors = []
        for map_name, map_values in maps.items():
            for key, value in map_values.items():
                if maps.get(map_name).get(key) is None:
                    errors.append(f"{key} in {map_name}")

        if len(errors) > 0:
            raise Exception(
                f"Unsuccessful CMIS configuration. "
                f"The following fields in {os.path.basename(mapper_file_path)} are "
                f"unfilled: {', '.join(er for er in errors)}"
            )

        self.refresh_reverse_maps()

    def refresh_reverse_maps(self):
        """
        The maps are now configurable through a json file, so once the maps are initialised,
        the reverse maps need to be updated
        """
        mapper.REVERSE_ZAAKTYPE_MAP = {
            value: key for key, value in ZAAKTYPE_MAP.items()
        }
        mapper.REVERSE_ZAAK_MAP = {value: key for key, value in ZAAK_MAP.items()}
        mapper.REVERSE_DOCUMENT_MAP = {
            value: key for key, value in DOCUMENT_MAP.items()
        }
        mapper.REVERSE_GEBRUIKSRECHTEN_MAP = {
            value: key for key, value in GEBRUIKSRECHTEN_MAP.items()
        }
        mapper.REVERSE_OBJECTINFORMATIEOBJECT_MAP = {
            value: key for key, value in OBJECTINFORMATIEOBJECT_MAP.items()
        }
