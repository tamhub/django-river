try:
    # Django 2.0 and newer
    from django.urls import re_path as url
except ImportError:
    # Django 1.11 and older
    from django.conf.urls import url
from django.contrib import admin

urlpatterns = [
    url(r'^admin/', admin.site.urls),
]