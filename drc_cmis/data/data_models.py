from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class Id:
    pass


@dataclass
class EnkelvoudigInformatieObject:
    version_label: Decimal
    object_type_id: Id
    name: str
    integriteitwaarde: str
    titel: str
    bestandsnaam: str
    formaat: str
    ondertekeningsoort: str
    beschrijving: str
    identificatie: str
    verzenddatum: date
    taal: str
    indicatiegebruiksrecht: str
    verwijderd: bool
    status: str
    ontvangstdatum: date
    informatieobjecttype: str
    auteur: str
    vertrouwelijkheidaanduiding: str
    integriteitalgoritme: str
    begin_registratie: datetime
    ondertekeningdatum: date
    bronorganisatie: str
    integriteitdatum: date
    link: str
    creatiedatum: date
    versie: Decimal
    lock: str


@dataclass
class Gebruiksrechten:
    version_label: Decimal
    object_type_id: Id
    name: str
    einddatum: datetime
    omschrijving_voorwaarden: str
    informatieobject: str
    startdatum: datetime


@dataclass
class Oio:
    version_label: Decimal
    object_type_id: Id
    name: str
    object_type: str
    besluit: str
    zaak: str
    informatieobject: str


CONVERTER = {
    str: "propertyString",
    date: "propertyDateTime",
    datetime: "propertyDateTime",
    Decimal: "propertyDecimal",
    bool: "propertyBoolean",
    Id: "propertyId",
}


def get_cmis_type(model: type, name: str) -> str:
    """Get the CMIS type of a property"""
    type_annotations = getattr(model, "__annotations__")
    property_type = type_annotations[name]
    return CONVERTER[property_type]
