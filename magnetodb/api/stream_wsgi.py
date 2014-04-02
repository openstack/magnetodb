# Copyright 2014 Mirantis Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json
import re
import shlex
import string

from threading import Event
import Queue

from gevent import monkey
monkey.patch_all()

from magnetodb import common
from magnetodb.openstack.common import log as logging
from magnetodb import storage
from magnetodb.storage import models
from magnetodb.api.openstack.v1 import parser
from magnetodb.api.openstack.v1 import utils

LOG = logging.getLogger(__name__)

MAX_FUTURES = 100


class Ctx:
    def __init__(self, tenant):
        self.tenant = tenant


def app_factory(global_conf, **local_conf):
    if not common.is_global_env_ready():
        options = dict(global_conf.items() + local_conf.items())
        oslo_config_args = options.get("oslo_config_args")
        s = string.Template(oslo_config_args)
        oslo_config_args = shlex.split(s.substitute(**options))
        common.setup_global_env(
            program=options.get("program", "magnetodb-stream-api"),
            args=oslo_config_args)

    return bulk_load_app


def make_callback(queue, event, done_count, chunk):
    def callback(future):
        done_count[0] += 1
        queue.put_nowait((future, chunk))
        event.set()
    return callback


def make_put_item(table_name, item):
    data = json.loads(item)

    attribute_map = parser.Parser.parse_item_attributes(data)

    return models.PutItemRequest(
        table_name, attribute_map)


def bulk_load_app(environ, start_response):

    from oslo.config import cfg
    max_async_jobs = cfg.CONF.max_async_jobs

    path = environ['PATH_INFO']

    LOG.debug('Request received: %s', path)

    if not re.match("^/v1/\w+/data/tables/\w+/bulk_load$", path):
        start_response('404 Not found', [('Content-Type', 'text/html')])
        yield 'Incorrect url. Please check it and try again\n'
        return

    url_comp = path.split('/')
    project_id = url_comp[2]
    table_name = url_comp[5]

    LOG.debug('Tenant: %s, table name: %s', project_id, table_name)

    context = environ['webob.adhoc_attrs']['context']

    utils.check_project_id(context, project_id)

    read_count = 0
    processed_count = 0
    unprocessed_count = 0
    failed_count = 0
    put_count = 0
    done_count = [0]
    last_read = None
    failed_items = {}

    dont_process = False

    future_ready_event = Event()
    future_ready_queue = Queue.Queue()

    stream = environ['wsgi.input']
    for chunk in stream:
        read_count += 1

        if dont_process:
            LOG.debug('Skipping item #%d', read_count)
            unprocessed_count += 1
            continue

        last_read = chunk

        try:
            put_request = make_put_item(table_name, chunk)

            future = storage.put_item_async(context, put_request)

            put_count += 1

            future.add_done_callback(make_callback(
                future_ready_queue,
                future_ready_event,
                done_count,
                chunk
            ))

            # prevent too many simultaneous async tasks
            while put_count - done_count[0] > max_async_jobs:
                future_ready_event.wait()
                future_ready_event.clear()

            # try to get result of finished futures
            try:
                while True:
                    finished_future, chunk = future_ready_queue.get_nowait()
                    finished_future.result()
                    processed_count += 1
            except Queue.Empty:
                pass

        except Exception as e:
            failed_items[chunk] = repr(e)
            dont_process = True
            LOG.debug('Error inserting item: %s, message: %s',
                      chunk, repr(e))

    LOG.debug('Request body has been read completely')

    # wait for all futures to be finished
    while done_count[0] < put_count:
        LOG.debug('Waiting for %d item(s) to be processed...',
                  put_count - done_count[0])
        future_ready_event.wait()
        future_ready_event.clear()

    LOG.debug('All items are processed. Getting results of item processing...')

    # get results of finished futures
    while done_count[0] > processed_count + failed_count:
        LOG.debug('Waiting for %d result(s)...',
                  processed_count + failed_count - done_count[0])
        chunk = None
        try:
            finished_future, chunk = future_ready_queue.get_nowait()
            finished_future.result()
            processed_count += 1
        except Queue.Empty:
            break
        except Exception as e:
            failed_count += 1
            failed_items[chunk] = repr(e)
            LOG.debug('Error inserting item: %s, message: %s',
                      chunk, repr(e))

    # Update count if error happened before put_item_async was invoked
    if dont_process:
        failed_count += 1

    start_response('200 OK', [('Content-Type', 'application/json')])

    resp = {
        'read': read_count,
        'processed': processed_count,
        'unprocessed': unprocessed_count,
        'failed': failed_count,
        'last_item': last_read,
        'failed_items': failed_items
    }

    yield json.dumps(resp)
