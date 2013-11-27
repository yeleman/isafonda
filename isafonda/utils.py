#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import datetime

import requests
from requests.exceptions import RequestException


def datetime_from_timestamp(timestamp):
    try:
        return datetime.datetime.fromtimestamp(int(timestamp) / 1000)
    except (TypeError, ValueError):
        return None
    return None


def to_timestamp(dt):
    """
    Return a timestamp for the given datetime object.
    """
    if not dt is None:
        return (dt - datetime.datetime(1970, 1, 1)).total_seconds()


def to_jstimestamp(adate):
    if not adate is None:
        return int(to_timestamp(adate)) * 1000


def get_test_payload():
    return {'action': 'test',
            'battery': '100',
            'log': '',
            'network': 'WIFI',
            'now': to_jstimestamp(datetime.datetime.now()),
            'phone_id': '',
            'phone_number': 'unknown',
            'phone_token': '',
            'power': '2',
            'send_limit': '10000',
            'settings_version': '0',
            'version': '30'}


def test_connection(url, timeout):
    try:
        req = requests.post(url,
                           data=get_test_payload(),
                           timeout=timeout)
        req.raise_for_status()
        return True
    except RequestException:
        pass
    return False


def should_forward(project, request):
    from isafonda.models import StalledRequest
    from isafonda.connection import conn_status

    matrix = {
        'transfer_outgoing': 'is_outgoing',
        'transfer_sms': 'is_sms',
        'transfer_mms': 'is_mms',
        'transfer_call': 'is_call',
        'transfer_send_status': 'is_send_status',
        'transfer_device_status': 'is_device_status',
        'transfer_sent': 'is_forwarded_sent'
    }

    if request.is_test:
        return False

    # special case for outgoing
    # we don't forward if there's alredy one pending
    if request.is_outgoing and project.transfer_outgoing and not conn_status.is_working(project):
        return not has_pending_outgoing(project)

    for allowance, state in matrix.items():
        if getattr(project, allowance, False) and getattr(request, state, False):
            return True

    return False

def has_pending_outgoing(project):
    from isafonda.models import StalledRequest
    return StalledRequest.objects.filter(
        project=project,
        status=StalledRequest.PENDING_DOWNSTREAM).count()
