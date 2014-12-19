# Copyright 2014 Symantec Corporation
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
import logging
import time

from magnetodb import notifier

from magnetodb.storage import models
from magnetodb.storage.manager import simple_impl as manager

LOG = logging.getLogger(__name__)


class AsyncSimpleStorageManager(manager.SimpleStorageManager):
    def __init__(self, storage_driver, table_info_repo,
                 concurrent_tasks=1000, batch_chunk_size=25,
                 schema_operation_timeout=300):
        manager.SimpleStorageManager.__init__(
            self, storage_driver, table_info_repo,
            concurrent_tasks, batch_chunk_size,
            schema_operation_timeout
        )

    def _do_create_table(self, context, table_info):
        start_time = time.time()
        self._notifier.info(
            context,
            notifier.EVENT_TYPE_TABLE_CREATE_START,
            table_info.schema)

        future = self._execute_async(self._storage_driver.create_table,
                                     context, table_info)

        def callback(future):
            if not future.exception():
                table_info.status = models.TableMeta.TABLE_STATUS_ACTIVE
                table_info.internal_name = future.result()
                self._table_info_repo.update(
                    context, table_info, ["status", "internal_name"]
                )
                self._notifier.info(
                    context,
                    notifier.EVENT_TYPE_TABLE_CREATE_END,
                    dict(
                        table_name=table_info.name,
                        table_uuid=str(table_info.id),
                        schema=table_info.schema,
                        value=start_time
                    ))
            else:
                table_info.status = models.TableMeta.TABLE_STATUS_CREATE_FAILED
                self._table_info_repo.update(
                    context, table_info, ["status"]
                )
                self._notifier.error(
                    context,
                    notifier.EVENT_TYPE_TABLE_CREATE_ERROR,
                    dict(
                        table_name=table_info.name,
                        table_uuid=str(table_info.id),
                        message=future.exception(),
                        value=start_time
                    ))

        future.add_done_callback(callback)

    def _do_delete_table(self, context, table_info):
        start_time = time.time()
        future = self._execute_async(self._storage_driver.delete_table,
                                     context, table_info)

        def callback(future):
            if not future.exception():
                self._table_info_repo.delete(
                    context, table_info.name
                )
                self._notifier.info(
                    context, notifier.EVENT_TYPE_TABLE_DELETE_END,
                    dict(
                        table_name=table_info.name,
                        table_uuid=str(table_info.id),
                        value=start_time
                    ))
            else:
                table_info.status = models.TableMeta.TABLE_STATUS_DELETE_FAILED
                self._table_info_repo.update(
                    context, table_info, ["status"]
                )
                self._notifier.error(
                    context, notifier.EVENT_TYPE_TABLE_DELETE_ERROR,
                    dict(
                        message=future.exception(),
                        table_name=table_info.name,
                        table_uuid=str(table_info.id),
                        value=start_time),
                    priority=notifier.PRIORITY_ERROR
                )

        future.add_done_callback(callback)
