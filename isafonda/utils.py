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
