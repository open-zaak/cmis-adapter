import logging
from json.decoder import JSONDecodeError

import requests

from drc_cmis.client.exceptions import (
    CmisBaseException,
    CmisInvalidArgumentException,
    CmisNotSupportedException,
    CmisNoValidResponse,
    CmisObjectNotFoundException,
    CmisPermissionDeniedException,
    CmisRuntimeException,
    CmisUpdateConflictException,
    GetFirstException,
)

logger = logging.getLogger(__name__)


class CMISRequest:
    @property
    def config(self):
        """
        Lazily load the config so that no DB queries are done while Django is starting.
        """
        from drc_cmis.models import CMISConfig

        return CMISConfig.get_solo()

    @property
    def base_url(self):
        return self.config.client_url

    @property
    def root_folder_url(self):
        return f"{self.base_url}/root"

    @property
    def base_folder(self):
        return f"{self.config.base_folder}"

    @property
    def user(self):
        return self.config.client_user

    @property
    def password(self):
        return self.config.client_password

    def get_request(self, url, params=None):
        logger.debug(f"GET: {url} | {params}")
        headers = {"Accept": "application/json"}
        response = requests.get(
            url, params=params, auth=(self.user, self.password), headers=headers
        )
        if not response.ok:
            raise Exception("Error with the query")

        if response.headers.get("Content-Type").startswith("application/json"):
            return response.json()
        return response.content

    def post_request(self, url, data, files=None):
        logger.debug(f"POST: {url} | {data}")
        headers = {"Accept": "application/json"}
        response = requests.post(
            url,
            data=data,
            auth=(self.user, self.password),
            files=files,
            headers=headers,
        )
        if not response.ok:
            error = response.json()
            if response.status_code == 401:
                raise CmisPermissionDeniedException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 400:
                raise CmisInvalidArgumentException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 404:
                raise CmisObjectNotFoundException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 403:
                raise CmisPermissionDeniedException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 405:
                raise CmisNotSupportedException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 409:
                raise CmisUpdateConflictException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            elif response.status_code == 500:
                raise CmisRuntimeException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )
            else:
                raise CmisBaseException(
                    status=response.status_code,
                    url=url,
                    message=error.get("message"),
                    code=error.get("exception"),
                )

        try:
            return response.json()
        except JSONDecodeError:
            if not response.text:
                return None
            raise CmisNoValidResponse(
                status=response.status_code,
                url=url,
                message=response.text,
                code="invalid_response",
            )

    def get_first_result(self, json, return_type):
        if len(json.get("results")) == 0:
            raise GetFirstException()

        return return_type(json.get("results")[0])

    def get_all_results(self, json, return_type):
        results = []
        for item in json.get("results"):
            results.append(return_type(item))
        return results

    def get_all_objects(self, json, return_type):
        objects = []
        for item in json:
            objects.append(return_type(item.get("object")))
        return objects
