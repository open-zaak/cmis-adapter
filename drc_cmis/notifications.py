"""
Listen to the notifications that are send by the NRC
"""
from typing import Type

from django.conf import settings
from django.utils.module_loading import import_string

from vng_api_common.models import APICredential
from vng_api_common.notifications.handlers import default
from zds_client.client import Client

from drc_cmis.client import CMISDRCClient

try:
    from zgw_consumers.client import get_client_class
except ImportError:

    def get_client_class() -> Type[Client]:
        return Client


def get_client(url: str):
    """
    Retrieve a ZDS Client instance for the given API URL.

    The client respects the setting ``CUSTOM_CLIENT_FETCHER`` as used by vng-api-common,
    and will have the auth configured.
    """
    Client = get_client_class()
    default = Client.from_url(url)

    if getattr(settings, "CUSTOM_CLIENT_FETCHER", None):
        client = import_string(settings.CUSTOM_CLIENT_FETCHER)(default.base_url)
        return client
    else:
        default.auth = APICredential.get_auth(url)
        return default


class ZakenHandler:
    def __init__(self):
        self.cmis_client = CMISDRCClient()

    def handle(self, data: dict) -> None:
        if data.get("actie") == "create" and data.get("resource") == "zaak":
            zaaktype_url = data.get("kenmerken", {}).get("zaaktype")
            zaak_url = data.get("resource_url")

            if zaak_url and zaaktype_url:
                zaaktype_folder = self.create_zaaktype_folder(zaaktype_url)
                self.create_zaak_folder(zaak_url, zaaktype_url, zaaktype_folder)

    def create_zaaktype_folder(self, zaaktype_url: str):
        client = get_client(zaaktype_url)
        zaaktype_data = client.retrieve("zaaktype", url=zaaktype_url)
        return self.cmis_client.get_or_create_zaaktype_folder(zaaktype_data)

    def create_zaak_folder(self, zaak_url: str, zaaktype_url: str, zaaktype_folder):
        client = get_client(zaak_url)
        zaak_data = client.retrieve("zaak", url=zaak_url)
        self.cmis_client.get_or_create_zaak_folder(zaak_data, zaaktype_folder)


class RoutingHandler:
    def __init__(self, config: dict, default):
        self.config = config
        self.default = default

    def handle(self, message: dict):
        handler = self.config.get(message["kanaal"])
        if handler is not None:
            handler.handle(message)
        else:
            self.default.handle(message)


default = RoutingHandler({"zaken": ZakenHandler()}, default=default)
