import os

from drc_cmis.client_builder import get_cmis_client
from drc_cmis.models import CMISConfig


class DMSMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        if os.getenv("CMIS_BINDING") == "BROWSER":
            CMISConfig.objects.create(
                client_url="http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
                binding="BROWSER",
                client_user="admin",
                client_password="admin",
                zaak_folder_path="/TestZaken/{{ zaaktype }}/{{ year }}/{{ month }}/{{ day }}/{{ zaak }}/",
                other_folder_path="/TestDRC/{{ year }}/{{ month }}/{{ day }}/",
                verzoek_folder_path="/TestDRC/Verzoeken/{{ year }}/{{ month }}/{{ day }}/{{ verzoek }}/",
            )
        elif os.getenv("CMIS_BINDING") == "WEBSERVICE":
            CMISConfig.objects.create(
                client_url="http://localhost:8082/alfresco/cmisws",
                binding="WEBSERVICE",
                client_user="admin",
                client_password="admin",
                zaak_folder_path="/TestZaken/{{ zaaktype }}/{{ year }}/{{ month }}/{{ day }}/{{ zaak }}/",
                other_folder_path="/TestDRC/{{ year }}/{{ month }}/{{ day }}/",
                verzoek_folder_path="/TestDRC/Verzoeken/{{ year }}/{{ month }}/{{ day }}/{{ verzoek }}/",
            )
        else:
            raise Exception(
                "No CMIS binding set through CMIS_BINDING environment variable."
            )

    def setUp(self):
        super().setUp()
        self.cmis_client = get_cmis_client()
        self.cmis_client.delete_cmis_folders_in_base()

    def tearDown(self) -> None:
        self.cmis_client.delete_cmis_folders_in_base()
