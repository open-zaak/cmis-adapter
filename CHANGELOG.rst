=========
Changelog
=========

1.5.1 (2022-09-01)
------------------

Fixed ``None`` / empty values in the WEBSERVICE binding.

1.5.0 (2022-08-24)
------------------

* Support writes for ``bestandsomvang`` attribute
* Allow writing of empty files
* CI: Use same Alfresco docker image in CI as Open Zaak
* Dropped support for Django 2.2

.. note:: This update requires the CMIS content model to be updated with a writeable
   ``Document.bestandsomvang`` attribute.

1.4.0 (2022-07-26)
------------------

Added support for OIO type "Verzoek"

1.3.2 (2022-07-26)
------------------

Added missing migration for CMISConfig.time_zone

1.3.1 (2022-06-09)
------------------

* Documented supported/lack of support of various SQL query types with DMS vendors
* Implemented re-arranging of documents on ZIO delete operations (#32)

1.3.0 (2022-03-10)
------------------

Added support for Django 3.2 and Python 3.9+, no functional changes.

1.2.6 (2021-05-12)
------------------

Performance tuning release

* Cache CMISConfig to prevent repeated database lookups.
* Cache retrieval of "getRepositoryInfo" to prevent excessive CMIS requests (#56)
* Various performance improvements (#58)

1.2.5 (2021-04-29)
------------------

Bugfix release

* Fix thread-local bug

1.2.4 (2021-04-29)
------------------

Bugfix and performance tuning release

* Fixed handling empty identificatie fields (#52)
* Use connection pooling in both CMIS bindings to speed up
  performance (#54)

1.2.3 (2021-03-22)
------------------

More performance improvements

* Avoid having to fetch some data by requiring it upfront
* Fixed creating documents without providing the identification upfront
* Various performance fixes by caching internal data structures

1.2.2 (2021-03-08)
------------------

Performance improvement in checking the main repo ID.

1.2.1 (2021-02-05)
------------------

Fixed broken CMIS Configuration admin when URL mapping feature is disabled.

1.2.0 (2021-02-04)
------------------

This release fixes a number of bugs and adds some new functionality.

* Added setting to configure main repository ID
* Improved readability of logging statements for webservice calls
* Added a URL mapper to deal with URL-length limitations (#37)
* Fixed being able to update ``Gebruiksrechten`` resource
* Fixed missing filename extensions in CMIS requests (#40)

1.1.2 (2020-12-10)
------------------

Bugfix release

* Fixed missing unique-together validation on identificatie-bronorganisatie
* Fixed packaging, now Javascript is included
* Fixed file content extraction for Corsa DMS
* Fixed CMIS queries w/r to duplicate folders
* Switched CI from Travis to Github Actions

1.1.1 (2020-09-06)
------------------

* Fixed binary content uploads (such as PDFs) in SOAP binding (#24)
* Added more logging for all calls (#26)

1.1.0 (2020-08-26)
------------------

* Added configurable paths to be used in the DMS when adding documents.
* Added connection status in admin.
* Fixed code coverage report.
* Fixed minor Corsa compatibility issues.
* Fixed minor documentation issues.

1.0.0 (2020-08-25)
------------------

Version 1.0.0 is a major overhaul of the project to ensure stability and to
allow for easier integration of newer Documenten API versions. Thanks to the
municipality of Utrecht and the municipality of Súdwest-Fryslân who made this
effort possible.

* Added support for CMIS 1.0 SOAP bindings
* Major rewrite of the code to support multiple CMIS bindings
* Renamed from "GEMMA DRC-CMIS" (`gemma-drc-cmis`) to "Documenten API CMIS
  adapter" (`cmis-adapter`)
* Code repository was moved from `GemeenteUtrecht` to `open-zaak` and now lives
  under the maintenance of the Open Zaak project team.
* License changed from MIT (0.5.0) to EUPL 1.2

0.5.0 (2019-05-06)
------------------

Last release under the control of the municipality of Utrecht.

After it's initial release on PyPI on April 16, 2019, several minor and patch
versions were released. These releases went mostly undocumented and we refer to
https://github.com/open-zaak/cmis-adapter/releases for a complete list.
