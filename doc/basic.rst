=====
Basic
=====

Installation
============

Please install django-redshift-backend with using pip (8.1.1 or later).

.. code-block:: bash

   $ pip install django-redshift-backend


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
           'OPTIONS': {
               'query_group': 'webapp',
           },
       }
   }


OPTIONS
-------

- ``query_group``: Set query_group_ to use `Work Load Management`_

.. _query_group: https://docs.aws.amazon.com/redshift/latest/dg/r_query_group.html
.. _Work Load Management: https://docs.aws.amazon.com/redshift/latest/dg/cm-c-implementing-workload-management.html

For more information, please refer :doc:`refs`.


