from drc_cmis.client.browser_client import CMISDRCClient
from drc_cmis.client.soap_client import SOAPCMISClient

from .models import CMISConfig


def get_client_class() -> type:
    config = CMISConfig.get_solo()
    if config.binding == "WEBSERVICE":
        return SOAPCMISClient
    else:
        return CMISDRCClient
