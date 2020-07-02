===========================
Documenten API CMIS adapter
===========================

:Version: 0.4.0
:Source: https://github.com/GemeenteUtrecht/gemma-drc-cmis
:Keywords: CMIS, Documenten API, VNG, Common Ground
:PythonVersion: 3.7

|build-status| |coverage| |black|

|python-versions| |django-versions| |pypi-version|

An adapter to manage `Documenten API`_ resources in a CMIS backend.

.. contents::

.. section-numbering::

Features
========

* CMIS 1.1 browser binding
* Store documents and metadata in a CMIS repository
* Supports reading and writing of documents
* Supports checking out/in of documents
* Supports custom data-model

Installation
============

Requirements
------------

* Python 3.7 or above
* setuptools 30.3.0 or above
* Django 2.2 or newer

Install
-------

.. code-block:: bash

    $ pip install drc-cmis


Add to installed apps

.. code-block:: python

    INSTALLED_APPS = [
        ...
        "drc_cmis",
        ...
    ]


And add the settings to enable it:

.. code-block:: python

    CMIS_ENABLED = True
    CMIS_DELETE_IS_OBLITERATE = True
    CMIS_MAPPER_FILE = /path/to/cmis_mapper.json

Usage
-----

.. todo:: provide proper documentation

.. |build-status| image:: https://travis-ci.org/GemeenteUtrecht/gemma-drc-cmis.svg?branch=master
    :target: https://travis-ci.org/GemeenteUtrecht/gemma-drc-cmis

.. |coverage| image:: https://codecov.io/gh/GemeenteUtrecht/gemma-drc-cmis/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/GemeenteUtrecht/gemma-drc-cmis
    :alt: Coverage status

.. |black| image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/drc-cmis.svg

.. |django-versions| image:: https://img.shields.io/pypi/djversions/drc-cmis.svg

.. |pypi-version| image:: https://img.shields.io/pypi/v/drc-cmis.svg
    :target: https://pypi.org/project/drc-cmis/

.. _Documenten API: https://vng-realisatie.github.io/gemma-zaken/standaard/documenten/index
