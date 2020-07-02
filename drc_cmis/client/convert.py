import logging
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.contrib.sites.models import Site
from django.http import HttpRequest
from django.urls import reverse

import iso8601

logger = logging.getLogger(__name__)


def make_absolute_uri(path: str, request: Optional[HttpRequest] = None) -> str:
    if request is not None:
        return request.build_absolute_uri(path)

    site = Site.objects.get_current()
    protocol = "https" if getattr(settings, "IS_HTTPS", True) else "http"
    return f"{protocol}://{site.domain}{path}"


def to_date(value):
    tmp_datetime = parseDateTimeValue(value)
    if tmp_datetime:
        return tmp_datetime.date()
    return None


def to_datetime(value):
    tmp_datetime = parseDateTimeValue(value)
    return tmp_datetime


def parseDateTimeValue(value):
    """
    Utility function to return a datetime from a string.
    """
    if type(value) == str:
        return iso8601.parse_date(value)
    elif type(value) == int:
        return datetime.fromtimestamp(value / 1000)
    else:
        return None


def make_enkelvoudiginformatieobject_dataclass(cmis_doc, dataclass, skip_deleted=False):
    if cmis_doc.verwijderd and not skip_deleted:
        # Return None if document is deleted.
        return None

    path = reverse(
        "enkelvoudiginformatieobject-detail",
        kwargs={"version": "1", "uuid": cmis_doc.versionSeriesId},
    )
    url = make_absolute_uri(path)

    download_link = reverse(
        "enkelvoudiginformatieobject-download",
        kwargs={"version": "1", "uuid": cmis_doc.versionSeriesId},
    )
    download_url = make_absolute_uri(download_link)

    return dataclass(
        url=url,
        inhoud=download_url,
        creatiedatum=to_date(cmis_doc.creatiedatum),
        ontvangstdatum=to_date(cmis_doc.ontvangstdatum),
        verzenddatum=to_date(cmis_doc.verzenddatum),
        integriteit_datum=to_date(cmis_doc.integriteit_datum),
        ondertekening_datum=to_date(cmis_doc.ondertekening_datum),
        titel=cmis_doc.titel,
        identificatie=cmis_doc.identificatie,
        bronorganisatie=cmis_doc.bronorganisatie,
        vertrouwelijkheidaanduiding=cmis_doc.vertrouwelijkheidaanduiding,
        auteur=cmis_doc.auteur,
        # FIXME -> status must be saved in EIO
        status=cmis_doc.status or "gearchiveerd",
        beschrijving=cmis_doc.beschrijving or "",
        indicatie_gebruiksrecht=cmis_doc.indicatie_gebruiksrecht,
        ondertekening_soort=cmis_doc.ondertekening_soort,
        informatieobjecttype=cmis_doc.informatieobjecttype,
        formaat=cmis_doc.formaat or "",
        taal=cmis_doc.taal,
        bestandsnaam=cmis_doc.bestandsnaam or "",
        link=cmis_doc.link or "",
        integriteit_algoritme=cmis_doc.integriteit_algoritme,
        integriteit_waarde=cmis_doc.integriteit_waarde,
        bestandsomvang=cmis_doc.bestandsomvang,
        begin_registratie=to_datetime(
            cmis_doc.begin_registratie or cmis_doc.creationDate
        ),
        versie=cmis_doc.versie,
        locked=bool(cmis_doc.versionSeriesCheckedOutId),
    )


def make_objectinformatieobject_dataclass(cmis_doc, dataclass, skip_deleted=False):
    if cmis_doc.verwijderd and not skip_deleted:
        # Return None if document is deleted.
        return None

    path = reverse(
        "objectinformatieobject-detail",
        kwargs={"version": "1", "uuid": cmis_doc.versionSeriesId},
    )
    url = make_absolute_uri(path)

    eio_path = reverse(
        "enkelvoudiginformatieobject-detail",
        kwargs={"version": "1", "uuid": cmis_doc.versionSeriesId},
    )
    eio_url = make_absolute_uri(eio_path)

    return dataclass(
        url=url,
        informatieobject=eio_url,
        object=cmis_doc.object,
        object_type=cmis_doc.object_type,
        aard_relatie=cmis_doc.aard_relatie,
        titel=cmis_doc.connectie__titel,
        beschrijving=cmis_doc.connectie__beschrijving,
        registratiedatum=cmis_doc.registratiedatum,
    )
