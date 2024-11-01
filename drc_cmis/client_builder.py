from typing import Union

from drc_cmis.browser.client import CMISDRCClient
from drc_cmis.models import CMISConfig
from drc_cmis.webservice.client import SOAPCMISClient


def get_cmis_client() -> Union[CMISDRCClient, SOAPCMISClient]:
    """Build the CMIS client with the binding specified in the configuration"""
    config = CMISConfig.get_solo()
    if config.binding == "WEBSERVICE":
        return SOAPCMISClient()
    else:
        return CMISDRCClient()
