===================
Alfresco on Docker
===================

Creates a container that runs Alfresco Community Edition.

Usage
=====

To use this with your project you need to follow these steps:

#. Go to this directory::

    $ cd alfresco

#. Run docker-compose in the background::

    $ docker-compose up -d

#. If this is the first time, it will take a while for Alfresco to be
   downloaded, installed and configured.

Locations
=========

#. You can find the Alfresco installation at::

    http://localhost:8080/
    # The default username/password are: admin/admin

#. You can find the CMIS 1.1 Browser binding endpoint at::

    http://localhost:8082/alfresco/cmisatom

#. You can find the CMIS 1.0 SOAP binding endpoint at::

    http://localhost:8082/alfresco/cmisws/cmis?wsdl


Content model and extension
===========================

See https://github.com/open-zaak/alfresco-content-model for the image with custom
content model and extension configuration.
