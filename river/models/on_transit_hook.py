from django.db import models
from django.db.models import CASCADE
try:
    # Try to import gettext_lazy for Django 3.0 and newer
    from django.utils.translation import gettext_lazy as _
except ImportError:
    # Fall back to ugettext_lazy for older Django versions
    from django.utils.translation import ugettext_lazy as _

from river.models import TransitionMeta, Transition
from river.models.hook import Hook


class OnTransitHook(Hook):
    class Meta:
        unique_together = [('callback_function', 'workflow', 'transition_meta', 'content_type', 'object_id', 'transition')]

    transition_meta = models.ForeignKey(TransitionMeta, verbose_name=_("Transition Meta"), related_name='on_transit_hooks', on_delete=CASCADE)
    transition = models.ForeignKey(Transition, verbose_name=_("Transition"), related_name='on_transit_hooks', null=True, blank=True, on_delete=CASCADE)