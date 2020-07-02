import os

from django.test import TestCase

import responses
from vng_api_common.models import APICredential

from drc_cmis.client import CMISDRCClient

from .mixins import DMSMixin

RESPONSES_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "responses")


def open_file(filename: str) -> str:
    path = os.path.join(RESPONSES_DIR, filename)
    return open(path, "rb")


class NotificationTests(DMSMixin, TestCase):
    def setUp(self):
        self.cmis_client = CMISDRCClient()

    def test_notifications_empty_dict(self):
        from drc_cmis.notifications import default

        with self.assertRaises(KeyError):
            default.handle({})

    def test_notifications_default(self):
        from drc_cmis.notifications import default

        default.handle({"kanaal": "random"})

    def test_notifications(self):
        from drc_cmis.notifications import default

        default.handle({"kanaal": "zaken"})

    @responses.activate
    def test_notifications_fully_filled(self):
        from drc_cmis.notifications import default

        with open_file("ztc-openapi.yaml") as resp_file:
            responses.add(
                responses.GET,
                "https://ref.tst.vng.cloud/ztc/api/v1/schema/openapi.yaml?v=3",
                body=resp_file.read(),
                status=200,
            )
        with open_file("ztc-zaaktype.json") as resp_file:
            responses.add(
                responses.GET,
                "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                body=resp_file.read(),
                status=200,
            )
        with open_file("zrc-openapi.yaml") as resp_file:
            responses.add(
                responses.GET,
                "https://ref.tst.vng.cloud/zrc/api/v1/zaken/schema/openapi.yaml?v=3",
                body=resp_file.read(),
                status=200,
            )
        with open_file("zrc-zaak.json") as resp_file:
            responses.add(
                responses.GET,
                "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
                body=resp_file.read(),
                status=200,
            )
        with open_file("alfresco-get-results.json") as resp_file:
            responses.add(
                responses.GET,
                "http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser/root",
                body=resp_file.read(),
                status=200,
                content_type="application/json",
            )
        with open_file("alfresco-results.json") as resp_file:
            responses.add(
                responses.POST,
                "http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser/root",
                body=resp_file.read(),
                status=200,
            )
        with open_file("alfresco-results.json") as resp_file:
            responses.add(
                responses.POST,
                "http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
                body=resp_file.read(),
                status=200,
            )

        APICredential.objects.create(
            api_root="https://ref.tst.vng.cloud/zrc/",
            label="ZRC",
            client_id="test",
            secret="test",
        )
        APICredential.objects.create(
            api_root="https://ref.tst.vng.cloud/ztc/",
            label="ZTC",
            client_id="test",
            secret="test",
        )

        data = {
            "kanaal": "zaken",
            "hoofdObject": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "actie": "create",
            "resource": "zaak",
            "resource_url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "aanmaakdatum": "2018-01-01T17:00:00Z",
            "kenmerken": {
                "bron": "082096752011",
                "zaaktype": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                "vertrouwelijkeidaanduiding": "openbaar",
            },
        }

        default.handle(data)

        case_folder = self.cmis_client.get_folder_from_case_url(
            "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid"
        )
        self.assertIsNotNone(case_folder)

    @responses.activate
    def test_notifications_no_resource_url(self):
        with open_file("alfresco-results-empty.json") as resp_file:
            responses.add(
                responses.POST,
                "http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
                body=resp_file.read(),
                status=200,
            )

        from drc_cmis.notifications import default

        data = {
            "kanaal": "zaken",
            "hoofdObject": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "actie": "create",
            "resource": "zaak",
            "aanmaakdatum": "2018-01-01T17:00:00Z",
            "kenmerken": {
                "bron": "082096752011",
                "zaaktype": "https://ref.tst.vng.cloud/ztc/api/v1/catalogussen/f7afd156-c8f5-4666-b8b5-28a4a9b5dfc7/zaaktypen/0119dd4e-7be9-477e-bccf-75023b1453c1",
                "vertrouwelijkeidaanduiding": "openbaar",
            },
        }

        default.handle(data)

        case_folder = self.cmis_client.get_folder_from_case_url(
            "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid"
        )
        self.assertIsNone(case_folder)

    @responses.activate
    def test_notifications_no_zaaktype(self):
        with open_file("alfresco-results-empty.json") as resp_file:
            responses.add(
                responses.POST,
                "http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
                body=resp_file.read(),
                status=200,
            )

        from drc_cmis.notifications import default

        data = {
            "kanaal": "zaken",
            "hoofdObject": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "actie": "create",
            "resource": "zaak",
            "resource_url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "aanmaakdatum": "2018-01-01T17:00:00Z",
            "kenmerken": {
                "bron": "082096752011",
                "vertrouwelijkeidaanduiding": "openbaar",
            },
        }

        default.handle(data)

        case_folder = self.cmis_client.get_folder_from_case_url(
            "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid"
        )
        self.assertIsNone(case_folder)

    @responses.activate
    def test_notifications_no_kenmerken(self):
        with open_file("alfresco-results-empty.json") as resp_file:
            responses.add(
                responses.POST,
                "http://localhost:8082/alfresco/api/-default-/public/cmis/versions/1.1/browser",
                body=resp_file.read(),
                status=200,
            )

        from drc_cmis.notifications import default

        data = {
            "kanaal": "zaken",
            "hoofdObject": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "actie": "create",
            "resource": "zaak",
            "resource_url": "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid",
            "aanmaakdatum": "2018-01-01T17:00:00Z",
        }

        default.handle(data)

        case_folder = self.cmis_client.get_folder_from_case_url(
            "https://ref.tst.vng.cloud/zrc/api/v1/zaken/random-zaak-uuid"
        )
        self.assertIsNone(case_folder)
