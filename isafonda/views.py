#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import json
import re

import requests
from requests.exceptions import RequestException

from django.http import HttpResponse  #, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404

from isafonda.models import (Project, FondaSMSRequest,
                             StalledRequest)
from isafonda.utils import should_forward, has_pending_outgoing
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

    automatic_reply = get_automatic_reply(fondareq, project)

    if not should_forward(project, fondareq):
        return build_response_with(
            pending_upstream_messages(
                project,
                phone_number=fondareq.phone_number,
                auto_reply=automatic_reply),
            phone_number=fondareq.phone_number)

    try:
        req = requests.post(project.url,
                            data=request.POST,
                            timeout=project.timeout)
        req.raise_for_status()
    except RequestException:
        conn_status.update(project, conn_status.NOT_WORKING)
        if not fondareq.is_outgoing or not has_pending_outgoing(project):
            cache_request_locally(request, project)
        return build_response_with(
            pending_upstream_messages(
                project,
                phone_number=fondareq.phone_number,
                auto_reply=automatic_reply),
            phone_number=fondareq.phone_number)

    conn_status.update(project, conn_status.WORKING)

    return merge_response_with(
        req,
        pending_upstream_messages(
            project,
            phone_number=fondareq.phone_number,
            auto_reply=automatic_reply))


def pending_upstream_messages(project,
                              max_items=None, phone_number=None,
                              auto_reply=None):
    # list of messages that were stalled in this gateway (fetched from server)
    # and not yet sent to upstream (phone)
    auto = [auto_reply] if auto_reply else []
    return StalledRequest.get_pending_upstream(project=project,
                                               max_items=max_items,
                                               phone_number=phone_number) + auto


def build_response_with(events=[], phone_number=None):
    response = {'events': [],
                'phone_number': phone_number}
    if len(events):
        if not len(response['events']):
            response['events'].append({'event': 'send', 'messages': []})
        response['events'][0]['messages'] += events
    return HttpResponse(json.dumps(response),
                        mimetype='application/json')


def merge_response_with(response, events=[]):
    response_obj = json.loads(response.text)

    if not isinstance(response_obj.get('events'), list):
        response_obj['events'] = []

    if len(events):
        if not len(response_obj['events']):
            response_obj['events'].append({'event': 'send', 'messages': []})
        response_obj['events'][0]['messages'] += events

    return HttpResponse(json.dumps(response_obj),
                        mimetype='application/json')


def can_overload_response(response):
    return response.status_code in (200, 201) \
        and response.headers.get('content-type') == 'application/json'


def cache_request_locally(request, project):
    StalledRequest.from_upstream(project=project, request=request)


def get_automatic_reply(request, project):
    if not project.automatic_reply or project.automatic_reply_text is None:
        return None

    if not request.is_incoming or request.identity is None:
        return None

    return {'to': request.identity,
            'message': project.automatic_reply_text}


@csrf_exempt
@require_POST
def external_events_handler(request, project_slug):
    failed_to_send = False
    print("project: {}".format(project_slug))
    project = get_object_or_404(Project, slug=project_slug)

    # if not project.transfer_upstream:
    #     return Http404()

    secret = request.GET.get('secret', '').strip()
    phone_number = request.GET.get('phone_number', None)
    events = json.loads(request.read())

    if project.transfer_upstream_secret \
        and project.transfer_upstream_secret != secret:
        return HttpResponse("Access Forbidden", status=403)

    if project.transfer_upstream:
        if phone_number is not None:
            params = {'phone_number': re.sub(r'^223', '', phone_number)}
        else:
            params = {}
        try:
            req = requests.post(project.upstream_url,
                                data=json.dumps(events),
                                timeout=project.timeout,
                                params=params)
            req.raise_for_status()
        except RequestException:
            failed_to_send = True

    if failed_to_send or not project.transfer_upstream:
        StalledRequest.from_downstream(project=project,
                                       events=events,
                                       phone_number=phone_number)
        return HttpResponse("Request cached for later delivery.",
                            status=201)

    return HttpResponse("Request properly forwarded.",
                        status=200)
