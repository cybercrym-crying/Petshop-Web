from django.db import models


# OOP: ABSTRAKSI + PEWARISAN - model abstrak (tanpa tabel sendiri) yang
# diwarisi model lain untuk mendapat created_at & updated_at.
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
