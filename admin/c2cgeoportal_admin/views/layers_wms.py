# -*- coding: utf-8 -*-

# Copyright (c) 2017-2021, Camptocamp SA
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of the FreeBSD Project.


from functools import partial
from typing import Any, Dict, List, Optional

import sqlalchemy
from c2cgeoform.schema import GeoFormSchemaNode
from c2cgeoform.views.abstract_views import ItemAction, ListField
from deform.widget import FormWidget
from pyramid.view import view_config, view_defaults
from sqlalchemy import delete, insert, inspect, update
from zope.sqlalchemy import mark_changed

from c2cgeoportal_admin import _
from c2cgeoportal_admin.schemas.dimensions import dimensions_schema_node
from c2cgeoportal_admin.schemas.interfaces import interfaces_schema_node
from c2cgeoportal_admin.schemas.metadata import metadatas_schema_node
from c2cgeoportal_admin.schemas.restriction_areas import restrictionareas_schema_node
from c2cgeoportal_admin.schemas.treeitem import parent_id_node
from c2cgeoportal_admin.views.dimension_layers import DimensionLayerViews
from c2cgeoportal_commons.models.main import LayerGroup, LayerWMS, LayerWMTS, OGCServer, TreeItem

_list_field = partial(ListField, LayerWMS)

base_schema = GeoFormSchemaNode(LayerWMS, widget=FormWidget(fields_template="layer_fields"))
base_schema.add(dimensions_schema_node.clone())
base_schema.add(metadatas_schema_node.clone())
base_schema.add(interfaces_schema_node.clone())
base_schema.add(restrictionareas_schema_node.clone())
base_schema.add_unique_validator(LayerWMS.name, LayerWMS.id)
base_schema.add(parent_id_node(LayerGroup))  # type: ignore


@view_defaults(match_param="table=layers_wms")
class LayerWmsViews(DimensionLayerViews):
    _list_fields = (
        DimensionLayerViews._list_fields
        + [
            _list_field(
                "ogc_server",
                renderer=lambda layer_wms: layer_wms.ogc_server.name,
                sort_column=OGCServer.name,
                filter_column=OGCServer.name,
            ),
            _list_field("layer"),
            _list_field("style"),
            _list_field("valid", label="Valid"),
            _list_field("invalid_reason", visible=False),
            _list_field("time_mode"),
            _list_field("time_widget"),
        ]
        + DimensionLayerViews._extra_list_fields
    )
    _id_field = "id"
    _model = LayerWMS
    _base_schema = base_schema

    def _base_query(self, query: Optional[sqlalchemy.orm.query.Query] = None) -> sqlalchemy.orm.query.Query:
        del query
        return super()._base_query(self._request.dbsession.query(LayerWMS).distinct().outerjoin("ogc_server"))

    @view_config(route_name="c2cgeoform_index", renderer="../templates/index.jinja2")  # type: ignore
    def index(self) -> Dict[str, Any]:
        return super().index()  # type: ignore

    @view_config(route_name="c2cgeoform_grid", renderer="fast_json")  # type: ignore
    def grid(self) -> Dict[str, Any]:
        return super().grid()  # type: ignore

    def _item_actions(self, item: LayerWMS, readonly: bool = False) -> List[ItemAction]:
        actions: List[ItemAction] = super()._item_actions(item, readonly)
        if inspect(item).persistent:
            actions.insert(
                next((i for i, v in enumerate(actions) if v.name() == "delete")),
                ItemAction(
                    name="convert_to_wmts",
                    label=_("Convert to WMTS"),
                    icon="glyphicon icon-l_wmts",
                    url=self._request.route_url("convert_to_wmts", id=getattr(item, self._id_field)),
                    method="POST",
                    confirmation=_("Are you sure you want to convert this layer to WMTS?"),
                ),
            )
        return actions

    @view_config(  # type: ignore
        route_name="c2cgeoform_item", request_method="GET", renderer="../templates/edit.jinja2"
    )
    def view(self) -> Dict[str, Any]:
        if self._is_new():
            dbsession = self._request.dbsession
            default_wms = LayerWMS.get_default(dbsession)
            if default_wms:
                return self.copy(default_wms, excludes=["name", "layer"])  # type: ignore
        return super().edit()  # type: ignore

    @view_config(  # type: ignore
        route_name="c2cgeoform_item", request_method="POST", renderer="../templates/edit.jinja2"
    )
    def save(self) -> Dict[str, Any]:
        return super().save()  # type: ignore

    @view_config(route_name="c2cgeoform_item", request_method="DELETE", renderer="fast_json")  # type: ignore
    def delete(self) -> Dict[str, Any]:
        return super().delete()  # type: ignore

    @view_config(  # type: ignore
        route_name="c2cgeoform_item_duplicate", request_method="GET", renderer="../templates/edit.jinja2"
    )
    def duplicate(self) -> Dict[str, Any]:
        return super().duplicate()  # type: ignore

    @view_config(route_name="convert_to_wmts", request_method="POST", renderer="fast_json")  # type: ignore
    def convert_to_wmts(self) -> Dict[str, Any]:
        src = self._get_object()
        dbsession = self._request.dbsession
        default_wmts = LayerWMTS.get_default(dbsession)
        values = (
            {"url": default_wmts.url, "matrix_set": default_wmts.matrix_set}
            if default_wmts
            else {"url": "", "matrix_set": ""}
        )
        with dbsession.no_autoflush:
            d = delete(LayerWMS.__table__)
            d = d.where(LayerWMS.__table__.c.id == src.id)
            i = insert(LayerWMTS.__table__)
            values.update(
                {
                    "id": src.id,
                    "layer": src.layer,
                    "image_type": src.ogc_server.image_type,
                    "style": src.style,
                }
            )
            i = i.values(values)
            u = update(TreeItem.__table__)
            u = u.where(TreeItem.__table__.c.id == src.id)
            u = u.values({"type": "l_wmts"})
            dbsession.execute(d)
            dbsession.execute(i)
            dbsession.execute(u)
            dbsession.expunge(src)

        dbsession.flush()
        mark_changed(dbsession)

        return {
            "success": True,
            "redirect": self._request.route_url(
                "c2cgeoform_item",
                table="layers_wmts",
                id=self._request.matchdict["id"],
                _query=[("msg_col", "submit_ok")],
            ),
        }
