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
class Verzending:
    uuid: str
    object_type_id: Id
    betrokkene: Url

    aard_relatie: str
    toelichting: str
    ontvangstdatum: date
    verzenddatum: date
    contact_persoon: Url
    contactpersoonnaam: str
    binnenlands_correspondentieadres_huisletter: str
    binnenlands_correspondentieadres_huisnummer: int
    binnenlands_correspondentieadres_huisnummer_toevoeging: str
    binnenlands_correspondentieadres_naam_openbare_ruimte: str
    binnenlands_correspondentieadres_postcode: str
    binnenlands_correspondentieadres_woonplaatsnaam: str
    buitenlands_correspondentieadres_adres_buitenland_1: str
    buitenlands_correspondentieadres_adres_buitenland_2: str
    buitenlands_correspondentieadres_adres_buitenland_3: str
    buitenlands_correspondentieadres_land_postadres: Url
    correspondentie_postadres_postbus_of_antwoord_nummer: int
    correspondentie_postadres_postcode: str
    correspondentie_postadres_postadrestype: str
    correspondentie_postadres_woonplaatsnaam: str
    faxnummer: str
    emailadres: str
    mijn_overheid: bool
    telefoonnummer: str

    informatieobject: QueriableUrl
    kopie_van: str


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
