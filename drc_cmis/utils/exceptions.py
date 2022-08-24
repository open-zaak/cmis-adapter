class DMSException(Exception):
    def __init__(self, message, *args, **kwargs):
        self.message = message


class FolderDoesNotExistError(DMSException):
    pass


class DocumentExistsError(DMSException):
    pass


class DocumentDoesNotExistError(DMSException):
    pass


class DocumentConflictException(DMSException):
    pass


class DocumentLockConflictException(DMSException):
    pass


class DocumentNotLockedException(DMSException):
    pass


class DocumentLockedException(DMSException):
    pass


class LockDidNotMatchException(DMSException):
    pass


class DocumentSizeMismatchException(DMSException):
    pass


class GetFirstException(Exception):
    pass


class CmisBaseException(Exception):
    """Common base class for all exceptions."""

    def __init__(self, status, url, message, code):
        self.display_message = f"Error {status}: {code} at {url} detail: {message}"
        super().__init__(self, self.display_message)
        self.status = status
        self.url = url
        self.message = message
        self.code = code


class CmisNoValidResponse(CmisBaseException):
    pass


class CmisInvalidArgumentException(CmisBaseException):
    """InvalidArgumentException"""

    pass


class CmisObjectNotFoundException(CmisBaseException):
    """ObjectNotFoundException"""

    pass


class CmisNotSupportedException(CmisBaseException):
    """NotSupportedException"""

    pass


class CmisPermissionDeniedException(CmisBaseException):
    """PermissionDeniedException"""

    pass


class CmisRuntimeException(CmisBaseException):
    """RuntimeException"""

    pass


class CmisConstraintException(CmisBaseException):
    """ConstraintException"""

    pass


class CmisContentAlreadyExistsException(CmisBaseException):
    """ContentAlreadyExistsException"""

    pass


class CmisFilterNotValidException(CmisBaseException):
    """FilterNotValidException"""

    pass


class CmisNameConstraintViolationException(CmisBaseException):
    """NameConstraintViolationException"""

    pass


class CmisStorageException(CmisBaseException):
    """StorageException"""

    pass


class CmisStreamNotSupportedException(CmisBaseException):
    """StreamNotSupportedException"""

    pass


class CmisUpdateConflictException(CmisBaseException):
    """UpdateConflictException"""

    pass


class CmisVersioningException(CmisBaseException):
    """VersioningException"""

    pass


class NoZaakBaseFolderException(Exception):
    pass


class NoOtherBaseFolderException(Exception):
    pass


class CmisRepositoryDoesNotExist(Exception):
    pass
