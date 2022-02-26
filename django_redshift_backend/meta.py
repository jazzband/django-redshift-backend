from django.db.models import Index


class DistKey(Index):
    """A single-field index denoting the distkey for a model.

    Use as follows:

      class MyModel(models.Model):
      ...

      class Meta:
          indexes = [DistKey(fields=['customer_id'])]
    """
    def deconstruct(self):
        path, expressions, kwargs = super().deconstruct()
        path = path.replace('django_redshift_backend.meta', 'django_redshift_backend')
        return (path, expressions, kwargs)


class SortKey(str):
    """A SORTKEY in Redshift, also valid as ordering in Django.

    https://docs.djangoproject.com/en/dev/ref/models/options/#django.db.models.Options.ordering

    Use as follows:

      class MyModel(models.Model):
      ...

      class Meta:
          ordering = [SortKey('created_at'), SortKey('-id')]
    """
    def __hash__(self):
        return hash(str(self))

    def deconstruct(self):
        path = '%s.%s' % (self.__class__.__module__, self.__class__.__name__)
        path = path.replace('django_redshift_backend.meta', 'django_redshift_backend')
        return (path, [str(self)], {})

    def __eq__(self, other):
        if self.__class__ == other.__class__:
            return self.deconstruct() == other.deconstruct()
        return NotImplemented
