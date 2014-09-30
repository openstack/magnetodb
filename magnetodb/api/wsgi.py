# Copyright 2014 Symantec Corporation
# Copyright 2013 Mirantis Inc.
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

import routes

from magnetodb.common import setup_global_env
from magnetodb.common import wsgi

from magnetodb.api.openstack import health_check
from magnetodb.api.openstack.v1 import openstack_api
from magnetodb.api.openstack.v1 import create_resource
from magnetodb.api.openstack.v1 import create_table
from magnetodb.api.openstack.v1 import list_tables
from magnetodb.api.openstack.v1 import describe_table
from magnetodb.api.openstack.v1 import scan
from magnetodb.api.openstack.v1 import query
from magnetodb.api.openstack.v1 import delete_table

from magnetodb.api.amz import controller as amz_api_controller
from magnetodb.api.amz import wsgi as amazon_wsgi


class MagnetoDBApplication(wsgi.Router):

    """API"""
    def __init__(self):
        mapper = routes.Mapper()
        super(MagnetoDBApplication, self).__init__(mapper)

        amz_dynamodb_api_app = (
            amazon_wsgi.AmazonResource(
                controller=amz_api_controller.AmzDynamoDBApiController())
        )

        mapper.extend(openstack_api, "/v1")

        mapper.connect("/", controller=amz_dynamodb_api_app,
                       conditions={'method': 'POST'},
                       action="process_request")

        mapper.connect("/v1/{project_id}/data/tables",
                       controller=create_resource(
                           list_tables.ListTablesController()),
                       conditions={'method': 'GET'},
                       action="list_tables")

        mapper.connect("/v1/{project_id}/data/tables",
                       controller=create_resource(
                           create_table.CreateTableController()),
                       conditions={'method': 'POST'},
                       action="create_table")

        mapper.connect("/v1/{project_id}/data/tables/{table_name}",
                       controller=create_resource(
                           describe_table.DescribeTableController()),
                       conditions={'method': 'GET'},
                       action="describe_table")

        mapper.connect("/v1/{project_id}/data/tables/{table_name}/scan",
                       controller=create_resource(
                           scan.ScanController()),
                       conditions={'method': 'POST'},
                       action="scan")

        mapper.connect("/v1/{project_id}/data/tables/{table_name}/query",
                       controller=create_resource(
                           query.QueryController()),
                       conditions={'method': 'POST'},
                       action="query")

        mapper.connect("/v1/{project_id}/data/tables/{table_name}",
                       controller=create_resource(
                           delete_table.DeleteTableController()),
                       conditions={'method': 'DELETE'},
                       action="delete_table")

    @classmethod
    @setup_global_env
    def factory_method(cls, global_conf, **local_conf):
        return cls()


class MagnetoDBHealthCheckApplication(wsgi.Router):

    """Health check API"""
    def __init__(self, auth_uri=''):
        mapper = routes.Mapper()
        super(MagnetoDBHealthCheckApplication, self).__init__(mapper)

        mapper.connect("/check", controller=create_resource(
                       health_check.HealthCheckController(auth_uri)),
                       conditions={'method': 'GET'},
                       action="health_check")

    @classmethod
    @setup_global_env
    def factory_method(cls, global_conf, **local_conf):
        if 'auth_uri' in global_conf:
            auth_uri = global_conf['auth_uri']
        return cls(auth_uri)
