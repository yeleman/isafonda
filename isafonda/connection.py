#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import datetime

from isafonda.models import Project
from isafonda.utils import test_connection


class ConnectionStatus(object):

    UNKNWON = 'unknown'
    WORKING = 'working'
    NOT_WORKING = 'not-working'

    def __init__(self):
        self.data = {}
        self.init_for_all()

    def init_for(self, project, with_update=False):
        now = datetime.datetime.now()
        self.data[project.slug] = {
            'status': self.UNKNWON,
            'last_change': now,
            'last_update': now
        }
        if with_update:
            self.update_from_network(project)

    def init_for_all(self):
        for project in Project.objects.all():
            self.init_for(project)

    def update(self, project, status):
        now = datetime.datetime.now()
        if status != self.status:
            self._set(project, 'status', status)
            self._set(project, 'last_change', now)
        self._set(project, 'last_update', now)

    def update_from_network(self, project):
        nstatus = self.WORKING if test_connection(project.url, project.timeout) \
                               else self.NOT_WORKING
        self.update(project, nstatus)

    def _get(self, project, prop):
        return self.data.get(project.slug, {}).get(prop)

    def _set(self, project, prop, value):
        if not hasattr(self.data, project.slug):
            self.data.update({project.slug: {}})
        self.data[project.slug].update({prop: value})

    def status(self, project):
        return self._get(project, 'status')

    def last_change(self, project):
        return self._get(project, 'last_change')

    def last_update(self, project):
        return self._get(project, 'last_update')

    def duration(self, project):
        return datetime.datetime.now() - self.last_change(project)

    def is_working(self, project):
        return self.status(project) == self.WORKING

    def update_all_status(self):
        for project in Project.objects.all():
            self.update_from_network(project)

# Status Holder Initializer
conn_status = ConnectionStatus()
