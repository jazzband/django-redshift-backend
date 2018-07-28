====================================
Redshift database backend for Django
====================================

This is a `Amazon Redshift`_ database backend for Django_.

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


