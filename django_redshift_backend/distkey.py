from __future__ import absolute_import

from django.db.models import Index


class DistKey(Index):
    """A single-field index denoting the distkey for a model.

    Use as follows:

      class MyModel(models.Model):
      ...

      class Meta:
          indexes = [DistKey(fields=['customer_id'])]
    """
    pass
