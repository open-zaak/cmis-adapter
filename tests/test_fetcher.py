import os
from unittest import skipIf
from unittest.mock import patch

from django.test import TestCase

from drc_cmis.webservice.client import SOAPCMISClient

from .mixins import DMSMixin

SOAP_RESPONSE = b"""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><getRepositoryInfoResponse xmlns="http://docs.oasis-open.org/ns/cmis/messaging/200908/" xmlns:ns2="http://docs.oasis-open.org/ns/cmis/core/200908/"><repositoryInfo><ns2:repositoryId>5341cc88-b2f6-4476-aff3-4add269dcb09</ns2:repositoryId></repositoryInfo><ns2:rootFolderId>workspace://SpacesStore/bf60ce3d-0051-4e43-90d0-b8c4dcf9259f</ns2:rootFolderId></getRepositoryInfoResponse></soap:Body></soap:Envelope>"""


class RepoInfoFetcherTests(DMSMixin, TestCase):
    @skipIf(
        os.getenv("CMIS_BINDING") != "WEBSERVICE",
        "Webservice specific test",
    )
    @patch("requests.Session.post")
    @patch("drc_cmis.webservice.client.SOAPCMISClient.get_main_repo_id", return_value=1)
    def test_repo_info_caching(self, mock_main_repo_id, mock_post):
        """
        Assert that the information of the same repository is not requested multiple times.
        """
        client = SOAPCMISClient()

        mock_post.return_value.content = SOAP_RESPONSE

        client.repository_info

        mock_post.assert_called_once()

        # fetch it again - no extra calls should be made
        client.repository_info

        mock_post.assert_called_once()

        # different repo_id, even different client instance
        mock_main_repo_id.return_value = 2
        client2 = SOAPCMISClient()

        client2.repository_info

        assert mock_post.call_count == 2
