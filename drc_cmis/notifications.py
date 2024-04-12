"""
Listen to the notifications that are send by the NRC
"""

from vng_api_common.notifications.handlers import RoutingHandler, default

from drc_cmis.client_builder import get_cmis_client, get_zds_client


class ZakenHandler:
    def __init__(self):
        self.cmis_client = get_cmis_client()

    def handle(self, data: dict) -> None:
        if data.get("actie") == "create" and data.get("resource") == "zaak":
            zaaktype_url = data.get("kenmerken", {}).get("zaaktype")
            zaak_url = data.get("resource_url")

            if zaak_url and zaaktype_url:
                self.create_zaak_folder(zaak_url, zaaktype_url)

    def create_zaak_folder(self, zaak_url: str, zaaktype_url: str, zaaktype_folder):
        client = get_zds_client(zaaktype_url)
        zaaktype_data = client.retrieve("zaaktype", url=zaaktype_url)

        client = get_zds_client(zaak_url)
        zaak_data = client.retrieve("zaak", url=zaak_url)
        self.cmis_client.get_or_create_zaak_folder(zaaktype_data, zaak_data)


default = RoutingHandler({"zaken": ZakenHandler()}, default=default)
