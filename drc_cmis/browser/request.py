import logging
from json.decoder import JSONDecodeError

from drc_cmis.utils.exceptions import (
    CmisBaseException,
    CmisInvalidArgumentException,
    CmisNotSupportedException,
    CmisNoValidResponse,
    CmisObjectNotFoundException,
    CmisPermissionDeniedException,
    CmisRuntimeException,
    CmisUpdateConflictException,
)

from ..connections import get_session

logger = logging.getLogger(__name__)


class Request:
    @property
    def session(self):
        # Uses a thread-local session object to enable connection pooling
        return get_session()

    def get_request(self, url, user, password, params=None):
        logger.debug(f"GET: {url} | {params}")
        headers = {"Accept": "application/json"}
        response = self.session.get(
            url, params=params, auth=(user, password), headers=headers
        )
        if not response.ok:
            raise Exception("Error with the query")

        if response.headers.get("Content-Type").startswith("application/json"):
            return response.json()
        return response.content

    def post_request(self, url, data, user, password, headers=None, files=None):
        logger.debug(f"POST: {url} | {data}")
        if headers is None:
            headers = {"Accept": "application/json"}
        response = self.session.post(
            url,
            data=data,
            auth=(user, password),
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
            if response.headers.get("Content-Type").startswith("application/json"):
                return response.json()
            else:
                return response.content.decode("UTF-8")
        except JSONDecodeError:
            if not response.text:
                return None
            raise CmisNoValidResponse(
                status=response.status_code,
                url=url,
                message=response.text,
                code="invalid_response",
            )
