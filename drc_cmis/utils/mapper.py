ZAAKTYPE_MAP = {
    "object_type_id": None,
    "url": None,
    "identificatie": None,
}

ZAAK_MAP = {
    "object_type_id": None,
    "url": None,
    "identificatie": None,
    "zaaktype": None,
    "bronorganisatie": None,
}

DOCUMENT_MAP = {
    "object_type_id": None,
    "uuid": None,
    "identificatie": None,
    "bronorganisatie": None,
    "creatiedatum": None,
    "titel": None,
    "vertrouwelijkheidaanduiding": None,
    "auteur": None,
    "status": None,
    "beschrijving": None,
    "ontvangstdatum": None,
    "verzenddatum": None,
    "indicatie_gebruiksrecht": None,
    "ondertekening_soort": None,
    "ondertekening_datum": None,
    "informatieobjecttype": None,
    "formaat": None,
    "taal": None,
    "bestandsnaam": None,
    "bestandsomvang": None,
    "versie": None,
    # "inhoud": "drc:",
    "link": None,
    "integriteit_algoritme": None,
    "integriteit_waarde": None,
    "integriteit_datum": None,
    "verwijderd": None,
    "begin_registratie": None,
    "lock": None,
    "kopie_van": None,
}

GEBRUIKSRECHTEN_MAP = {
    "object_type_id": None,
    "uuid": None,
    "informatieobject": None,
    "omschrijving_voorwaarden": None,
    "startdatum": None,
    "einddatum": None,
    "kopie_van": None,
}

OBJECTINFORMATIEOBJECT_MAP = {
    "object_type_id": None,
    "uuid": None,
    "informatieobject": None,
    "object_type": None,
    "zaak": None,
    "besluit": None,
    "verzoek": None,
}

VERZENDING_MAP = {
    "object_type_id": None,
    "uuid": None,
    "informatieobject": None,
    "betrokkene": None,
    "aard_relatie": None,
    "toelichting": None,
    "ontvangstdatum": None,
    "verzenddatum": None,
    "contact_persoon": None,
    "contactpersoonnaam": None,
    "binnenlands_correspondentieadres_huisletter": None,
    "binnenlands_correspondentieadres_huisnummer": None,
    "binnenlands_correspondentieadres_huisnummer_toevoeging": None,
    "binnenlands_correspondentieadres_naam_openbare_ruimte": None,
    "binnenlands_correspondentieadres_postcode": None,
    "binnenlands_correspondentieadres_woonplaatsnaam": None,
    "buitenlands_correspondentieadres_adres_buitenland_1": None,
    "buitenlands_correspondentieadres_adres_buitenland_2": None,
    "buitenlands_correspondentieadres_adres_buitenland_3": None,
    "buitenlands_correspondentieadres_land_postadres": None,
    "correspondentie_postadres_postbus_of_antwoord_nummer": None,
    "correspondentie_postadres_postcode": None,
    "correspondentie_postadres_postadrestype": None,
    "correspondentie_postadres_woonplaatsnaam": None,
    "faxnummer": None,
    "emailadres": None,
    "mijn_overheid": None,
    "telefoonnummer": None,
    "kopie_van": None,
}


REVERSE_ZAAKTYPE_MAP = {value: key for key, value in ZAAKTYPE_MAP.items()}
REVERSE_ZAAK_MAP = {value: key for key, value in ZAAK_MAP.items()}
REVERSE_DOCUMENT_MAP = {value: key for key, value in DOCUMENT_MAP.items()}
REVERSE_GEBRUIKSRECHTEN_MAP = {value: key for key, value in GEBRUIKSRECHTEN_MAP.items()}
REVERSE_OBJECTINFORMATIEOBJECT_MAP = {
    value: key for key, value in OBJECTINFORMATIEOBJECT_MAP.items()
}
REVERSE_VERZENDING_MAP = {value: key for key, value in VERZENDING_MAP.items()}


def mapper(drc_name, type="document"):
    if type == "zaaktype":
        return ZAAKTYPE_MAP.get(drc_name, None)
    if type == "zaak":
        return ZAAK_MAP.get(drc_name, None)
    if type == "document":
        return DOCUMENT_MAP.get(drc_name, None)
    if type == "gebruiksrechten":
        return GEBRUIKSRECHTEN_MAP.get(drc_name, None)
    if type == "oio":
        return OBJECTINFORMATIEOBJECT_MAP.get(drc_name, None)
    if type == "verzending":
        return VERZENDING_MAP.get(drc_name, None)
    return None


def reverse_mapper(cmis_name, type="document"):
    if type == "zaaktype":
        return REVERSE_ZAAKTYPE_MAP.get(cmis_name, None)
    if type == "zaak":
        return REVERSE_ZAAK_MAP.get(cmis_name, None)
    if type == "document":
        return REVERSE_DOCUMENT_MAP.get(cmis_name, None)
    if type == "gebruiksrechten":
        return REVERSE_GEBRUIKSRECHTEN_MAP.get(cmis_name, None)
    if type == "oio":
        return REVERSE_OBJECTINFORMATIEOBJECT_MAP.get(cmis_name, None)
    if type == "verzending":
        return REVERSE_VERZENDING_MAP.get(cmis_name, None)
    return None
