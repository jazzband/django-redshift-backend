.. release procedure

Procedure:

1. check CI status testing result: https://github.com/jazzband/django-redshift-backend/actions?query=workflow%3ATest
2. update release version/date in ``CHANGES.rst``
3. create Github release, tagging with version name that MUST following semver. e.g.: ``git tag 1.0.1``
4. publish Github release to invoke release process in Github Actions.
5. approve release files. please check your email or https://jazzband.co/projects/django-redshift-backend
6. check PyPI page: https://pypi.org/p/django-redshift-backend
7. bump version in ``CHANGES.rst`` and commit/push them onto GitHub

