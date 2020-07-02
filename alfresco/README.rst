===================
Alfresco on Docker
===================

Creates a container that runs Alfresco Community.

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

#. You can find the CMIS endpoint at::

    http://localhost:8082/alfresco/cmisatom
