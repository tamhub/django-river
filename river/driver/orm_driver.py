from django.db.models import  Q

from river.driver.river_driver import RiverDriver



class OrmDriver(RiverDriver):

    def get_available_approvals(self, as_user):
        # Get authorized transition approval metadata
        authorized_approvals = self._authorized_approvals(as_user)

        return authorized_approvals

    def _authorized_approvals(self, as_user):
        group_q = Q()
        for g in as_user.groups.all():
            group_q = group_q | Q(groups__in=[g])


        from river.models import TransitionApprovalMeta
        return TransitionApprovalMeta.objects.filter(
            Q(workflow=self.workflow) &
            (
                    (Q(groups__isnull=True) | group_q)
            )
        )

