====================================
Redshift database backend for Django
====================================

This is a `Amazon Redshift`_ database backend for Django_.

.. image:: https://img.shields.io/readthedocs/django-redshift-backend/master.svg
   :alt: Read the Docs (master)
   :target: http://django-redshift-backend.rtfd.io/

.. image:: https://img.shields.io/pypi/v/django-redshift-backend.svg
   :alt: PyPI
   :target: http://pypi.org/p/django-redshift-backend

.. image:: https://img.shields.io/pypi/pyversions/django-redshift-backend.svg
   :alt: PyPI - Python Version

.. image:: https://img.shields.io/pypi/djversions/django-redshift-backend.svg
   :alt: PyPI - Django Version

.. image:: https://img.shields.io/github/license/shimizukawa/django-redshift-backend.svg
   :alt: GitHub
   :target: https://github.com/shimizukawa/django-redshift-backend/blob/master/LICENSE

.. image:: https://img.shields.io/travis/shimizukawa/django-redshift-backend/master.svg
   :alt: Travis (.org) branch
   :target: https://travis-ci.org/shimizukawa/django-redshift-backend

.. image:: https://img.shields.io/github/stars/shimizukawa/django-redshift-backend.svg?style=social&label=Stars
   :alt: GitHub stars
   :target: https://github.com/shimizukawa/django-redshift-backend

.. _Amazon Redshift: https://aws.amazon.com/jp/redshift/
.. _Django: https://www.djangoproject.com/

Documentation
=============

- http://django-redshift-backend.rtfd.io/

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

For more information, please refer: Documentation_


LICENSE
=======
Apache Software License


.. CHANGES.rst will be concatenated here by setup.py


