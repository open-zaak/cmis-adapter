from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class Id:
    pass


class Url:
    pass


class QueriableUrl:
    pass


@dataclass
class EnkelvoudigInformatieObject:
    version_label: Decimal
    object_type_id: Id
    name: str
    integriteit_waarde: str
    titel: str
    bestandsnaam: str
    bestandsomvang: int
    formaat: str
    ondertekening_soort: str
    beschrijving: str
    identificatie: str
    verzenddatum: date
    taal: str
    indicatie_gebruiksrecht: str
    verwijderd: bool
    status: str
    ontvangstdatum: date
    informatieobjecttype: QueriableUrl
    auteur: str
    vertrouwelijkheidaanduiding: str
    begin_registratie: datetime
    ondertekening_datum: date
    bronorganisatie: str
    integriteit_datum: date
    link: Url
    creatiedatum: date
    versie: Decimal
    lock: str
    uuid: str
    integriteit_algoritme: str
    kopie_van: str


@dataclass
class Gebruiksrechten:
    uuid: str
    version_label: Decimal
    object_type_id: Id
    name: str
    einddatum: datetime
    omschrijving_voorwaarden: str
    informatieobject: QueriableUrl
    startdatum: datetime
    kopie_van: str


@dataclass
class Oio:
    uuid: str
    version_label: Decimal
    object_type_id: Id
    name: str
    object_type: str
    besluit: QueriableUrl
    zaak: QueriableUrl
    verzoek: QueriableUrl
    informatieobject: QueriableUrl


@dataclass
class Folder:
    object_type_id: Id


@dataclass
class ZaakFolderData:
    object_type_id: Id
    url: QueriableUrl
    identificatie: str
    zaaktype: QueriableUrl
    bronorganisatie: str


@dataclass
class ZaakTypeFolderData:
    object_type_id: Id
    url: QueriableUrl
    identificatie: str


CONVERTER = {
    int: "propertyInteger",
    str: "propertyString",
    date: "propertyDateTime",
    datetime: "propertyDateTime",
    Decimal: "propertyDecimal",
    bool: "propertyBoolean",
    Id: "propertyId",
    Url: "propertyString",
    QueriableUrl: "propertyString",
}


def get_type(model: type, name: str) -> type:
    """Return the type of a field"""
    type_annotations = getattr(model, "__annotations__")
    if type_annotations.get(name):
        return type_annotations.get(name)


def get_cmis_type(model: type, name: str) -> str:
    """Get the CMIS type of a property"""
    type_annotations = getattr(model, "__annotations__")
    property_type = type_annotations[name]
    return CONVERTER[property_type]
