from __future__ import unicode_literals

from django.db import models
from django.utils.timezone import now

# Create your models here.


class Family(models.Model):
    responsible_name = models.TextField(null=False)

    def __str__(self):
        return self.responsible_name


class Patient(models.Model):
    id = models.AutoField(primary_key=True)
    # Full Name
    name = models.TextField()
    # Day of Birth
    dob = models.DateField()

    family = models.ForeignKey(Family, null=True)

    def __str__(self):
        return " de ".join([self.name, self.family.responsible_name])

    #TODO: moar info


class Visit(models.Model):
    # TODO: check UTC policy
    # https://docs.djangoproject.com/en/1.10/ref/models/fields/#django.db.models.DateField.auto_now_add
    date = models.DateTimeField(default=now)
    patient = models.ForeignKey(Patient)

    def __str__(self):
        return "{} - {}".format(self.patient.name, self.date)


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

    visit = models.ForeignKey(Visit)  # TODO: check this relationship
