from drc_cmis.connections import use_cmis_connection_pool

from .request import SOAPRequest
from .utils import extract_repo_info_from_xml, extract_xml_from_soap, make_soap_envelope


class SOAPRepositoryInfoFetcher:
    """
    Retrieve the information about a repository in the DMS

    Caching is done based on the repository ID.
    """

    def __init__(self):
        self.cache = {}

    @use_cmis_connection_pool
    def fetch(self, repo_id: str, base_url: str, user: str, password: str) -> dict:
        if repo_id in self.cache:
            return self.cache[repo_id]

        request = SOAPRequest(base_url)

        soap_envelope = make_soap_envelope(
            auth=(user, password),
            repository_id=repo_id,
            cmis_action="getRepositoryInfo",
        )

        soap_response = request.request(
            "RepositoryService", soap_envelope=soap_envelope.toxml()
        )

        xml_response = extract_xml_from_soap(soap_response)

        self.cache[repo_id] = extract_repo_info_from_xml(xml_response)

        return self.cache[repo_id]


# sentinel instance, with a cache
repo_info_fetcher = SOAPRepositoryInfoFetcher()
"""
Sentinel repository info fetcher instance, used by :class:`drc_cmis.webservice.client.SOAPCMISClient`.
Note that you can mutate ``repo_info_fetcher.cache`` to replace it with another cache
backend.
"""
