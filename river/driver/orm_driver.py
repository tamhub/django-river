from django.contrib import auth
from django.db.models import Min, CharField, Q, F
from django.db.models.functions import Cast
from django_cte import With

from river.driver.river_driver import RiverDriver
from river.models import TransitionApproval, PENDING


class OrmDriver(RiverDriver):

    def get_available_approvals(self, as_user):
        # Get authorized transition approval metadata
        authorized_approvals = self._authorized_approvals(as_user)

        return authorized_approvals

    def _authorized_approvals(self, as_user):
        group_q = Q()
        for g in as_user.groups.all():
            group_q = group_q | Q(groups__in=[g])

        permissions = []
        for backend in auth.get_backends():
            permissions.extend(backend.get_all_permissions(as_user))

        permission_q = Q()
        for p in permissions:
            label, codename = p.split('.')
            permission_q = permission_q | Q(permissions__content_type__app_label=label, permissions__codename=codename)

        from river.models import TransitionApprovalMeta
        return TransitionApprovalMeta.objects.filter(
            Q(workflow=self.workflow) &
            (
                    (Q(permissions__isnull=True) | permission_q) &
                    (Q(groups__isnull=True) | group_q)
            )
        )

