#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)

from django.core.management.base import BaseCommand
from optparse import make_option

from isafonda.models import Project, StalledRequest
from isafonda.utils import test_connection
from isafonda.connection import conn_status


class Command(BaseCommand):
    help = "Ping the upstream server and clears pending messages if reachable"
    option_list = BaseCommand.option_list + (
        make_option('-p', '--project',
                    action="store",
                    dest='project',
                    default=None,
                    help='Project slug to check unpon'),)

    def handle(self, *args, **options):
        project_slug = options.get('project')
        try:
            project = Project.objects.get(slug=project_slug)
        except Project.DoesNotExist:
            print("Unable to find poject with slug `{}`".format(project_slug))
            return

        print("Pinging server for project `{}`".format(project.slug))

        if conn_status.is_working(project):
            print("Last known state was working. Exiting.")
            return

        print("Testing connection now.")

        if not test_connection(project.url, project.timeout):
            conn_status.update(project, conn_status.NOT_WORKING)
            print("Connection not working. Exiting.")
            return

        # record that it worked
        conn_status.update(project, conn_status.WORKING)
        print("Connection is now working. Processing.")

        # clear-up the pending requests for server
        for sreq in StalledRequest.objects.filter(
                project=project,
                status=StalledRequest.PENDING_DOWNSTREAM):
            sreq.retry_downstream()

        print("Updates completed.")
