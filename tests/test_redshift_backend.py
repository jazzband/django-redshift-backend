# -*- coding: utf-8 -*-

import unittest

from django.db import connections


class DatabaseWrapperTest(unittest.TestCase):

    def test_load_redshift_backend(self):
        db = connections['default']
        self.assertIsNotNone(db)
