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
            )
        elif os.getenv("CMIS_BINDING") == "WEBSERVICE":
            CMISConfig.objects.create(
                client_url="http://localhost:8082/alfresco/cmisws",
                binding="WEBSERVICE",
                client_user="admin",
                client_password="admin",
            )

    def setUp(self):
        super().setUp()
        self.cmis_client = get_cmis_client()
        self._removeTree()
        self.cmis_client._base_folder = None

    def _removeTree(self):
        base_folder = self.cmis_client.base_folder
        base_folder.delete_tree()
