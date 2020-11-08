=====
Basic
=====

Installation
============

Please install django-redshift-backend with using pip (8.1.1 or later).

.. code-block:: bash

   $ pip install django-redshift-backend

This backend requires ``psycopg2``, which may be installed from source or wheel (pre-built binaries).
If you don't want to specify it separately, you may install it using extra:

.. code-block:: bash

   # For pre-built binary
   $ pip install django-redshift-backend[psycopg2-binary]

   # For the source distribution
   $ pip install django-redshift-backend[psycopg2]

Please refer to the `psycopg2 documentation`_ for more details on the topic.

.. _psycopg2 documentation: https://www.psycopg.org/docs/install.html#psycopg-vs-psycopg-binary

Django settings
===============

ENGINE for DATABASES is 'django_redshift_backend'. You can set the name in your settings.py as::

   DATABASES = {
       'default': {
           'ENGINE': 'django_redshift_backend',
           'NAME': '<your database name>',
           'USER': '<your database username>',
           'PASSWORD': '<your database password>',
           'HOST': '<your database hostname>',
           'PORT': '5439',
       }
   }

For more information, please refer :doc:`refs`.

