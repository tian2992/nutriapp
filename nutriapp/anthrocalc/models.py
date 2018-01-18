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

    family = models.ForeignKey(Family, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return " de ".join([self.name, self.family.responsible_name])

    #TODO: moar info


class MultipleVisit(models.Model):
    date = models.DateTimeField(default=now)


# A point in time where metrics are taken
class Visit(models.Model):
    # def __init__(self, *args, **kwargs):
    #     super(Visit, self).__init__(*args, **kwargs)
    #
    # def __init__(self, multiple_visit, *args, **kwargs):
    #     super(Visit, self).__init__(*args, **kwargs)
    #     self.date = multiple_visit.date

    # TODO: check UTC policy
    # https://docs.djangoproject.com/en/1.10/ref/models/fields/#django.db.models.DateField.auto_now_add
    date = models.DateTimeField(default=now)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)

    def __str__(self):
        return "{} - {}".format(self.patient.name, self.date)


class Metric(models.Model):
    weight = models.FloatField()
    height = models.FloatField()
    standing_or_upright = models.NullBooleanField()
    # TODO: add moar metrics

    visit = models.ForeignKey(Visit, on_delete=models.CASCADE)  # TODO: check this relationship


## A visit includes a set of metrics, given the living conditions
class EnvironmentMetric(models.Model):


    visit = models.ForeignKey(Visit, on_delete=models.CASCADE)


# Treatments or actions taken to fix the condition
class Action(models.Model):
    type = models.TextField()
    value = models.TextField()

    visit = models.ForeignKey(Visit, on_delete=models.CASCADE)  # TODO: check this relationship
