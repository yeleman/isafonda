#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from __future__ import (unicode_literals, absolute_import,
                        division, print_function)
import datetime
import json

import requests
from django.conf import settings
from django.db import models
from picklefield.fields import PickledObjectField
from requests.exceptions import RequestException

from isafonda._compat import implements_to_string
from isafonda.utils import datetime_from_timestamp


class FondaSMSRequest(dict):

    OUTGOING = 'outgoing'
    INCOMING = 'incoming'
    SEND_STATUS = 'send_status'
    DEVICE_STATUS = 'device_status'
    TEST = 'test'
    AMQP_STARTED = 'amqp_started'
    FORWARD_SENT = 'forward_sent'

    MOBILE = 'MOBILE'
    WIFI = 'WIFI'

    SMS = 'sms'
    MMS = 'mms'
    CALL = 'call'

    @classmethod
    def from_post(cls, post_data):
        d = FondaSMSRequest()
        for k, v in post_data.items():
            d.update({k: v})
        return d

    @property
    def is_mobile(self):
        return self.get('network', self.WIFI) == self.MOBILE

    @property
    def is_wifi(self):
        return not self.is_mobile

    @property
    def date(self):
        return datetime_from_timestamp(self.get('now'))

    @property
    def event_date(self):
        if self.get('timestamp') is not None:
            return datetime_from_timestamp(self.get('timestamp'))

    @property
    def phone_number(self):
        return self.get('phone_number', '').strip() or None

    @property
    def identity(self):
        return self.get('from')

    @property
    def is_test(self):
        return self.get('action') == self.TEST

    @property
    def is_outgoing(self):
        return self.get('action') == self.OUTGOING

    @property
    def is_incoming(self):
        return self.get('action') == self.INCOMING

    @property
    def is_sms(self):
        return self.get('action') == self.INCOMING \
            and self.get('message_type') == self.SMS

    @property
    def is_mms(self):
        return self.get('action') == self.INCOMING \
            and self.get('message_type') == self.MMS

    @property
    def is_call(self):
        return self.get('action') == self.INCOMING \
            and self.get('message_type') == self.CALL

    @property
    def is_send_status(self):
        return self.get('action') == self.SEND_STATUS

    @property
    def is_device_status(self):
        return self.get('action') == self.DEVICE_STATUS

    @property
    def is_forwarded_sent(self):
        return self.get('action') == self.FORWARD_SENT


@implements_to_string
class Project(models.Model):

    slug = models.CharField(max_length=30, primary_key=True)
    name = models.CharField(max_length=100)
    url = models.URLField()
    reply_same_phone = models.BooleanField()
    automatic_reply = models.BooleanField(
        help_text="When active, reply to every incoming request.")
    automatic_reply_text = models.CharField(
        max_length=380, null=True, blank=True)
    timeout = models.FloatField(default=10)
    max_items = models.PositiveIntegerField(
        default=settings.DEFAULT_MAX_ITEMS_TO_UPSTREAM)
    transfer_outgoing = models.BooleanField(
        help_text="Transfer requests for ougoing messages.")
    transfer_sms = models.BooleanField(
        help_text="Transfer incoming SMS to server.")
    transfer_mms = models.BooleanField(
        help_text="Transfer incoming MMS to server.")
    transfer_call = models.BooleanField(
        help_text="Transfer incoming call notifications to server.")
    transfer_send_status = models.BooleanField(
        help_text="Transfer delivery report status to server.")
    transfer_device_status = models.BooleanField(
        help_text="Transfer device (battery, network) status to server.")
    transfer_sent = models.BooleanField(
        help_text="Transfer non-app (manual) SMS sent from phone to server.")
    upstream_url = models.URLField(
        help_text="URL of the closer-to-device equipment/isafonda.",
        null=True, blank=True)
    transfer_upstream = models.BooleanField(
        help_text="Transfer events from downstream gateway to upstream.")
    transfer_upstream_secret = models.CharField(
        max_length=250, null=True, blank=True,
        help_text="A string to protect unauthorized people from sending.")

    def __str__(self):
        return self.name


@implements_to_string
class StalledRequest(models.Model):

    class Meta:
        ordering = ('created_on', )

    # to phone
    PENDING_UPSTREAM = 'PENDING_UPSTREAM'
    SENT_UPSTREAM = 'SENT_UPSTREAM'
    # to wan
    PENDING_DOWNSTREAM = 'PENDING_DOWNSTREAM'
    SENT_DOWNSTREAM = 'SENT_DOWNSTREAM'

    STATUSES = {
        PENDING_UPSTREAM: "Pending to phone",
        SENT_UPSTREAM: "Sent to phone",
        PENDING_DOWNSTREAM: "Pending to Server",
        SENT_DOWNSTREAM: "Sent to Server"
    }

    project = models.ForeignKey(Project, related_name='messages')
    status = models.CharField(max_length=75,
                              choices=STATUSES.items())
    created_on = models.DateTimeField(auto_now_add=True)
    originated_on = models.DateTimeField()
    altered_on = models.DateTimeField(auto_now=True)
    phone_number = models.CharField(max_length=50, null=True, blank=True)
    payload = PickledObjectField(null=True, blank=True)

    def __str__(self):
        return "{project}#{id}".format(project=self.project.slug,
                                       id=self.id)

    @classmethod
    def from_upstream(cls, project, request):
        fondareq = FondaSMSRequest.from_post(request.POST)
        return cls.objects.create(project=project,
                                  status=cls.PENDING_DOWNSTREAM,
                                  originated_on=fondareq.event_date or fondareq.date,
                                  phone_number=fondareq.phone_number or None,
                                  payload=fondareq)

    @classmethod
    def get_pending_upstream(cls, project, max_items=None, phone_number=None):
        max_items = project.max_items if max_items is None else max_items
        going_items = []
        remaining = max_items - len(going_items)
        base_filter = cls.objects.filter(status=cls.PENDING_UPSTREAM)
        none_list = list(base_filter.filter(phone_number__isnull=True))

        if project.reply_same_phone:
            all_reqs = list(set(none_list + list(base_filter.filter(phone_number=phone_number))))
        else:
            all_reqs = none_list

        for req in all_reqs:
            if len(req.payload) <= remaining:
                going_items += req.payload
                req.status = cls.SENT_UPSTREAM
            else:
                going_items += req.payload[:remaining]
                req.payload = req.payload[remaining:]
            req.save()
        return going_items

    def retry_downstream(self):
        now = datetime.datetime.now()
        try:
            req = requests.post(self.project.url,
                                data=self.payload,
                                timeout=self.project.timeout)
            req.raise_for_status()
        except RequestException:
            # failed again. Just update time
            self.altered_on = now
            self.save()

        # worked! store response and change status
        self.update(self.SENT_DOWNSTREAM)

        try:
            response_obj = json.loads(req.text)
            events = response_obj['events'][0]['messages']
            phone_number = response_obj.get('phone_number') or None
        except:
            return

        # don't store anything if there's no reply
        if not len(events):
            return

        # we do have some replies to forward upstream
        self.from_downstream(self.project, events, phone_number)

    @classmethod
    def from_downstream(cls, project, events, phone_number=None):
        return cls.objects.create(
            project=project,
            status=cls.PENDING_UPSTREAM,
            originated_on=datetime.datetime.now(),
            phone_number=phone_number or None,
            payload=events)


    def update(self, status):
        self.status = status
        self.altered_on = datetime.datetime.now()
        self.save()

