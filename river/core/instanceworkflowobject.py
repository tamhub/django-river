import logging
from functools import reduce

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone

from river.config import app_config
from river.models import (
    TransitionApproval, PENDING, State, APPROVED, Workflow, CANCELLED, Transition, DONE, JUMPED
)
from river.signals import ApproveSignal, TransitionSignal, OnCompleteSignal
from river.utils.error_code import ErrorCode
from river.utils.exceptions import RiverException
from django.core.exceptions import ValidationError

LOGGER = logging.getLogger(__name__)


class InstanceWorkflowObject:
    def __init__(self, workflow_object, field_name):
        self.workflow_object = workflow_object
        self.field_name = field_name
        self.class_workflow = getattr(workflow_object.__class__.river, field_name)
        self.content_type = app_config.CONTENT_TYPE_CLASS.objects.get_for_model(workflow_object)
        self.workflow = Workflow.objects.filter(content_type=self.content_type, field_name=field_name).first()
        self.initialized = False

    @transaction.atomic
    def initialize_approvals(self):
        if self.initialized or not self.workflow:
            return
        if self.workflow.transition_approvals.filter(
          object_id=self.workflow_object.pk,
          content_type=self.content_type
        ).exists():
            return
        self._create_transition_approvals()
        self.initialized = True
        LOGGER.debug("Transition approvals are initialized for the workflow object %s", self.workflow_object)

    def _create_transition_approvals(self):
        transition_meta_list = self.workflow.transition_metas.filter(source_state=self.workflow.initial_state)
        iteration = 0
        processed_transitions = set()

        while transition_meta_list:
            for transition_meta in transition_meta_list:
                self._create_transition_with_approvals(transition_meta, iteration)
                processed_transitions.add(transition_meta.pk)

            transition_meta_list = self.workflow.transition_metas.filter(
                source_state__in=transition_meta_list.values_list("destination_state", flat=True)
            ).exclude(pk__in=processed_transitions)
            iteration += 1

    def _create_transition_with_approvals(self, transition_meta, iteration):
      transition = Transition.objects.filter(
        workflow=self.workflow,
        workflow_object=self.workflow_object,
        source_state=transition_meta.source_state,
        destination_state=transition_meta.destination_state,
        meta=transition_meta,
        iteration=iteration
      ).last()
      
      if not transition:
          transition = Transition.objects.create(
            workflow=self.workflow,
            workflow_object=self.workflow_object,
            source_state=transition_meta.source_state,
            destination_state=transition_meta.destination_state,
            meta=transition_meta,
            iteration=iteration
        )

      for transition_approval_meta in transition_meta.transition_approval_meta.all():
        transition_approval, created = TransitionApproval.objects.get_or_create(
          workflow=self.workflow,
          object_id=self.workflow_object.pk,
          content_type=self.content_type,
          transition=transition,
          priority=transition_approval_meta.priority,
          meta=transition_approval_meta
        )
        if created:
          transition_approval.permissions.add(*transition_approval_meta.permissions.all())
          transition_approval.groups.add(*transition_approval_meta.groups.all())

    @property
    def on_initial_state(self):
        return self.get_state() == self.class_workflow.initial_state

    @property
    def on_final_state(self):
        return self.class_workflow.final_states.filter(pk=self.get_state().pk).exists()

    @property
    def next_approvals(self):
        transitions = Transition.objects.filter(
            workflow=self.workflow,
            object_id=self.workflow_object.pk,
            source_state=self.get_state()
        )
        return TransitionApproval.objects.filter(transition__in=transitions)

    @property
    def recent_approval(self):
      approvals = getattr(self.workflow_object, self.field_name + "_transition_approvals").filter(
        transaction_date__isnull=False)
      if approvals.exists():
        return approvals.latest('transaction_date')
      return None

    @transaction.atomic
    def jump_to(self, state):
        try:
            recent_iteration = self.recent_approval.transition.iteration if self.recent_approval else 0
            jumped_transition = self._get_jumped_transition(recent_iteration, state)
            self._set_jumped_transitions_to_jumped(jumped_transition)
            self.set_state(state)
            self.workflow_object.save()
        except Transition.DoesNotExist:
            raise RiverException(
                ErrorCode.STATE_IS_NOT_AVAILABLE_TO_BE_JUMPED,
                "This state is not available to be jumped in the future of this object"
            )

    def _get_jumped_transition(self, recent_iteration, state):
        return getattr(self.workflow_object, self.field_name + "_transitions").filter(
            iteration__gte=recent_iteration, destination_state=state, status=PENDING
        ).earliest("iteration")

    def _set_jumped_transitions_to_jumped(self, jumped_transition):
        jumped_transitions = self._get_transitions_before(jumped_transition.iteration).filter(status=PENDING)
        TransitionApproval.objects.filter(pk__in=jumped_transitions.values_list("transition_approvals__pk", flat=True)) \
            .update(status=JUMPED)
        jumped_transitions.update(status=JUMPED)

    def _get_transitions_before(self, iteration):
        return Transition.objects.filter(
            workflow=self.workflow,
            workflow_object=self.workflow_object,
            iteration__lte=iteration
        )

    def get_available_states(self, as_user=None):
        destination_state_ids = (self.get_available_approvals(as_user=as_user)
                                 .filter(transition_meta__source_state=self.get_state())).values_list('transition_meta__destination_state', flat=True)
        return State.objects.filter(pk__in=destination_state_ids)

    def get_available_approvals(self, as_user=None, destination_state=None):
        approvals = self.class_workflow.get_available_approvals(as_user)
        if destination_state:
            approvals = approvals.filter(transition_meta__destination_state=destination_state)
        else:
            approvals = approvals.filter(transition_meta__source_state=self.get_state())
        return approvals

    @transaction.atomic
    def approve(self, as_user, next_state=None):
        available_approvals = self.get_available_approvals(as_user=as_user)
        if not available_approvals.exists():
            raise ValidationError("There is no available approval for the user.")
        if next_state:
            available_approvals = available_approvals.filter(transition_meta__destination_state=next_state)
            if not available_approvals.exists():
                available_states = self.get_available_states(as_user)
                raise ValidationError("Invalid state is given(%s). Valid states are %s" % (
                    next_state, ','.join(map(str, available_states))
                ))
        if available_approvals.count() > 1 and not next_state:
            raise RiverException(ErrorCode.NEXT_STATE_IS_REQUIRED,
                                 "State must be given when there are multiple states for destination")

        self._process_approval(available_approvals.first(), as_user, next_state)

    def _process_approval(self, approval, as_user, next_state):
        approval, _ = TransitionApproval.objects.get_or_create(
            workflow=self.workflow,
            content_type=self._content_type,
            object_id=self.workflow_object.pk,
            meta=approval,
            status=PENDING,
            transition=Transition.objects.get_or_create(
                content_type=self._content_type,
                object_id=self.workflow_object.pk,
                meta=approval.transition_meta,
                workflow=self.workflow,
                source_state=approval.transition_meta.source_state,
                destination_state=approval.transition_meta.destination_state,
            )[0]
        )
        approval.status = APPROVED
        approval.transactioner = as_user
        approval.transaction_date = timezone.now()
        approval.previous = self.recent_approval if self.recent_approval else None
        approval.save()

        if next_state:
            self.cancel_impossible_future(approval)

        has_transit = False
        if not approval.peers.filter(status=PENDING).exists():
            approval.transition.status = DONE
            approval.transition.save()
            previous_state = self.get_state()
            self.set_state(approval.transition.destination_state)
            has_transit = True
            if self._check_if_it_cycled(approval.transition):
                self._re_create_cycled_path(approval.transition)
            LOGGER.debug(
                "Workflow object %s is proceeded for next transition. Transition: %s -> %s",
                self.workflow_object, previous_state, self.get_state()
            )

        with self._approve_signal(approval), self._transition_signal(has_transit, approval), self._on_complete_signal():
            self.workflow_object.save()

    @transaction.atomic
    def cancel_impossible_future(self, approved_approval):
        transition = approved_approval.transition
        possible_transition_ids = self._get_possible_transition_ids(transition)

        cancelled_transitions = Transition.objects.filter(
            workflow=self.workflow,
            object_id=self.workflow_object.pk,
            status=PENDING,
            iteration__gte=transition.iteration
        ).exclude(pk__in=possible_transition_ids)

        TransitionApproval.objects.filter(transition__in=cancelled_transitions).update(status=CANCELLED)
        cancelled_transitions.update(status=CANCELLED)

    def _get_possible_transition_ids(self, transition):
        possible_transition_ids = {transition.pk}
        possible_next_states = {transition.destination_state.label}

        while possible_next_states:
            possible_transitions = Transition.objects.filter(
                workflow=self.workflow,
                object_id=self.workflow_object.pk,
                status=PENDING,
                source_state__label__in=possible_next_states
            ).exclude(pk__in=possible_transition_ids)

            possible_transition_ids.update(possible_transitions.values_list("pk", flat=True))
            possible_next_states = set(possible_transitions.values_list("destination_state__label", flat=True))

        return possible_transition_ids

    def _approve_signal(self, approval):
        return ApproveSignal(self.workflow_object, self.field_name, approval)

    def _transition_signal(self, has_transit, approval):
        return TransitionSignal(has_transit, self.workflow_object, self.field_name, approval)

    def _on_complete_signal(self):
        return OnCompleteSignal(self.workflow_object, self.field_name)

    @property
    def _content_type(self):
        return ContentType.objects.get_for_model(self.workflow_object)

    def _to_key(self, source_state):
        return f"{self.content_type.pk}{self.field_name}{source_state.label}"

    def _check_if_it_cycled(self, done_transition):
        transitions = Transition.objects.filter(
            workflow_object=self.workflow_object,
            workflow=self.class_workflow.workflow,
            source_state=done_transition.destination_state
        )
        return transitions.filter(status=DONE).exists() and not transitions.filter(status=PENDING).exists()

    def _get_transition_images(self, source_states):
        meta_max_iteration = Transition.objects.filter(
            workflow=self.workflow,
            workflow_object=self.workflow_object,
            source_state__pk__in=source_states,
        ).values_list("meta").annotate(max_iteration=Max("iteration"))

        return Transition.objects.filter(
            Q(workflow=self.workflow, object_id=self.workflow_object.pk) &
            reduce(lambda agg, q: q | agg,
                   [Q(meta__id=meta_id, iteration=max_iteration) for meta_id, max_iteration in meta_max_iteration],
                   Q(pk=-1))
        )

    def _re_create_cycled_path(self, done_transition):
        old_transitions = self._get_transition_images([done_transition.destination_state.pk])
        iteration = done_transition.iteration + 1
        regenerated_transitions = set()

        while old_transitions.exists():
            for old_transition in old_transitions:
                cycled_transition = self._create_cycled_transition(old_transition, iteration)
                self._create_cycled_approvals(old_transition, cycled_transition)

            regenerated_transitions.add((old_transition.source_state, old_transition.destination_state))
            old_transitions = self._get_transition_images(
                old_transitions.values_list("destination_state__pk", flat=True)
            ).exclude(
                reduce(lambda agg, q: q | agg, [
                    Q(source_state=source_state, destination_state=destination_state)
                    for source_state, destination_state in regenerated_transitions
                ], Q(pk=-1))
            )
            iteration += 1

    def _create_cycled_transition(self, old_transition, iteration):
        return Transition.objects.create(
            source_state=old_transition.source_state,
            destination_state=old_transition.destination_state,
            workflow=old_transition.workflow,
            object_id=old_transition.workflow_object.pk,
            content_type=old_transition.content_type,
            status=PENDING,
            iteration=iteration,
            meta=old_transition.meta
        )

    def _create_cycled_approvals(self, old_transition, cycled_transition):
        for old_approval in old_transition.transition_approvals.all():
            cycled_approval = TransitionApproval.objects.create(
                transition=cycled_transition,
                workflow=old_approval.workflow,
                object_id=old_approval.workflow_object.pk,
                content_type=old_approval.content_type,
                priority=old_approval.priority,
                status=PENDING,
                meta=old_approval.meta
            )
            cycled_approval.permissions.set(old_approval.permissions.all())
            cycled_approval.groups.set(old_approval.groups.all())

    def get_state(self):
        return getattr(self.workflow_object, self.field_name)

    def set_state(self, state):
        setattr(self.workflow_object, self.field_name, state)
