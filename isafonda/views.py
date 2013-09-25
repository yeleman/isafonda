#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import json

import requests
from requests.exceptions import RequestException

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404

from isafonda.models import (Project, FondaSMSRequest,
                             StalledRequest)
from isafonda.utils import should_forward
from isafonda.connection import conn_status


def home(request):
    text = "Service is running OK.\n"
    text += "\n".join(["{slug}:\t{name}".format(slug=p.slug,
                                                name=p.name)
                       for p in Project.objects.all()])

    return HttpResponse(text, mimetype='text/plain')


@csrf_exempt
@require_POST
def fondasms_handler(request, project_slug):

    project = get_object_or_404(Project, slug=project_slug)

    fondareq = FondaSMSRequest.from_post(request.POST)

    if not should_forward(project, fondareq):
        return build_response_with(pending_upstream_messages(
            project, phone_number=fondareq.phone_number))

    try:
        req = requests.post(project.url,
                            data=request.POST,
                            timeout=project.timeout)
        req.raise_for_status()
    except RequestException:
        conn_status.update(project, conn_status.NOT_WORKING)
        cache_request_locally(request, project)
        return build_response_with(pending_upstream_messages(
            project, phone_number=fondareq.phone_number))

    conn_status.update(project, conn_status.WORKING)

    return merge_response_with(req, pending_upstream_messages(
        project, phone_number=fondareq.phone_number))


def pending_upstream_messages(project, max_items=None, phone_number=None):
    # list of messages that were stalled in this gateway (fetched from server)
    # and not yet sent to upstream (phone)
    return StalledRequest.get_pending_upstream(project=project,
                                               max_items=max_items,
                                               phone_number=phone_number)


def build_response_with(events=[]):
    response = {"events": events}
    return HttpResponse(json.dumps(response),
                        mimetype='application/json')


def merge_response_with(response, events=[]):
    response_obj = json.loads(response.text)

    if not isinstance(response_obj.get('events'), list):
        response_obj['events'] = []

    response_obj['events'] += events

    return HttpResponse(json.dumps(response_obj),
                        mimetype='application/json')


def can_overload_response(response):
    return response.status_code in (200, 201) \
        and response.headers.get('content-type') == 'application/json'


def cache_request_locally(request, project):
    StalledRequest.from_upstream(project=project, request=request)
