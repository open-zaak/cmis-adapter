import requests
from requests import Response

from client.query import CMISQuery
from cmis.utils import (
    get_xml_doc,
    extract_xml_from_soap,
    extract_repository_id_from_xml,
    extract_root_folder_id_from_xml,
    extract_folders_from_xml,
)


class SOAPCMISRequest:
    _boundary = "------=_Part_52_1132425564.1594208078802"

    _headers = {
        "Content-Type": 'multipart/related; type="application/xop+xml"; start="<rootpart@soapui.org>"; '
        'start-info="application/soap+xml"; boundary="----=_Part_52_1132425564.1594208078802"',
        "SOAPAction": "",
        "MIME-Version": "1.0",
    }

    _envelope_headers = {
        "Content-Type": 'application/xop+xml; charset=UTF-8; type="application/soap+xml"',
        "Content-Transfer-Encoding": "8bit",
        "Content-ID": "<rootpart@soapui.org>",
    }

    @property
    def config(self):
        """
        Lazily load the config so that no DB queries are done while Django is starting.
        """
        from drc_cmis.models import CMISConfig

        return CMISConfig.get_solo()

    @property
    def base_url(self):
        """Return the base URL

        For example, for Alfresco running locally the base URL for SOAP requests is http://localhost:8082/alfresco/cmisws
        """
        return self.config.client_url

    @property
    def base_folder_name(self) -> str:
        return self.config.base_folder_name

    @property
    def main_repo_id(self) -> str:
        """Get ID of the CMS main repository"""

        if self._main_repo_id is None:
            soap_envelope = get_xml_doc(cmis_action="getRepositories")
            soap_response = self.request(
                "RepositoryService", soap_envelope=soap_envelope.toxml()
            )

            xml_response = extract_xml_from_soap(soap_response)
            self._main_repo_id = extract_repository_id_from_xml(xml_response)

        return self._main_repo_id

    @property
    def root_folder_id(self) -> str:
        """Get the ID of the folder where all folders/documents will be created"""

        if self._root_folder_id is None:
            soap_envelope = get_xml_doc(
                cmis_action="getRepositoryInfo", repository_id=self.main_repo_id
            )
            soap_response = self.request(
                "RepositoryService", soap_envelope=soap_envelope.toxml()
            )

            xml_response = extract_xml_from_soap(soap_response)
            self._root_folder_id = extract_root_folder_id_from_xml(xml_response)

        return self._root_folder_id

    def request(self, path: str, soap_envelope: str) -> Response:
        url = f"http://localhost:8082/alfresco/cmisws/{path.lstrip('/')}"

        envelope_header = ""
        for key, value in self._envelope_headers.items():
            envelope_header += f"{key}: {value}\n"

        # Format the body of the request
        body = f"\n{self._boundary}\n{envelope_header}\n{soap_envelope}\n\n{self._boundary}--\n"

        soap_response = requests.post(url, data=body, headers=self._headers, files=[])
        soap_response.raise_for_status()

        return soap_response.content.decode("UTF-8")
