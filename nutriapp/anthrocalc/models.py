from __future__ import unicode_literals

from django.db import models
from django.utils.timezone import now

# Create your models here.


class Patient(models.Model):
    id = models.AutoField(primary_key=True)
    # Full Name
    name = models.TextField()
    # Day of Birth
    dob = models.DateField()
    #TODO: moar info


class Visit(models.Model):
    # TODO: check UTC policy
    # https://docs.djangoproject.com/en/1.10/ref/models/fields/#django.db.models.DateField.auto_now_add
    date = models.DateTimeField(default=now)
    patient = models.ForeignKey(Patient)


class Metric(models.Model):
    weight = models.FloatField()
    height = models.FloatField()
    standing_or_upright = models.NullBooleanField()
    # TODO: add moar metrics

    visit = models.ForeignKey(Visit)  # TODO: check this relationship


# A class for treatments or actions taken to fix the condition
class Action(models.Model):
    type = models.TextField()
    value = models.TextField()

    visit = models.ForeignKey(Visit) # TODO: check this relationship
