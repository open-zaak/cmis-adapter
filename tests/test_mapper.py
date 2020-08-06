from django.test import TestCase

from drc_cmis.utils.mapper import mapper, reverse_mapper


class MapperTests(TestCase):
    def test_mapper_get_document(self):
        self.assertEqual(mapper("identificatie"), "drc:document__identificatie")
        self.assertEqual(
            mapper("identificatie", "document"), "drc:document__identificatie"
        )

    def test_mapper_get_gebruiksrechten(self):
        self.assertIs(mapper("informatieobject"), None)
        self.assertEqual(
            mapper("informatieobject", "gebruiksrechten"),
            "drc:gebruiksrechten__informatieobject",
        )

    def test_mapper_get_oio(self):
        self.assertIs(mapper("informatieobject"), None)
        self.assertEqual(mapper("informatieobject", "oio"), "drc:oio__informatieobject")

    def test_mapper_get_unknown(self):
        self.assertIsNone(mapper("identificatie", "unknown"))

    def test_mapper_get_zaaktype(self):
        self.assertEqual(
            mapper("identificatie", "zaaktype"), "drc:zaaktype__identificatie"
        )

    def test_mapper_get_zaak(self):
        self.assertEqual(mapper("identificatie", "zaak"), "drc:zaak__identificatie")


class ReverseMapperTests(TestCase):
    def test_mapper_get_document(self):
        self.assertEqual(reverse_mapper("drc:document__identificatie"), "identificatie")
        self.assertEqual(
            reverse_mapper("drc:document__identificatie", "document"), "identificatie"
        )

    def test_mapper_get_gebruiksrechten(self):
        self.assertEqual(reverse_mapper("drc:gebruiksrechten__informatieobject"), None)
        self.assertEqual(
            reverse_mapper("drc:gebruiksrechten__informatieobject", "gebruiksrechten"),
            "informatieobject",
        )

    def test_mapper_get_oio(self):
        self.assertEqual(reverse_mapper("drc:oio__informatieobject"), None)
        self.assertEqual(
            reverse_mapper("drc:oio__informatieobject", "oio"), "informatieobject"
        )

    def test_mapper_get_unknown(self):
        self.assertIsNone(reverse_mapper("drc:document__identificatie", "unknown"))
