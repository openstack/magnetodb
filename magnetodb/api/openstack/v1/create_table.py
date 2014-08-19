# Copyright 2014 Mirantis Inc.
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

import jsonschema


from magnetodb import storage
from magnetodb.storage import models

from magnetodb.openstack.common.log import logging

from magnetodb.api.openstack.v1 import parser
from magnetodb.api.openstack.v1 import utils
from magnetodb.common import exception
from magnetodb.common import probe

LOG = logging.getLogger(__name__)


class CreateTableController():
    """
    The CreateTable operation adds a new table.
    Table names must be unique within each tenant.
    """

    schema = {
        "required": [parser.Props.ATTRIBUTE_DEFINITIONS,
                     parser.Props.KEY_SCHEMA,
                     parser.Props.TABLE_NAME],
        "properties": {
            parser.Props.ATTRIBUTE_DEFINITIONS: {
                "type": "array",
                "items": parser.Types.ATTRIBUTE_DEFINITION
            },
            parser.Props.KEY_SCHEMA: parser.Types.KEY_SCHEMA,

            parser.Props.LOCAL_SECONDARY_INDEXES: {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [parser.Props.INDEX_NAME,
                                 parser.Props.KEY_SCHEMA,
                                 parser.Props.PROJECTION],
                    "properties": {
                        parser.Props.INDEX_NAME: parser.Types.INDEX_NAME,
                        parser.Props.KEY_SCHEMA: parser.Types.KEY_SCHEMA,
                        parser.Props.PROJECTION: parser.Types.PROJECTION
                    }
                }
            },

            parser.Props.TABLE_NAME: parser.Types.TABLE_NAME
        }
    }

    @probe.probe(__name__)
    def create_table(self, req, body, project_id):
        utils.check_project_id(req.context, project_id)
        with probe.Probe(__name__ + '.jsonschema.validate'):
            jsonschema.validate(body, self.schema)

        table_name = body.get(parser.Props.TABLE_NAME)

        # parse table attributes
        attribute_definitions = parser.Parser.parse_attribute_definitions(
            body.get(parser.Props.ATTRIBUTE_DEFINITIONS, {})
        )

        # parse table key schema
        key_attrs = parser.Parser.parse_key_schema(
            body.get(parser.Props.KEY_SCHEMA, [])
        )

        # parse table indexed field list
        index_def_map = parser.Parser.parse_local_secondary_indexes(
            body.get(
                parser.Props.LOCAL_SECONDARY_INDEXES, [])
        )
        for index_name, index_def in index_def_map.iteritems():
            if index_def.alt_hash_key_attr != key_attrs[0]:
                msg = _("Error. Hash key of index '%(index_name)s' must "
                        "be the same as primary key's hash key.")
                raise exception.ValidationError(msg, index_name=index_name)

        # prepare table_schema structure
        table_schema = models.TableSchema(
            attribute_definitions, key_attrs, index_def_map)

        # creating table
        req.context.tenant = project_id
        table_meta = storage.create_table(
            req.context, table_name, table_schema)

        url = req.path_url + "/" + table_name
        bookmark = req.path_url + "/" + table_name

        result = {
            parser.Props.TABLE_DESCRIPTION: {
                parser.Props.ATTRIBUTE_DEFINITIONS: (
                    parser.Parser.format_attribute_definitions(
                        table_meta.schema.attribute_type_map
                    )
                ),
                parser.Props.CREATION_DATE_TIME: 0,
                parser.Props.ITEM_COUNT: 0,
                parser.Props.KEY_SCHEMA: (
                    parser.Parser.format_key_schema(
                        table_meta.schema.key_attributes
                    )
                ),
                parser.Props.TABLE_NAME: table_name,
                parser.Props.TABLE_STATUS: (
                    parser.Parser.format_table_status(table_meta.status)
                ),
                parser.Props.TABLE_SIZE_BYTES: 0,
                parser.Props.LINKS: [
                    {
                        parser.Props.HREF: url,
                        parser.Props.REL: parser.Values.SELF
                    },
                    {
                        parser.Props.HREF: bookmark,
                        parser.Props.REL: parser.Values.BOOKMARK
                    }
                ]
            }
        }

        if table_meta.schema.index_def_map:
            table_def = result[parser.Props.TABLE_DESCRIPTION]
            table_def[parser.Props.LOCAL_SECONDARY_INDEXES] = (
                parser.Parser.format_local_secondary_indexes(
                    table_meta.schema.key_attributes[0],
                    table_meta.schema.index_def_map
                )
            )

        return result
