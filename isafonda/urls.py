from django.conf.urls import patterns, include, url

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',

    url(r'^admin/', include(admin.site.urls)),
    url(r'^(?P<project_slug>[a-zA-Z0-9\_\-\.]+)/?$',
        'isafonda.views.fondasms_handler',
        name='fondasms_project'),
    url(r'^$', 'isafonda.views.home', name='home'),
)
