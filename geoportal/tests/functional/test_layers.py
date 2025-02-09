# Copyright (c) 2013-2023, Camptocamp SA
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

# pylint: disable=missing-docstring,attribute-defined-outside-init,protected-access,no-value-for-parameter


from unittest import TestCase

from tests.functional import cleanup_db, create_default_ogcserver, create_dummy_request
from tests.functional import setup_common as setup_module  # noqa
from tests.functional import setup_db
from tests.functional import teardown_common as teardown_module  # noqa


class TestLayers(TestCase):
    _table_index = 0
    _tables = None

    def setup_method(self, _):
        setup_module()

        import transaction

        from c2cgeoportal_commons.models import DBSession
        from c2cgeoportal_commons.models.main import Interface, Role
        from c2cgeoportal_commons.models.static import User

        setup_db()

        self.metadata = None
        self.layer_ids = []

        for o in DBSession.query(User).all():
            DBSession.delete(o)

        self.role = Role(name="__test_role")
        self.user = User(
            username="__test_user", password="__test_user", settings_role=self.role, roles=[self.role]
        )
        self.main = Interface(name="main")

        DBSession.add(self.user)
        DBSession.add(self.role)
        DBSession.add(self.main)

        create_default_ogcserver()

        transaction.commit()

    def teardown_method(self, _):
        import transaction

        cleanup_db()

        if self._tables is not None:
            for table in self._tables[::-1]:
                table.drop()

        transaction.commit()

    def _create_layer(
        self,
        public=False,
        none_area=False,
        attr_list=False,
        exclude_properties=False,
        metadatas=None,
        geom_type=False,
    ):
        """
        This function is central for this test class.

        It creates a layer with two features, and associates a restriction area to it.
        """
        import transaction
        from geoalchemy2 import Geometry, WKTElement
        from sqlalchemy import CheckConstraint, Column, ForeignKey, Table, types
        from sqlalchemy.ext.declarative import declarative_base

        from c2cgeoportal_commons.models import DBSession
        from c2cgeoportal_commons.models.main import LayerWMS, OGCServer, RestrictionArea

        if self._tables is None:
            self._tables = []

        self.__class__._table_index += 1
        id = self.__class__._table_index

        engine = DBSession.c2c_rw_bind
        connection = engine.connect()

        if not self.metadata:
            self.metadata = declarative_base(bind=engine).metadata

        tablename = f"table_{id:d}"

        table1 = Table(
            f"{tablename!s}_child",
            self.metadata,
            Column("id", types.Integer, primary_key=True),
            Column("name", types.Unicode),
            schema="public",
        )
        if geom_type:
            table1.append_column(Column("geom", Geometry("POINT", srid=21781)))
        else:
            table1.append_column(Column("geom", Geometry(srid=21781)))
        self._tables.append(table1)

        table2 = Table(
            tablename,
            self.metadata,
            Column("id", types.Integer, primary_key=True),
            Column("child_id", types.Integer, ForeignKey(f"public.{tablename!s}_child.id")),
            Column("name", types.Unicode),
            Column(
                "email",
                types.Unicode,
                CheckConstraint(
                    """email ~* '^[A-Za-z0-9._%%-]
                                      +@[A-Za-z0-9.-]+[.][A-Za-z]+$'""",
                    name="proper_email",
                ),
            ),
            Column("last_update_user", types.Unicode),
            Column("last_update_date", types.DateTime),
            schema="public",
        )
        if geom_type:
            table2.append_column(Column("geom", Geometry("POINT", srid=21781)))
        else:
            table2.append_column(Column("geom", Geometry(srid=21781)))
        self._tables.append(table2)

        table1.drop(checkfirst=True)
        table2.drop(checkfirst=True)
        table1.create()
        table2.create()

        ins = table1.insert().values(name="c1é")
        c1_id = connection.execute(ins).inserted_primary_key[0]
        ins = table1.insert().values(name="c2é")
        c2_id = connection.execute(ins).inserted_primary_key[0]

        ins = table2.insert().values(child_id=c1_id, name="foo", geom=WKTElement("POINT(5 45)", 21781))
        connection.execute(ins)
        ins = table2.insert().values(child_id=c2_id, name="bar", geom=WKTElement("POINT(6 46)", 21781))
        connection.execute(ins)
        if attr_list:
            ins = table2.insert().values(
                child_id=c2_id, name="aaa,bbb,foo", geom=WKTElement("POINT(6 46)", 21781)
            )
            connection.execute(ins)

        ogc_server = DBSession.query(OGCServer).filter(OGCServer.name == "__test_ogc_server").one()
        layer = LayerWMS()
        layer.id = id
        layer.name = str(id)
        layer.ogc_server = ogc_server
        layer.geo_table = tablename
        layer.public = public
        layer.interface = [self.main]

        if exclude_properties:
            layer.exclude_properties = "name"

        if metadatas:
            layer.metadatas = metadatas

        DBSession.add(layer)

        if not public:
            ra = RestrictionArea()
            ra.name = "__test_ra"
            ra.layers = [layer]
            ra.roles = [self.role]
            ra.readwrite = True
            if not none_area:
                poly = "POLYGON((4 44, 4 46, 6 46, 6 44, 4 44))"
                ra.area = WKTElement(poly, srid=21781)
            DBSession.add(ra)

        transaction.commit()

        self.layer_ids.append(id)
        return id

    @staticmethod
    def _get_request(layerid, username=None):
        from c2cgeoportal_commons.models import DBSession
        from c2cgeoportal_commons.models.static import User

        request = create_dummy_request()
        request.matchdict = {"layer_id": str(layerid)}
        if username is not None:
            request.user = DBSession.query(User).filter_by(username=username).one()
        return request

    def test_read_public(self):
        from geojson.feature import FeatureCollection

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(public=True)
        request = self._get_request(layer_id)

        collection = Layers(request).read_many()
        self.assertTrue(isinstance(collection, FeatureCollection))
        self.assertEqual([f.properties["child"] for f in collection.features], ["c1é", "c2é"])

    def test_read_many_no_auth(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id)

        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.read_many)

    def test_read_many(self):
        from geojson.feature import FeatureCollection

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")

        layers = Layers(request)
        collection = layers.read_many()
        self.assertTrue(isinstance(collection, FeatureCollection))
        assert [f.properties["child"] for f in collection.features] == ["c1é"]

    def test_read_many_layer_not_found(self):
        from pyramid.httpexceptions import HTTPNotFound

        from c2cgeoportal_geoportal.views.layers import Layers

        self._create_layer()
        request = self._get_request(10000, username="__test_user")

        layers = Layers(request)
        self.assertRaises(HTTPNotFound, layers.read_many)

    def test_read_many_multi(self):
        from geojson.feature import FeatureCollection

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id1 = self._create_layer()
        layer_id2 = self._create_layer()
        layer_id3 = self._create_layer()

        layer_ids = f"{layer_id1:d},{layer_id2:d},{layer_id3:d}"
        request = self._get_request(layer_ids, username="__test_user")

        layers = Layers(request)
        collection = layers.read_many()
        self.assertTrue(isinstance(collection, FeatureCollection))
        self.assertEqual(
            [f.properties["__layer_id__"] for f in collection.features], [layer_id1, layer_id2, layer_id3]
        )

    def test_read_one_public(self):
        from geojson.feature import Feature

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(public=True)
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 1

        layers = Layers(request)
        feature = layers.read_one()
        self.assertTrue(isinstance(feature, Feature))
        assert feature.id == 1
        assert feature.properties["name"] == "foo"
        assert feature.properties["child"] == "c1é"

    def test_read_one_public_notfound(self):
        from pyramid.httpexceptions import HTTPNotFound

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(public=True)
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 10000

        layers = Layers(request)
        feature = layers.read_one()
        self.assertTrue(isinstance(feature, HTTPNotFound))

    def test_read_one_no_auth(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 1

        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.read_one)

    def test_read_one_no_perm(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 2

        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.read_one)

    def test_read_one(self):
        from geojson.feature import Feature

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1

        layers = Layers(request)
        feature = layers.read_one()
        self.assertTrue(isinstance(feature, Feature))
        assert feature.id == 1
        assert feature.properties["name"] == "foo"
        assert feature.properties["child"] == "c1é"

    def test_count(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id)

        layers = Layers(request)
        response = layers.count()
        assert response == 2

    def test_create_no_auth(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id)
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}, {"type": "Feature", "properties": {"text": "foo", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}]}'  # noqa
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.create)

    def test_create_no_perm(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [4, 44]}}, {"type": "Feature", "properties": {"text": "foo", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}]}'  # noqa
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.create)

    def test_create(self):
        from geojson.feature import FeatureCollection

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}, {"type": "Feature", "properties": {"text": "foo", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}]}'  # noqa
        layers = Layers(request)
        collection = layers.create()
        self.assertTrue(isinstance(collection, FeatureCollection))
        assert len(collection.features) == 2

    def test_create_with_constraint_fail_integrity(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"email": "novalidemail", "name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}, {"type": "Feature", "properties": {"text": "foo", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}]}'  # noqa
        layers = Layers(request)
        response = layers.create()
        assert request.response.status_int == 400
        self.assertTrue("error_type" in response)
        self.assertTrue("message" in response)
        assert response["error_type"] == "integrity_error"

    def test_create_log(self):
        from datetime import datetime

        from geojson.feature import FeatureCollection

        from c2cgeoportal_commons.models import DBSession
        from c2cgeoportal_commons.models.main import Metadata
        from c2cgeoportal_commons.models.static import User
        from c2cgeoportal_geoportal.views.layers import Layers

        self.assertEqual(DBSession.query(User.username).all(), [("__test_user",)])

        metadatas = [
            Metadata("lastUpdateDateColumn", "last_update_date"),
            Metadata("lastUpdateUserColumn", "last_update_user"),
        ]
        layer_id = self._create_layer(metadatas=metadatas)
        request = self._get_request(layer_id, username="__test_user")
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}]}'  # noqa
        layers = Layers(request)
        collection = layers.create()
        assert request.response.status_int == 201
        self.assertTrue(isinstance(collection, FeatureCollection))
        assert len(collection.features) == 1
        properties = collection.features[0]

        assert request.user.username == "__test_user"

        assert properties.last_update_user == request.user.id
        self.assertIsInstance(properties.last_update_date, datetime)

    def test_create_validation_fails(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}, {"type": "Feature", "properties": {"text": "foo", "child": "c2é"}, "geometry": {"type": "LineString", "coordinates": [[5, 45], [5, 45]]}}]}'  # noqa
        layers = Layers(request)
        response = layers.create()
        assert request.response.status_int == 400
        self.assertTrue("error_type" in response)
        self.assertTrue("message" in response)
        assert response["error_type"] == "validation_error"
        assert response["message"] == "Too few points in geometry component[5 45]"

    def test_create_no_validation(self):
        from geojson.feature import FeatureCollection

        from c2cgeoportal_commons.models.main import Metadata
        from c2cgeoportal_geoportal.views.layers import Layers

        metadatas = [Metadata("geometryValidation", "False")]
        layer_id = self._create_layer(metadatas=metadatas, geom_type=False)
        request = self._get_request(layer_id, username="__test_user")
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}, {"type": "Feature", "properties": {"text": "foo", "child": "c2é"}, "geometry": {"type": "LineString", "coordinates": [[5, 45], [5, 45]]}}]}'  # noqa
        layers = Layers(request)
        collection = layers.create()
        assert request.response.status_int == 201
        self.assertTrue(isinstance(collection, FeatureCollection))
        assert len(collection.features) == 2

    def test_update_no_auth(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}'  # noqa
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.update)

    def test_update_no_perm_dst_geom(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [4, 44]}}'  # noqa
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.update)

    def test_update_no_perm_src_geom(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 2
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}'  # noqa
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.update)

    def test_update(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}'  # noqa
        layers = Layers(request)
        feature = layers.update()
        assert feature.id == 1
        assert feature.name == "foobar"
        assert feature.child == "c2é"

    def test_update_log(self):
        from datetime import datetime

        from c2cgeoportal_commons.models.main import Metadata
        from c2cgeoportal_geoportal.views.layers import Layers

        metadatas = [
            Metadata("lastUpdateDateColumn", "last_update_date"),
            Metadata("lastUpdateUserColumn", "last_update_user"),
        ]
        layer_id = self._create_layer(metadatas=metadatas)
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}'  # noqa
        layers = Layers(request)
        feature = layers.update()
        assert feature.id == 1
        assert feature.last_update_user == request.user.id
        self.assertIsInstance(feature.last_update_date, datetime)

    def test_update_validation_fails(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "LineString", "coordinates": [[5, 45], [5, 45]]}}'  # noqa
        layers = Layers(request)
        response = layers.update()
        assert request.response.status_int == 400
        self.assertTrue("error_type" in response)
        self.assertTrue("message" in response)
        assert response["error_type"] == "validation_error"
        assert response["message"] == "Too few points in geometry component[5 45]"

    def test_update_validation_fails_simple(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "LineString", "coordinates": [[5, 45], [6, 45], [5, 45]]}}'  # noqa
        layers = Layers(request)
        response = layers.update()
        assert request.response.status_int == 400
        self.assertTrue("error_type" in response)
        self.assertTrue("message" in response)
        assert response["error_type"] == "validation_error"
        assert response["message"] == "Not simple"

    def test_update_validation_fails_constraint(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"email": "novalidemail"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}'  # noqa
        layers = Layers(request)
        response = layers.update()
        assert request.response.status_int == 400
        self.assertTrue("error_type" in response)
        self.assertTrue("message" in response)
        assert response["error_type"] == "integrity_error"

    def test_update_no_validation(self):
        from c2cgeoportal_commons.models.main import Metadata
        from c2cgeoportal_geoportal.views.layers import Layers

        metadatas = [Metadata("geometryValidation", "False")]
        layer_id = self._create_layer(metadatas=metadatas, geom_type=False)
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "LineString", "coordinates": [[5, 45], [5, 45]]}}'  # noqa
        layers = Layers(request)
        feature = layers.update()
        assert feature.id == 1
        assert feature.name == "foobar"
        assert feature.child == "c2é"

    def test_delete_no_auth(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 2
        request.method = "DELETE"
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.delete)

    def test_delete_no_perm(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 2
        request.method = "DELETE"
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.delete)

    def test_delete(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "DELETE"
        layers = Layers(request)
        response = layers.delete()
        assert response.status_int == 204

    def test_metadata_no_auth(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id)

        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.metadata)

    def test_metadata(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer()
        request = self._get_request(layer_id, username="__test_user")

        layers = Layers(request)
        cls = layers.metadata()
        assert cls.__table__.name == f"table_{layer_id:d}"
        self.assertTrue(hasattr(cls, "name"))
        self.assertTrue("child" in cls.__dict__)

    def test_metadata_log(self):
        from c2cgeoportal_commons.models.main import Metadata
        from c2cgeoportal_geoportal.views.layers import Layers

        metadatas = [
            Metadata("lastUpdateDateColumn", "last_update_date"),
            Metadata("lastUpdateUserColumn", "last_update_user"),
        ]
        layer_id = self._create_layer(metadatas=metadatas)
        request = self._get_request(layer_id, username="__test_user")

        layers = Layers(request)
        cls = layers.metadata()
        self.assertFalse(hasattr(cls, "last_update_date"))
        self.assertFalse(hasattr(cls, "last_update_user"))

    def test_metadata_exclude_properties(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(exclude_properties=True)
        request = self._get_request(layer_id, username="__test_user")

        layers = Layers(request)
        cls = layers.metadata()
        self.assertFalse(hasattr(cls, "name"))

    def test_metadata_columns_order(self):
        from c2cgeoportal_commons.models.main import Metadata
        from c2cgeoportal_geoportal.views.layers import Layers

        attributes_order = "name,email,child_id"

        layer_id = self._create_layer(metadatas=[Metadata("editingAttributesOrder", attributes_order)])
        request = self._get_request(layer_id, username="__test_user")

        layers = Layers(request)
        cls = layers.metadata()

        self.assertEqual(attributes_order.split(","), cls.__attributes_order__)

    def test_metadata_editing_enumeration_config(self):
        import json

        from c2cgeoportal_commons.models.main import Metadata
        from c2cgeoportal_geoportal.views.layers import Layers

        editing_enumerations = '{"a_column": {"value": "value_column", "order_by": "order_column"}}'

        metadatas = [Metadata("editingEnumerations", editing_enumerations)]
        layer_id = self._create_layer(metadatas=metadatas)
        request = self._get_request(layer_id, username="__test_user")

        layers = Layers(request)
        cls = layers.metadata()

        assert json.loads(editing_enumerations) == cls.__enumerations_config__

    # # # With None area # # #
    def test_read_public_none_area(self):
        from geojson.feature import FeatureCollection

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(public=True, none_area=True)
        request = self._get_request(layer_id)

        layers = Layers(request)
        collection = layers.read_many()
        self.assertTrue(isinstance(collection, FeatureCollection))
        self.assertEqual([f.properties["child"] for f in collection.features], ["c1é", "c2é"])

    def test_read_many_no_auth_none_area(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id)

        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.read_many)

    def test_read_many_none_area(self):
        from geojson.feature import FeatureCollection

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id, username="__test_user")

        layers = Layers(request)
        collection = layers.read_many()
        self.assertTrue(isinstance(collection, FeatureCollection))
        assert len(collection.features) == 2
        assert collection.features[0].properties["child"] == "c1é"
        assert collection.features[1].properties["child"] == "c2é"

    def test_read_one_public_none_area(self):
        from geojson.feature import Feature

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(public=True, none_area=True)
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 1

        layers = Layers(request)
        feature = layers.read_one()
        self.assertTrue(isinstance(feature, Feature))
        assert feature.id == 1
        assert feature.properties["name"] == "foo"
        assert feature.properties["child"] == "c1é"

    def test_read_one_no_auth_none_area(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 1

        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.read_one)

    def test_read_one_none_area(self):
        from geojson.feature import Feature

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1

        layers = Layers(request)
        feature = layers.read_one()
        self.assertTrue(isinstance(feature, Feature))
        assert feature.id == 1
        assert feature.properties["name"] == "foo"
        assert feature.properties["child"] == "c1é"

    def test_count_none_area(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id)

        layers = Layers(request)
        response = layers.count()
        assert response == 2

    def test_create_no_auth_none_area(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id)
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}, {"type": "Feature", "properties": {"text": "foo", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}]}'  # noqa
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.create)

    def test_create_none_area(self):
        from geojson.feature import FeatureCollection

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id, username="__test_user")
        request.method = "POST"
        request.body = '{"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "foo", "child": "c1é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}, {"type": "Feature", "properties": {"text": "foo", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}]}'  # noqa
        layers = Layers(request)
        collection = layers.create()
        self.assertTrue(isinstance(collection, FeatureCollection))
        assert len(collection.features) == 2

    def test_update_no_auth_none_area(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}'  # noqa
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.update)

    def test_update_none_area(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "PUT"
        request.body = '{"type": "Feature", "id": 1, "properties": {"name": "foobar", "child": "c2é"}, "geometry": {"type": "Point", "coordinates": [5, 45]}}'  # noqa
        layers = Layers(request)
        feature = layers.update()
        assert feature.id == 1
        assert feature.name == "foobar"
        assert feature.child == "c2é"

    def test_delete_no_auth_none_area(self):
        from pyramid.httpexceptions import HTTPForbidden

        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id)
        request.matchdict["feature_id"] = 2
        request.method = "DELETE"
        layers = Layers(request)
        self.assertRaises(HTTPForbidden, layers.delete)

    def test_delete_none_area(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(none_area=True)
        request = self._get_request(layer_id, username="__test_user")
        request.matchdict["feature_id"] = 1
        request.method = "DELETE"
        layers = Layers(request)
        response = layers.delete()
        assert response.status_int == 204

    def test_enumerate_attribute_values(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(public=True)
        tablename = f"table_{layer_id:d}"
        settings = {
            "layers": {
                "enum": {"layer_test": {"attributes": {"label": {"table": tablename, "column_name": "name"}}}}
            }
        }

        request = self._get_request(layer_id)
        request.registry.settings.update(settings)
        request.matchdict["layer_name"] = "layer_test"
        request.matchdict["field_name"] = "label"
        layers = Layers(request)
        response = layers.enumerate_attribute_values()
        self.assertEqual(response, {"items": [{"value": "bar"}, {"value": "foo"}]})

    def test_enumerate_attribute_values_list(self):
        from c2cgeoportal_geoportal.views.layers import Layers

        layer_id = self._create_layer(public=True, attr_list=True)
        tablename = f"table_{layer_id:d}"
        settings = {
            "layers": {
                "enum": {
                    "layer_test": {
                        "attributes": {"label": {"table": tablename, "column_name": "name", "separator": ","}}
                    }
                }
            }
        }

        request = self._get_request(layer_id)
        request.registry.settings.update(settings)
        request.matchdict["layer_name"] = "layer_test"
        request.matchdict["field_name"] = "label"

        layers = Layers(request)
        response = layers.enumerate_attribute_values()
        self.assertEqual(
            response, {"items": [{"value": "aaa"}, {"value": "bar"}, {"value": "bbb"}, {"value": "foo"}]}
        )
