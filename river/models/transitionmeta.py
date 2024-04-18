from __future__ import unicode_literals

from django.db import models
from django.db.models import PROTECT, CASCADE

try:
    # Try to import gettext_lazy for Django 3.0 and newer
    from django.utils.translation import gettext_lazy as _
except ImportError:
    # Fall back to ugettext_lazy for older Django versions
    from django.utils.translation import ugettext_lazy as _

from river.models import State, Workflow
from river.models.base_model import BaseModel


class TransitionMeta(BaseModel):
    class Meta:
        app_label = 'river'
        verbose_name = _("Transition Meta")
        verbose_name_plural = _("Transition Meta")
        unique_together = [('workflow', 'source_state', 'destination_state')]

    workflow = models.ForeignKey(Workflow, verbose_name=_("Workflow"), related_name='transition_metas', on_delete=CASCADE)
    source_state = models.ForeignKey(State, verbose_name=_("Source State"), related_name='transition_meta_as_source', on_delete=CASCADE)
    destination_state = models.ForeignKey(State, verbose_name=_("Destination State"), related_name='transition_meta_as_destination', on_delete=CASCADE)

    def __str__(self):
        return 'Field Name:%s, %s -> %s' % (
            self.workflow,
            self.source_state,
            self.destination_state
        )