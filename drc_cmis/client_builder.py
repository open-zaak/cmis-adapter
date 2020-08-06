from typing import Type, Union

from django.conf import settings
from django.utils.module_loading import import_string

from vng_api_common.models import APICredential
from zds_client.client import Client

from drc_cmis.browser.client import CMISDRCClient
from drc_cmis.models import CMISConfig
from drc_cmis.webservice.client import SOAPCMISClient

try:
    from zgw_consumers.client import get_client_class
except ImportError:

    def get_client_class() -> Type[Client]:
        return Client


def get_cmis_client() -> Union[CMISDRCClient, SOAPCMISClient]:
    """Build the CMIS client with the binding specified in the configuration"""
    config = CMISConfig.get_solo()
    if config.binding == "WEBSERVICE":
        return SOAPCMISClient()
    else:
        return CMISDRCClient()


def get_zds_client(url: str):
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
