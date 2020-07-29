from drc_cmis.client_builder import get_client_class
from drc_cmis.models import CMISConfig


class DMSMixin:
    def setUp(self):
        super().setUp()
        client_class = get_client_class()
        self.cmis_client = client_class()
        self._removeTree()
        self.cmis_client._base_folder = None

    def _removeTree(self):
        base_folder = self.cmis_client.base_folder
        base_folder.delete_tree()


class BrowserTestCase(DMSMixin):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        CMISConfig.objects.create(
            client_url="http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
            binding="BROWSER",
            client_user="admin",
            client_password="admin",
        )


class WebServiceTestCase(DMSMixin):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        CMISConfig.objects.create(
            client_url="http://localhost:8082/alfresco/cmisws",
            binding="WEBSERVICE",
            client_user="admin",
            client_password="admin",
        )
