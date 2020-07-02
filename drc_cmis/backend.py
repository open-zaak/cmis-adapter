import logging
from decimal import Decimal

from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.translation import ugettext_lazy as _

from cmislib.exceptions import UpdateConflictException
from rest_framework.exceptions import ValidationError

from drc_cmis.client.mapper import mapper

from .client import CMISDRCClient
from .client.convert import (
    make_enkelvoudiginformatieobject_dataclass,
    make_objectinformatieobject_dataclass,
)
from .client.exceptions import (
    CmisUpdateConflictException,
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockConflictException,
    DocumentNotLockedException,
    GetFirstException,
)
from .data.v1_0_x import (
    EnkelvoudigInformatieObject,
    ObjectInformatieObject,
    PaginationObject,
)

logger = logging.getLogger(__name__)


class BackendException(ValidationError):
    def __init__(
        self,
        detail,
        create=False,
        update=False,
        retreive_single=False,
        delete=False,
        retreive_list=False,
        code=None,
    ):
        self.create = create
        self.update = update
        self.retreive_single = retreive_single
        self.delete = delete
        self.retreive_list = retreive_list

        super().__init__(detail, code)


class CMISDRCStorageBackend:
    """
    This is the backend that is used to store the documents in a CMIS compatible backend.

    This class is based on:
        drc.backend.abstract.BaseDRCStorageBackend
    """

    exception_class = BackendException
    eio_dataclass = EnkelvoudigInformatieObject
    oio_dataclass = ObjectInformatieObject
    pagination_dataclass = PaginationObject

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmis_client = CMISDRCClient()

    def create_document(self, data, content):
        """
        Create a new document in the CMIS backend.

        Args:
            data (dict): A dict containing the values returned from the serializer.
            content (BytesStream): The content of the document.

        Returns:
            dataclass: An enkelvoudig informatieobject dataclass.

        Raises:
            BackendException: Raised a backend exception if the document exists.
            BackendException: Raised a backend exception if there is a document with the same name.

        """
        identification = data.pop("identificatie")
        logger.debug(f"CMIS_BACKEND: create_document {identification} start")

        try:
            cmis_doc = self.cmis_client.create_document(identification, data, content)
            dict_doc = make_enkelvoudiginformatieobject_dataclass(
                cmis_doc, self.eio_dataclass
            )
            logger.debug(f"CMIS_BACKEND: create_document {identification} successful")
            return dict_doc
        except UpdateConflictException:
            error_message = "Document is niet uniek. Dit kan liggen aan de titel, inhoud of documentnaam"
            raise self.exception_class({None: error_message}, create=True)
        except DocumentExistsError as e:
            raise self.exception_class({None: e.message}, create=True)

    def get_documents(self, page=1, page_size=100, filters=None):
        """
        Fetch all the documents from CMIS backend.

        Args:
            filters (dict or None): A dict with the filters that need to be applied.

        Returns:
            dataclass: A list of enkelvoudig informatieobject dataclass.

        """
        print("get_documents")
        logger.debug("CMIS_BACKEND: get_documents start")
        cmis_documents = self.cmis_client.get_cmis_documents(
            filters=filters, page=page, results_per_page=page_size
        )
        print(cmis_documents)
        documents_data = []
        for cmis_doc in cmis_documents["results"]:
            dict_document = make_enkelvoudiginformatieobject_dataclass(
                cmis_doc, self.eio_dataclass
            )
            if dict_document:
                documents_data.append(dict_document)
        print(documents_data)
        paginated_result = self.pagination_dataclass(
            count=cmis_documents["total_count"], results=documents_data,
        )

        logger.debug("CMIS_BACKEND: get_documents successful")
        return paginated_result

    def get_document(self, uuid: str):
        """
        Get a document by cmis versionId.

        Args:
            uuid (str): The cmis version id (only the uuid part).

        Returns:
            dataclass: An enkelvoudig informatieobject dataclass.

        Raises:
            BackendException: Raised a backend exception if the document does not exists.

        """
        logger.debug(f"CMIS_BACKEND: get_document {uuid} start")
        try:
            cmis_document = self.cmis_client.get_cmis_document(uuid)
        except DocumentDoesNotExistError as e:
            raise self.exception_class(
                {None: e.message}, create=True, code="document-does-not-exist"
            )
        else:
            logger.debug(f"CMIS_BACKEND: get_document {uuid} successful")
            doc = make_enkelvoudiginformatieobject_dataclass(
                cmis_document, self.eio_dataclass
            )
            return doc

    def get_document_content(self, uuid):
        logger.debug(f"CMIS_BACKEND: get_document_content {uuid} start")
        try:
            cmis_document = self.cmis_client.get_cmis_document(uuid)
        except DocumentDoesNotExistError as e:
            raise self.exception_class({None: e.message}, create=True)
        else:
            content = cmis_document.get_content_stream()
            content.seek(0)
            logger.debug(f"CMIS_BACKEND: get_document_content {uuid} successful")
            return content.read(), cmis_document.name

    def update_document(self, uuid, lock, data, content):
        """
        Update the document that is saved in the drc.

        Args:
            uuid (str): The uuid from the document.
            data (dict): A dict with the fields that need to be updated.
            content (BytesStream): The content of the document.

        Returns:
            dataclass: An enkelvoudig informatieobject dataclass.

        Raises:
            BackendException: Raised a backend exception if the document does not exists.

        """
        logger.debug(f"CMIS_BACKEND: update_document {uuid} start")
        try:
            cmis_document = self.cmis_client.update_cmis_document(
                uuid, lock, data, content
            )
        except DocumentDoesNotExistError as e:
            raise self.exception_class({None: e.message}, update=True)
        except DocumentNotLockedException as e:
            raise self.exception_class(
                {None: e.message}, update=True, code="not-locked"
            )
        except DocumentLockConflictException as e:
            raise self.exception_class(
                {None: e.message}, update=True, code="wrong-lock"
            )
        else:
            logger.debug(f"CMIS_BACKEND: update_document {uuid} successful")
            return make_enkelvoudiginformatieobject_dataclass(
                cmis_document, self.eio_dataclass
            )

    def delete_document(self, uuid):
        """
        A request to delete the document.

        Args:
            uuid (str): The uuid of the document.

        Returns:
            dataclass: An enkelvoudig informatieobject dataclass.

        Raises:
            BackendException: Raised a backend exception if the document does not exists.

        """
        logger.debug(f"CMIS_BACKEND: delete_document {uuid} start")
        try:
            cmis_document = self.cmis_client.delete_cmis_document(uuid)
        except DocumentDoesNotExistError as e:
            raise self.exception_class({None: e.message}, create=True)
        else:
            logger.debug(f"CMIS_BACKEND: delete_document {uuid} successful")
            return make_enkelvoudiginformatieobject_dataclass(
                cmis_document, self.eio_dataclass, skip_deleted=True
            )

    def obliterate_document(self, uuid: str) -> None:
        """
        Permanently delete the document identified by ``uuid``.

        Args:
            uuid (str): The uuid of the document.

        Returns:
            None

        Raises:
            BackendException: Raised a backend exception if the document does not exists.

        """
        logger.info("Obliterating document with UUID %s", uuid)
        try:
            self.cmis_client.obliterate_document(uuid)
        except DocumentDoesNotExistError as exc:
            raise self.exception_class({None: exc.message}, delete=True) from exc
        else:
            logger.info("Obliterated document with UUID %s", uuid)

    def lock_document(self, uuid: str, lock: str):
        """
        Check out the CMIS document and store the lock value for check in/unlock.
        """
        logger.debug("CMIS checkout of document %s (lock value %s)", uuid, lock)
        cmis_doc = self.cmis_client.get_cmis_document(uuid)

        already_locked = self.exception_class(
            detail="Document was already checked out", code="double_lock"
        )

        try:
            pwc = cmis_doc.checkout()
            assert (
                pwc.isPrivateWorkingCopy
            ), "checkout result must be a private working copy"
            if pwc.lock:
                raise already_locked

            # store the lock value on the PWC so we can compare it later
            pwc.update_properties({mapper("lock"): lock})
        except CmisUpdateConflictException as exc:
            raise already_locked from exc

        logger.debug(
            "CMIS checkout of document %s with lock value %s succeeded", uuid, lock
        )

    def unlock_document(self, uuid, lock, force=False):
        logger.debug(f"CMIS_BACKEND: unlock_document {uuid} start with: {lock}")
        cmis_doc = self.cmis_client.get_cmis_document(uuid)
        pwc = cmis_doc.get_private_working_copy()

        if constant_time_compare(pwc.lock, lock) or force:
            pwc.update_properties({mapper("lock"): ""})
            new_doc = pwc.checkin("Updated via Documenten API")
            logger.debug("Unlocked document with UUID %s (forced: %s)", uuid, force)
            return make_enkelvoudiginformatieobject_dataclass(
                new_doc, self.eio_dataclass, skip_deleted=True
            )

        raise self.exception_class(
            detail=_("Lock did not match"), update=True, code="unlock-failed"
        )

    ################################################################################################
    # Splits #######################################################################################
    ################################################################################################

    def create_document_case_connection(self, data):
        """
        Create the connection between a document and a case folder.

        There are 2 possible paths here,
        1. There is no case connected to the document yet. So the document can be connected to the case.
            1.1. If there is a folder, move the document into the correct folder.
        2. There is a case connected to the document, so we need to create a copy of the document.

        Args:
            data (dict): A dict containing the values returned from the serializer.

        Returns:
            dataclass: An object informatieobject dataclass.

        """
        if not data.get("registratiedatum"):
            data["registratiedatum"] = timezone.now()
        logger.debug(
            f"CMIS_BACKEND: create_document_case_connection {data['registratiedatum']} start"
        )

        document_id = data.get("informatieobject").split("/")[-1]
        try:
            cmis_doc = self.cmis_client.get_cmis_document(document_id)
            if cmis_doc.object == data.get("object"):
                raise self.exception_class(
                    detail=_("connection is not unique"), code="unique"
                )
        except DocumentDoesNotExistError:
            assert False, "Error hier"

        try:
            folder = self.cmis_client.get_folder_from_case_url(data.get("object"))
        except GetFirstException:
            folder = None
        zaak_url = cmis_doc.object
        logger.debug(f"CMIS_BACKEND_VALUE: {zaak_url}")
        if not zaak_url:
            cmis_doc = self.cmis_client.update_case_connection(cmis_doc.objectId, data)
            if folder:
                self.cmis_client.move_to_case(cmis_doc, folder)
        elif zaak_url == data.get("object"):
            pass
        else:
            cmis_doc = self.cmis_client.copy_document(cmis_doc, folder, data)

        objectinformatieobject = make_objectinformatieobject_dataclass(
            cmis_doc, self.oio_dataclass
        )
        logger.debug(
            f"CMIS_BACKEND: create_document_case_connection {data['registratiedatum']} successful"
        )
        return objectinformatieobject

    def get_document_case_connections(self, filters=None):
        """
        Get all connections between case folders and documents.

        Returns:
            dataclass: A list of object informatieobject dataclass.

        """
        logger.debug("CMIS_BACKEND: get_document_case_connections start")

        if not filters:
            filters = {}

        if "informatieobject" in filters and filters.get("informatieobject"):
            document = self.get_document_case_connection(
                filters.get("informatieobject").split("/")[-1]
            )
            return [document]

        if "object" not in filters:
            filters["object"] = "NOT NULL"
        cmis_documents = self.cmis_client.get_cmis_documents(filters=filters, page=0)
        documents_data = []

        for cmis_doc in cmis_documents.get("results"):
            dict_document = make_objectinformatieobject_dataclass(
                cmis_doc, self.oio_dataclass
            )
            if dict_document:
                documents_data.append(dict_document)
        logger.debug("CMIS_BACKEND: get_document_case_connections successful")
        return documents_data

    def get_document_case_connection(self, uuid):
        """
        Get a single connection by uuid.

        Args:
            uuid (str): the CMIS id from the connected document.

        Returns:
            dataclass: A object informatieobject dataclass.

        Raises:
            BackendException: If the document can not be found.

        """
        logger.debug(f"CMIS_BACKEND: get_document_case_connection {uuid} start")
        try:
            cmis_document = self.cmis_client.get_cmis_document(
                uuid, filters={"drc:connectie__zaakurl": "NOT NULL"}
            )
        except DocumentDoesNotExistError as e:
            raise self.exception_class({None: e.message}, create=True)
        else:
            objectinformatieobject = make_objectinformatieobject_dataclass(
                cmis_document, self.oio_dataclass
            )
            logger.debug(
                f"CMIS_BACKEND: get_document_case_connection {uuid} successful"
            )
            return objectinformatieobject

    def update_document_case_connection(self, uuid, data):
        """
        Update the connection.

        Args:
            uuid (str): The CMIS id of the document.
            data (dict): The data that needs to be updated.

        Returns:
            dataclass: A object informatieobject dataclass.

        Raises:
            BackendException: If the document can not be found.

        """
        logger.debug(f"CMIS_BACKEND: update_document_case_connection {uuid} start")
        try:
            cmis_document = self.cmis_client.update_case_connection(uuid, data)
        except DocumentDoesNotExistError as e:
            raise self.exception_class({None: e.message}, create=True)
        else:
            objectinformatieobject = make_objectinformatieobject_dataclass(
                cmis_document, self.oio_dataclass
            )
            logger.debug(
                f"CMIS_BACKEND: update_document_case_connection {uuid} successful"
            )
            return objectinformatieobject

    def delete_document_case_connection(self, uuid):
        """
        Uncouple a document from the case folder.

        Args:
            uuid (str): The CMIS id of the document.

        Returns:
            dataclass: A object informatieobject dataclass.

        Raises:
            BackendException: If the document can not be found.

        """
        logger.debug(f"CMIS_BACKEND: delete_document_case_connection {uuid} start")
        try:
            cmis_document = self.cmis_client.delete_case_connection(uuid)
        except DocumentDoesNotExistError as e:
            raise self.exception_class({None: e.message}, create=True)
        else:
            objectinformatieobject = make_objectinformatieobject_dataclass(
                cmis_document, self.oio_dataclass
            )
            logger.debug(
                f"CMIS_BACKEND: delete_document_case_connection {uuid} successful"
            )
            return objectinformatieobject

    def _fix_version(self, version):
        if version:
            return Decimal(version) / Decimal("100.0")
        return None

    def _find_version(self, version, cmis_document):
        versions = cmis_document.get_all_versions()
        if int(version) == version:
            version = round(version, 1)
        return versions.get(str(version))
