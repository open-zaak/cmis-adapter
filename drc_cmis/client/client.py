import logging
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import List, Optional, Union
from uuid import UUID

from django.db.utils import IntegrityError
from django.utils.crypto import constant_time_compare

from cmislib.exceptions import UpdateConflictException

from drc_cmis.cmis.drc_document import (
    Document,
    Folder,
    Gebruiksrechten,
    ObjectInformatieObject,
)
from drc_cmis.cmis.utils import CMISRequest

from .exceptions import (
    DocumentConflictException,
    DocumentDoesNotExistError,
    DocumentExistsError,
    DocumentLockConflictException,
    DocumentNotLockedException,
    GetFirstException,
)
from .mapper import mapper
from .query import CMISQuery
from .utils import get_random_string

logger = logging.getLogger(__name__)


class CMISDRCClient(CMISRequest):
    """
    DRC client implementation using the CMIS protocol.

    This class makes it easier to query for everything you need.
    """

    documents_in_folders_query = CMISQuery("SELECT * FROM drc:document WHERE %s")
    find_folder_by_case_url_query = CMISQuery(
        "SELECT * FROM drc:zaakfolder WHERE drc:zaak__url='%s'"
    )

    _repo = None
    _root_folder = None
    _base_folder = None

    @property
    def _get_base_folder(self):
        logger.debug("CMIS_CLIENT: _get_base_folder")
        if not self._base_folder:
            base = self.get_request(self.root_folder_url)
            for folder_response in base.get("objects"):
                folder = Folder(folder_response["object"])
                if folder.name == self.base_folder:
                    self._base_folder = folder
            if not self._base_folder:
                folder = Folder({})
                self._base_folder = folder.create_folder(name=self.base_folder)
        return self._base_folder

    # generic querying
    def query(self, return_type, lhs: List[str], rhs: List[str]):
        table = return_type.table
        where = (" WHERE " + " AND ".join(lhs)) if lhs else ""
        query = CMISQuery("SELECT * FROM %s%s" % (table, where))

        body = {
            "cmisaction": "query",
            "statement": query(*rhs),
        }
        response = self.post_request(self.base_url, body)
        logger.debug(response)
        return self.get_all_results(response, return_type)

    # ZRC Notification client calls.
    def get_or_create_zaaktype_folder(self, zaaktype):
        """
        Create a folder with the prefix 'zaaktype-' to make a zaaktype folder

        """
        logger.debug("CMIS_CLIENT: get_or_create_zaaktype_folder")
        properties = {
            "cmis:objectTypeId": "F:drc:zaaktypefolder",
            mapper("url", "zaaktype"): zaaktype.get("url"),
            mapper("identificatie", "zaaktype"): zaaktype.get("identificatie"),
        }

        folder_name = (
            f"zaaktype-{zaaktype.get('omschrijving')}-{zaaktype.get('identificatie')}"
        )
        cmis_folder = self._get_or_create_folder(
            folder_name, self._get_base_folder, properties
        )
        return cmis_folder

    def get_or_create_zaak_folder(self, zaak, zaaktype_folder):
        """
        Create a folder with the prefix 'zaak-' to make a zaak folder

        """
        logger.debug("CMIS_CLIENT: get_or_create_zaak_folder")
        properties = {
            "cmis:objectTypeId": "F:drc:zaakfolder",
            mapper("url", "zaak"): zaak.get("url"),
            mapper("identificatie", "zaak"): zaak.get("identificatie"),
            mapper("zaaktype", "zaak"): zaak.get("zaaktype"),
            mapper("bronorganisatie", "zaak"): zaak.get("bronorganisatie"),
        }
        cmis_folder = self._get_or_create_folder(
            f"zaak-{zaak.get('identificatie')}", zaaktype_folder, properties
        )
        return cmis_folder

    # DRC client calls.
    def create_document(self, identification: str, data: dict, content=None):
        """
        Create a cmis document.

        Args:
            identification (str): A unique identifier for the document.
            data (dict): A dict with all the data that needs to be saved on the document.
            content (BytesStream): The content of the document.

        Returns:
            AtomPubDocument: A cmis document.

        Raises:
            DocumentExistsError: when a document already uses the same identifier.

        """
        logger.debug("CMIS_CLIENT: create_document")
        self._check_document_exists(identification)

        now = datetime.now()
        data.setdefault("versie", 1)

        if content is None:
            content = BytesIO()

        year_folder = self._get_or_create_folder(str(now.year), self._get_base_folder)
        month_folder = self._get_or_create_folder(str(now.month), year_folder)
        day_folder = self._get_or_create_folder(str(now.day), month_folder)

        properties = Document.build_properties(
            data, new=True, identification=identification
        )

        # Make sure that the content is set.
        content.seek(0)
        return day_folder.create_document(
            name=properties.pop("cmis:name"),
            properties=properties,
            content_file=content,
        )

    def get_cmis_documents(self, filters=None, page=1, results_per_page=100):
        """
        Gives a list of cmis documents.

        Args:
            filters (dict): A dict of filters that need to be applied to the search.

        Returns:
            AtomPubDocument: A list of CMIS documents.

        """
        logger.debug("CMIS_CLIENT: get_cmis_documents")
        filter_string = self._build_filter(filters, strip_end=True)
        query = "SELECT * FROM drc:document WHERE drc:document__verwijderd='false'"
        if filter_string:
            query += f" AND {filter_string}"

        logger.debug(query)
        data = {
            "cmisaction": "query",
            "statement": query,
        }

        skip_count = 0
        if page:
            results_per_page = results_per_page
            max_items = results_per_page
            skip_count = page * results_per_page - results_per_page

            data["maxItems"] = max_items
            data["skipCount"] = skip_count

        json_response = self.post_request(self.base_url, data)
        logger.debug(json_response)
        results = self.get_all_results(json_response, Document)
        return {
            "has_next": json_response["hasMoreItems"],
            "total_count": json_response["numItems"],
            "has_prev": skip_count > 0,
            "results": results,
        }

    def get_cmis_document(
        self, uuid: Optional[str], via_identification=None, filters=None
    ):
        """
        Given a cmis document instance.

        :param uuid: UUID of the document as used in the endpoint URL
        :return: :class:`AtomPubDocument` object, the latest version of this document
        """
        logger.debug("CMIS_CLIENT: get_cmis_document")
        assert (
            not via_identification
        ), "Support for 'via_identification' is being dropped"

        error_string = (
            f"Document met identificatie {uuid} bestaat niet in het CMIS connection"
        )
        does_not_exist = DocumentDoesNotExistError(error_string)

        # shortcut - no reason in going over the wire
        if uuid is None:
            raise does_not_exist

        # this always selects the latest version
        query = CMISQuery("SELECT * FROM drc:document WHERE cmis:objectId = '%s' %s")

        filter_string = self._build_filter(
            filters, filter_string="AND ", strip_end=True
        )
        data = {
            "cmisaction": "query",
            "statement": query(uuid, filter_string),
        }
        json_response = self.post_request(self.base_url, data)

        try:
            return self.get_first_result(json_response, Document)
        except GetFirstException as exc:
            raise does_not_exist from exc

    def update_cmis_document(self, uuid: str, lock: str, data: dict, content=None):
        logger.debug("Updating document with UUID %s", uuid)
        cmis_doc = self.get_cmis_document(uuid)

        if not cmis_doc.isVersionSeriesCheckedOut:
            raise DocumentNotLockedException(
                "Document is not checked out and/or locked."
            )

        assert not cmis_doc.isPrivateWorkingCopy, "Unexpected PWC retrieved"
        pwc = cmis_doc.get_private_working_copy()

        if not pwc.lock:
            raise DocumentNotLockedException(
                "Document is not checked out and/or locked."
            )

        correct_lock = constant_time_compare(lock, pwc.lock)
        if not correct_lock:
            raise DocumentLockConflictException("Wrong document lock given.")

        # build up the properties
        current_properties = cmis_doc.properties
        new_properties = Document.build_properties(data, new=False)

        diff_properties = {
            key: value
            for key, value in new_properties.items()
            if current_properties.get(key) != value
        }

        try:
            pwc.update_properties(diff_properties)
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc

        if content is not None:
            pwc.set_content_stream(content)

        return pwc

    def delete_cmis_document(self, uuid):
        """
        Update the property that the document is deleted.

        Arguments:
            uuid (str): The uuid of the document.

        Returns:
            AtomPubDocument: A CMIS document.

        Raises:
            DocumentConflictException: If the document could not be updated.
        """
        logger.debug("CMIS_CLIENT: delete_cmis_document")
        cmis_doc = self.get_cmis_document(uuid)
        new_properties = {mapper("verwijderd"): True}

        try:
            cmis_doc.update_properties(new_properties)
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc
        return cmis_doc

    def delete_cmis_folders_in_base(self):
        for child_folder in self._get_base_folder.get_children():
            child_folder.delete_tree()

    def obliterate_document(self, uuid: str) -> None:
        logger.debug("CMIS_CLIENT: obliterate_document")
        cmis_doc = self.get_cmis_document(uuid)
        cmis_doc.destroy()
        logger.debug("CMIS_CLIENT: obliteration successful")

    # Split ########################################################################################

    def update_case_connection(self, uuid, data):
        logger.debug("CMIS_CLIENT: update_case_connection")
        cmis_doc = self.get_cmis_document(uuid)

        current_properties = cmis_doc.properties
        new_properties = self._build_case_properties(data, allow_empty=False)
        diff_properties = {
            key: value
            for key, value in new_properties.items()
            if current_properties.get(key) != new_properties.get(key)
        }

        if diff_properties:
            try:
                cmis_doc.update_properties(diff_properties)
            except UpdateConflictException as exc:
                # Node locked!
                raise DocumentConflictException from exc
        return cmis_doc

    def delete_case_connection(self, uuid):
        logger.debug("CMIS_CLIENT: delete_case_connection")
        cmis_doc = self.get_cmis_document(uuid)
        parents = cmis_doc.get_object_parents()
        connection_count = len(parents)

        in_zaakfolder = False
        for parent in parents:
            if parent.properties.get("cmis:objectTypeId") == "F:drc:zaakfolder":
                in_zaakfolder = True

        if in_zaakfolder and connection_count == 1:
            now = datetime.now()
            year_folder = self._get_or_create_folder(
                str(now.year), self._get_base_folder
            )
            month_folder = self._get_or_create_folder(str(now.month), year_folder)
            day_folder = self._get_or_create_folder(str(now.day), month_folder)

            self.move_to_case(cmis_doc, day_folder)

        # Clear properties
        current_properties = cmis_doc.properties
        new_properties = self._build_case_properties({}, allow_empty=True)
        diff_properties = {
            key: value
            for key, value in new_properties.items()
            if current_properties.get(key) != new_properties.get(key)
        }

        if diff_properties:
            try:
                cmis_doc.update_properties(diff_properties)
            except UpdateConflictException as exc:
                # Node locked!
                raise DocumentConflictException from exc
        return cmis_doc

    def move_to_case(self, cmis_doc, folder):
        logger.debug("CMIS_CLIENT: move_to_case")
        parent = [parent for parent in cmis_doc.get_object_parents()][0]
        cmis_doc.move(parent, folder)

    def copy_document(self, cmis_doc, folder, data):
        """
        The copy from source is not supported via the atom pub bindings.
        So we create a new document with the same values.
        """
        logger.debug("CMIS_CLIENT: copy_document")

        attributes = [
            "auteur",
            "beschrijving",
            "bestandsnaam",
            "bronorganisatie",
            "creatiedatum",
            "formaat",
            "identificatie",
            "indicatie_gebruiksrecht",
            "informatieobjecttype",
            "integriteit_algoritme",
            "integriteit_datum",
            "integriteit_waarde",
            "link",
            "ondertekening_datum",
            "ondertekening_soort",
            "ontvangstdatum",
            "status",
            "taal",
            "vertrouwelijkheidaanduiding",
            "verwijderd",
            "verzenddatum",
        ]

        # copy the properties from the source document
        properties = {
            mapper(attribute, type="document"): getattr(cmis_doc, attribute)
            for attribute in attributes
        }

        properties.update(
            **{
                "cmis:objectTypeId": cmis_doc.objectTypeId,
                mapper("titel", type="document"): f"{cmis_doc.titel} - copy",
                "drc:kopie_van": cmis_doc.uuid,  # Keep tack of where this is copied from.
            }
        )

        new_properties = self._build_case_properties(data)
        properties.update(**new_properties)

        if not folder:
            now = datetime.now()
            year_folder = self._get_or_create_folder(
                str(now.year), self._get_base_folder
            )
            month_folder = self._get_or_create_folder(str(now.month), year_folder)
            folder = self._get_or_create_folder(str(now.day), month_folder)

        # Update the cmis:name to make it more unique
        file_name = f"{cmis_doc.titel}-{get_random_string()}"
        properties["cmis:name"] = file_name

        stream = cmis_doc.get_content_stream()
        new_doc = folder.create_document(
            name=file_name, properties=properties, content_file=stream,
        )

        return new_doc

    def get_folder_from_case_url(self, zaak_url):
        logger.debug("CMIS_CLIENT: get_folder_from_case_url")
        query = self.find_folder_by_case_url_query(zaak_url)
        data = {
            "cmisaction": "query",
            "statement": query,
        }

        json_response = self.post_request(self.base_url, data)
        try:
            return self.get_first_result(json_response, Folder)
        except GetFirstException:
            return None

    # Private functions.
    def _get_or_create_folder(self, name, parent, properties=None):
        """
        Get or create the folder with :param:`name` in :param:`parent`.

        :param name: string, the name of the folder to create.
        :param parent: parent folder to create the folder in as subfolder.
        :param properties: dictionary with cmis and/or custom properties to
          pass to the folder object
        :return: the folder that was retrieved or created.
        """
        logger.debug("CMIS_CLIENT: _get_or_create_folder")
        existing = self._get_folder(name, parent)
        if existing:
            return existing
        return parent.create_folder(name, properties=properties or {})

    def _get_folder(self, name, parent):
        logger.debug("CMIS_CLIENT: _get_folder")
        existing = next(
            (child for child in parent.get_children() if str(child.name) == str(name)),
            None,
        )
        if existing is not None:
            return existing
        return None

    def _build_filter(self, filters, filter_string="", strip_end=False):
        logger.debug("CMIS_CLIENT: _build_filter")
        if filters:
            for key, value in filters.items():
                if mapper(key):
                    key = mapper(key)
                elif mapper(key, type="connection"):
                    key = mapper(key, type="connection")
                elif mapper(key, type="gebruiksrechten"):
                    key = mapper(key, type="gebruiksrechten")
                elif mapper(key, type="objectinformatieobject"):
                    key = mapper(key, type="objectinformatieobject")

                if value and value in ["NULL", "NOT NULL"]:
                    filter_string += f"{key} IS {value} AND "
                elif isinstance(value, Decimal):
                    filter_string += f"{key} = {value} AND "
                elif isinstance(value, list):
                    if len(value) == 0:
                        continue
                    filter_string += "( "
                    for item in value:
                        sub_filter_string = self._build_filter(
                            {key: item}, strip_end=True
                        )
                        filter_string += f"{sub_filter_string} OR "
                    filter_string = filter_string[:-3]
                    filter_string += " ) AND "
                elif value:
                    filter_string += f"{key} = '{value}' AND "

        if strip_end and filter_string[-4:] == "AND ":
            filter_string = filter_string[:-4]

        return filter_string

    def _build_case_properties(self, data, allow_empty=True):
        logger.debug("CMIS_CLIENT: _build_case_properties")
        props = {}
        if data.get("object") or allow_empty:
            props[mapper("object", "connection")] = data.get("object")
        if data.get("object_type") or allow_empty:
            props[mapper("object_type", "connection")] = data.get("object_type")
        if data.get("aard_relatie") or allow_empty:
            props[mapper("aard_relatie", "connection")] = data.get("aard_relatie")
        if data.get("titel") or allow_empty:
            props[mapper("titel", "connection")] = data.get("titel")
        if data.get("beschrijving") or allow_empty:
            props[mapper("beschrijving", "connection")] = data.get("beschrijving")
        if data.get("registratiedatum") or allow_empty:
            props[mapper("registratiedatum", "connection")] = data.get(
                "registratiedatum"
            )

        return props

    def _check_document_exists(self, identification: Union[str, UUID]):
        # FIXME: should be both bronorganisatie and identification check, not just identification
        logger.debug("CMIS_CLIENT: _check_document_exists")

        column = mapper("identificatie", type="document")
        query = CMISQuery(f"SELECT * FROM drc:document WHERE {column} = '%s'")

        data = {
            "cmisaction": "query",
            "statement": query(str(identification)),
        }
        json_response = self.post_request(self.base_url, data)
        if json_response["numItems"] > 0:
            error_string = f"Document identificatie {identification} is niet uniek."
            raise DocumentExistsError(error_string)

    def create_cmis_gebruiksrechten(self, data):
        """
        Creates a Gebruiksrechten object.
        :return:
        """

        gebruiksrechten_folder = self._get_or_create_folder(
            "Gebruiksrechten", self._get_base_folder
        )

        properties = {
            mapper(key, type="gebruiksrechten"): value
            for key, value in data.items()
            if mapper(key, type="gebruiksrechten")
        }

        return gebruiksrechten_folder.create_gebruiksrechten(
            name=get_random_string(), properties=properties
        )

    def get_all_cmis_gebruiksrechten(self):

        query = "SELECT * FROM drc:gebruiksrechten"

        data = {
            "cmisaction": "query",
            "statement": query,
        }

        json_response = self.post_request(self.base_url, data)
        results = self.get_all_results(json_response, Gebruiksrechten)
        return {
            "has_next": json_response["hasMoreItems"],
            "total_count": json_response["numItems"],
            "has_prev": False,
            "results": results,
        }

    def get_a_cmis_gebruiksrechten(self, uuid):

        query = f"SELECT * FROM drc:gebruiksrechten WHERE cmis:objectId = 'workspace://SpacesStore/{uuid};1.0'"

        data = {
            "cmisaction": "query",
            "statement": query,
        }

        json_response = self.post_request(self.base_url, data)

        try:
            return self.get_first_result(json_response, Gebruiksrechten)
        except GetFirstException:
            error_string = (
                f"Gebruiksrechten met uuid {uuid} bestaat niet in het CMIS connection"
            )
            raise DocumentDoesNotExistError(error_string)

    def get_cmis_gebruiksrechten(self, filters):

        if filters.get("uuid") is not None:
            results = [self.get_a_cmis_gebruiksrechten(filters.get("uuid"))]
            return {
                "has_next": False,
                "total_count": 1,
                "has_prev": False,
                "results": results,
            }
        else:
            query = "SELECT * FROM drc:gebruiksrechten WHERE "
            sql_filters = self._build_filter(filters, strip_end=True)

            if sql_filters:
                query += f"{sql_filters}"

            data = {
                "cmisaction": "query",
                "statement": query,
            }

            json_response = self.post_request(self.base_url, data)
            results = self.get_all_results(json_response, Gebruiksrechten)
            return {
                "has_next": json_response["hasMoreItems"],
                "total_count": json_response["numItems"],
                "has_prev": False,
                "results": results,
            }

    def delete_cmis_geruiksrechten(self, uuid):

        gebruiksrechten = self.get_a_cmis_gebruiksrechten(uuid)

        try:
            gebruiksrechten.delete_gebruiksrechten()
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc

    def create_cmis_oio(self, data):
        """
        Creates a ObjectInformatieObject.
        """

        # TODO: Implement constraints directly in Alfresco?
        if data.get("zaak") is not None and data.get("besluit") is not None:
            raise IntegrityError(
                "ObjectInformatie object cannot have both Zaak and Besluit relation"
            )
        elif data.get("zaak") is None and data.get("besluit") is None:
            raise IntegrityError(
                "ObjectInformatie object needs to have either a Zaak or Besluit relation"
            )
        oio_folder = self._get_or_create_folder(
            "ObjectInformatieObject", self._get_base_folder
        )

        properties = {
            mapper(key, type="objectinformatieobject"): value
            for key, value in data.items()
            if mapper(key, type="objectinformatieobject")
        }

        return oio_folder.create_oio(name=get_random_string(), properties=properties)

    def get_all_cmis_oio(self):

        query = "SELECT * FROM drc:oio"

        data = {
            "cmisaction": "query",
            "statement": query,
        }

        json_response = self.post_request(self.base_url, data)
        results = self.get_all_results(json_response, ObjectInformatieObject)
        return {
            "has_next": json_response["hasMoreItems"],
            "total_count": json_response["numItems"],
            "has_prev": False,
            "results": results,
        }

    def get_a_cmis_oio(self, uuid):
        """
        Filters the objectinformatieobject in Alfresco based on the UUID
        :param uuid: string
        :return: The first retrieved objectinformatie object with right uuid
        """

        query = f"SELECT * FROM drc:oio WHERE cmis:objectId = 'workspace://SpacesStore/{uuid};1.0'"

        data = {
            "cmisaction": "query",
            "statement": query,
        }

        json_response = self.post_request(self.base_url, data)

        try:
            return self.get_first_result(json_response, ObjectInformatieObject)
        except GetFirstException:
            error_string = f"ObjectInformatieObject met uuid {uuid} bestaat niet in het CMIS connection"
            raise DocumentDoesNotExistError(error_string)

    def get_cmis_oio(self, filters):
        """
        Filters the ObjectInformatieObjects on either the informatieobject, the zaak or besluit URL.
        :param filters: dict - valid keys are 'informatieobject', 'zaak' or 'besluit'
        :return: dictionary with the total number of results, the documents retrieved and 'has_prev/next' properties
        """

        if filters.get("uuid") is not None:
            try:
                results = [self.get_a_cmis_oio(filters.get("uuid"))]
                return {
                    "has_next": False,
                    "total_count": 1,
                    "has_prev": False,
                    "results": results,
                }
            except DocumentDoesNotExistError:
                results = []
                return {
                    "has_next": False,
                    "total_count": 0,
                    "has_prev": False,
                    "results": results,
                }
        elif len(filters) == 0:
            query = "SELECT * FROM drc:oio"
        else:
            query = "SELECT * FROM drc:oio WHERE "
            sql_filters = self._build_filter(filters, strip_end=True)

            if sql_filters:
                query += f"{sql_filters}"

        data = {
            "cmisaction": "query",
            "statement": query,
        }

        json_response = self.post_request(self.base_url, data)
        results = self.get_all_results(json_response, ObjectInformatieObject)
        return {
            "has_next": json_response["hasMoreItems"],
            "total_count": json_response["numItems"],
            "has_prev": False,
            "results": results,
        }

    def delete_cmis_oio(self, uuid):
        oio = self.get_a_cmis_oio(uuid)

        try:
            oio.delete_oio()
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc
