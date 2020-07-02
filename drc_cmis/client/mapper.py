ZAAKTYPE_MAP = {
    "url": "drc:zaaktype__url",
    "identificatie": "drc:zaaktype__identificatie",
}

ZAAK_MAP = {
    "url": "drc:zaak__url",
    "identificatie": "drc:zaak__identificatie",
    "zaaktype": "drc:zaak__zaaktypeurl",
    "bronorganisatie": "drc:zaak__bronorganisatie",
}


DOCUMENT_MAP = {
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
}

GEBRUIKSRECHTEN_MAP = {
    "informatieobject": None,
    "omschrijving_voorwaarden": None,
    "startdatum": None,
    "einddatum": None,
}

OBJECTINFORMATIEOBJECT_MAP = {
    "informatieobject": None,
    "object_type": None,
    "zaak": None,
    "besluit": None,
}

CONNECTION_MAP = {
    "object": "drc:connectie__zaakurl",
    "object_type": "drc:connectie__objecttype",
    "aard_relatie": "drc:connectie__aardrelatieweergave",
    "titel": "drc:connectie__titel",
    "beschrijving": "drc:connectie__beschrijving",
    "registratiedatum": "drc:connectie__registratiedatum",
}

REVERSE_ZAAKTYPE_MAP = {value: key for key, value in ZAAKTYPE_MAP.items()}
REVERSE_ZAAK_MAP = {value: key for key, value in ZAAK_MAP.items()}
REVERSE_DOCUMENT_MAP = {value: key for key, value in DOCUMENT_MAP.items()}
REVERSE_CONNECTION_MAP = {value: key for key, value in CONNECTION_MAP.items()}
REVERSE_GEBRUIKSRECHTEN_MAP = {value: key for key, value in GEBRUIKSRECHTEN_MAP.items()}
REVERSE_OBJECTINFORMATIEOBJECT_MAP = {
    value: key for key, value in OBJECTINFORMATIEOBJECT_MAP.items()
}


def mapper(drc_name, type="document"):
    if type == "document":
        return DOCUMENT_MAP.get(drc_name, None)
    if type == "connection":
        return CONNECTION_MAP.get(drc_name, None)
    if type == "zaaktype":
        return ZAAKTYPE_MAP.get(drc_name, None)
    if type == "zaak":
        return ZAAK_MAP.get(drc_name, None)
    if type == "gebruiksrechten":
        return GEBRUIKSRECHTEN_MAP.get(drc_name, None)
    if type == "objectinformatieobject":
        return OBJECTINFORMATIEOBJECT_MAP.get(drc_name, None)
    return None


def reverse_mapper(cmis_name, type="document"):
    if type == "document":
        return REVERSE_DOCUMENT_MAP.get(cmis_name, None)
    if type == "connection":
        return REVERSE_CONNECTION_MAP.get(cmis_name, None)
    if type == "zaaktype":
        return REVERSE_ZAAKTYPE_MAP.get(cmis_name, None)
    if type == "zaak":
        return REVERSE_ZAAK_MAP.get(cmis_name, None)
    if type == "gebruiksrechten":
        return REVERSE_GEBRUIKSRECHTEN_MAP.get(cmis_name, None)
    if type == "objectinformatieobject":
        return REVERSE_OBJECTINFORMATIEOBJECT_MAP.get(cmis_name, None)
    return None
