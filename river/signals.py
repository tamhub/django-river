import logging
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.dispatch import Signal
from river.models import Workflow
from river.models.hook import BEFORE, AFTER
from river.models.on_approved_hook import OnApprovedHook
from river.models.on_complete_hook import OnCompleteHook
from river.models.on_transit_hook import OnTransitHook

# Define signals
pre_on_complete = Signal()
post_on_complete = Signal()
pre_transition = Signal()
post_transition = Signal()
pre_approve = Signal()
post_approve = Signal()

LOGGER = logging.getLogger(__name__)


class SignalHandler:
    def __init__(self, workflow_object, field_name, transition_approval=None):
        self.workflow_object = workflow_object
        self.field_name = field_name
        self.transition_approval = transition_approval
        self.content_type = ContentType.objects.get_for_model(workflow_object.__class__)
        self.workflow = Workflow.objects.get(content_type=self.content_type, field_name=self.field_name)

    def execute_hooks(self, hook_model, when, transition_approval_field):
        # TODO: Implement this
        # hooks = hook_model.objects.filter(
        #     (Q(object_id__isnull=True) | Q(object_id=self.workflow_object.pk, content_type=self.content_type)) &
        #     (Q(**{transition_approval_field: self.transition_approval}) | Q(**{transition_approval_field: None})) &
        #     Q(workflow__field_name=self.field_name, hook_type=when)
        # )
        # for hook in hooks:
        #     hook.execute(self.get_context(when))
        pass

    def get_context(self, when):
        context = {
            "hook": {
                "when": when,
                "payload": {
                    "workflow": self.workflow,
                    "workflow_object": self.workflow_object,
                }
            }
        }
        if self.transition_approval:
            context["hook"]["payload"]["transition_approval"] = self.transition_approval
        return context


class TransitionSignal(SignalHandler):
    def __init__(self, status, workflow_object, field_name, transition_approval):
        super().__init__(workflow_object, field_name, transition_approval)
        self.status = status

    def __enter__(self):
        if self.status:
            self.execute_hooks(OnTransitHook, BEFORE, 'transition')
            LOGGER.debug(
                f"Signal fired before transition ({self.transition_approval.transition}) for {self.workflow_object}")

    def __exit__(self, exc_type, exc_value, traceback):
        if self.status:
            self.execute_hooks(OnTransitHook, AFTER, 'transition')
            LOGGER.debug(
                f"Signal fired after transition ({self.transition_approval.transition}) for {self.workflow_object}")


class ApproveSignal(SignalHandler):
    def __enter__(self):
        self.execute_hooks(OnApprovedHook, BEFORE, 'transition_approval')
        LOGGER.debug(
            f"Signal fired before transition approval for {self.workflow_object} due to transition "
            f"{self.transition_approval.transition.source_state.label} -> "
            f"{self.transition_approval.transition.destination_state.label}")

    def __exit__(self, exc_type, exc_value, traceback):
        self.execute_hooks(OnApprovedHook, AFTER, 'transition_approval')
        LOGGER.debug(
            f"Signal fired after transition approval for {self.workflow_object} due to transition "
            f"{self.transition_approval.transition.source_state.label} -> "
            f"{self.transition_approval.transition.destination_state.label}")


class OnCompleteSignal(SignalHandler):
    def __init__(self, workflow_object, field_name):
        super().__init__(workflow_object, field_name)
        self.status = getattr(self.workflow_object.river, self.field_name).on_final_state

    def __enter__(self):
        if self.status:
            self.execute_hooks(OnCompleteHook, BEFORE, None)
            LOGGER.debug(f"Signal fired before workflow of {self.workflow_object} is complete")

    def __exit__(self, exc_type, exc_value, traceback):
        if self.status:
            self.execute_hooks(OnCompleteHook, AFTER, None)
            LOGGER.debug(f"Signal fired after workflow of {self.workflow_object} is complete")
