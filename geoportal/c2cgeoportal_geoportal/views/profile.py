# Copyright (c) 2012-2023, Camptocamp SA
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


import math
from decimal import Decimal
from typing import Any, Dict, List, Tuple

import geojson
import pyramid.request
from pyramid.httpexceptions import HTTPNotFound
from pyramid.i18n import TranslationStringFactory
from pyramid.view import view_config

from c2cgeoportal_geoportal.lib.common_headers import Cache, set_common_headers
from c2cgeoportal_geoportal.views.raster import Raster

_ = TranslationStringFactory("c2cgeoportal")


class Profile(Raster):
    """All the view concerned the profile."""

    def __init__(self, request: pyramid.request.Request):
        Raster.__init__(self, request)

    @view_config(route_name="profile.json", renderer="fast_json")  # type: ignore
    def json(self) -> Dict[str, Any]:
        """Answer to /profile.json."""
        _, points = self._compute_points()
        set_common_headers(self.request, "profile", Cache.PUBLIC_NO)
        return {"profile": points}

    def _compute_points(self) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Compute the alt=fct(dist) array."""
        geom = geojson.loads(self.request.params["geom"], object_hook=geojson.GeoJSON.to_instance)

        layers: List[str]
        if "layers" in self.request.params:
            rasters = {}
            layers = self.request.params["layers"].split(",")
            for layer in layers:
                if layer in self.rasters:
                    rasters[layer] = self.rasters[layer]
                else:
                    raise HTTPNotFound(f"Layer {layer!s} not found")
        else:
            rasters = self.rasters
            layers = list(rasters.keys())
            layers.sort()

        points: List[Dict[str, Any]] = []

        dist = 0
        prev_coord = None
        coords = self._create_points(geom.coordinates, int(self.request.params["nbPoints"]))
        for coord in coords:
            if prev_coord is not None:
                dist += self._dist(prev_coord, coord)

            values = {}
            for ref in list(rasters.keys()):
                value = self._get_raster_value(self.rasters[ref], ref, coord[0], coord[1])
                values[ref] = value

            # 10cm accuracy is enough for distances
            rounded_dist = Decimal(str(dist)).quantize(Decimal("0.1"))
            points.append({"dist": rounded_dist, "values": values, "x": coord[0], "y": coord[1]})
            prev_coord = coord

        return layers, points

    @staticmethod
    def _dist(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Compute the distance between 2 points."""
        return math.sqrt(math.pow(coord1[0] - coord2[0], 2.0) + math.pow(coord1[1] - coord2[1], 2.0))

    def _create_points(self, coords: List[Tuple[float, float]], nb_points: int) -> List[Tuple[float, float]]:
        """Add some points in order to reach roughly the asked number of points."""
        total_length = 0
        prev_coord = None
        for coord in coords:
            if prev_coord is not None:
                total_length += self._dist(prev_coord, coord)
            prev_coord = coord

        if total_length == 0.0:
            return coords

        result: List[Tuple[float, float]] = []
        prev_coord = None
        for coord in coords:
            if prev_coord is not None:
                cur_length = self._dist(prev_coord, coord)
                cur_nb_points = max(int(nb_points * cur_length / total_length + 0.5), 1)
                dx = (coord[0] - prev_coord[0]) / float(cur_nb_points)
                dy = (coord[1] - prev_coord[1]) / float(cur_nb_points)
                for i in range(1, cur_nb_points + 1):
                    result.append((prev_coord[0] + dx * i, prev_coord[1] + dy * i))
            else:
                result.append((coord[0], coord[1]))
            prev_coord = coord
        return result
