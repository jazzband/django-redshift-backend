===========
Development
===========

Code of Conduct
===============

Please refer :doc:`code-of-conduct`.

Issue Reporting
===============

**To Be Written**

* https://github.com/shimizukawa/django-redshift-backend/issues

Testing
=======

Install these packages before testing:

* tox-1.8 or later
* virtualenv-15.0.1 or later
* pip-10.0.3 or later

Run test
--------

Just run tox::

   $ tox

tox have several sections for testing.

CI (Continuous Integration)
----------------------------

All tests will be run on Travis CI service.

* https://travis-ci.org/shimizukawa/django-redshift-backend


Pull Request
============

**To Be Written**

* https://github.com/shimizukawa/django-redshift-backend/pulls


Releasing
=========

New package version
-------------------

The django-redshift-backend package will be uploaded to PyPI: https://pypi.org/project/django-redshift-backend/.

Here is a release procefure for releasing.

.. include:: ../checklist.rst


Updated documentation
---------------------

Sphinx documentation under ``doc/`` directory on the master branch will be automatically uploaded into ReadTheDocs: http://django-redshift-backend.rtfd.io/.

