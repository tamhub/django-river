from django.db import models
from django.utils.translation import gettext_lazy as _


class FeatureSetting(models.Model):
    class FeatureChoices(models.TextChoices):
        USERNAME_COLUMN = 'username_column', _('Username Column')
        DATABASE_VISIBILITY = 'database_visibility', _('Database Visibility')
        Transition_History_Display = 'transition_history_display', _('Transition History Display')

        # Add more features in the future

    feature = models.CharField(
        max_length=50,
        choices=FeatureChoices.choices,
        unique=True,  # Ensure each feature is listed only once
    )
    is_enabled = models.BooleanField(default=False)

    def __str__(self):
        return self.get_feature_display()  # Show human-readable feature name
