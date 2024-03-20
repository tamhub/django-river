from uuid import uuid4

from django.db import models

from river.models.fields.state import StateField


class BasicTestModel(models.Model):
    id = models.BigAutoField(primary_key=True)
    test_field = models.CharField(max_length=50, null=True, blank=True)
    my_field = StateField()


class BasicTestModelWithoutAdmin(models.Model):
    id = models.BigAutoField(primary_key=True)
    test_field = models.CharField(max_length=50, null=True, blank=True)
    my_field = StateField()


class ModelWithoutStateField(models.Model):
    id = models.BigAutoField(primary_key=True)
    test_field = models.CharField(max_length=50, null=True, blank=True)


class ModelForSlowCase1(models.Model):
    id = models.BigAutoField(primary_key=True)
    status = StateField()


class ModelForSlowCase2(models.Model):
    id = models.BigAutoField(primary_key=True)
    status = StateField()


class ModelWithTwoStateFields(models.Model):
    id = models.BigAutoField(primary_key=True)
    status1 = StateField()
    status2 = StateField()


class ModelWithStringPrimaryKey(models.Model):
    custom_pk = models.CharField(max_length=200, primary_key=True, default=uuid4())
    status = StateField()