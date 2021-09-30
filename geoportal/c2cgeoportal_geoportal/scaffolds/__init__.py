# Copyright (c) 2011-2021, Camptocamp SA
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


import glob
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, Iterable, List, Optional, Type, Union, cast

import requests
import yaml
from pyramid.compat import input_
from pyramid.scaffolds.template import Template


class BaseTemplate(Template):  # type: ignore
    """
    A class that can be used as a base class for c2cgeoportal scaffolding templates.

    Greatly inspired from ``pyramid.scaffolds.template.PyramidTemplate``.
    """

    def pre(  # pylint: disable=arguments-renamed
        self, command: str, output_dir: str, vars_: Dict[str, Union[str, int]]
    ) -> None:
        """
        Override ``pyramid.scaffold.template.Template.pre``.

        Adding several variables to the default variables list.

        Also prevents common misnaming (such as naming a package "site" or naming a package logger "root").
        """
        self._get_vars(vars_, "package", "Get a package name: ")
        self._get_vars(vars_, "srid", "Spatial Reference System Identifier (e.g. 2056): ", int)
        srid = cast(int, vars_["srid"])
        extent = self._epsg2bbox(srid)
        self._get_vars(
            vars_,
            "extent",
            "Extent (minx miny maxx maxy): in EPSG: {srid} projection, default is "
            "[{bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}]: ".format(srid=srid, bbox=extent)
            if extent
            else f"Extent (minx miny maxx maxy): in EPSG: {srid} projection: ",
        )
        match = re.match(r"([\d.]+)[,; ] *([\d.]+)[,; ] *([\d.]+)[,; ] *([\d.]+)", cast(str, vars_["extent"]))
        if match is not None:
            extent = [match.group(n + 1) for n in range(4)]
        assert extent is not None
        vars_["extent"] = ",".join(extent)
        vars_["extent_mapserver"] = " ".join(extent)

        super().pre(command, output_dir, vars_)

        if vars_["package"] == "site":
            raise ValueError(
                "Sorry, you may not name your package 'site'. "
                "The package name 'site' has a special meaning in "
                "Python.  Please name it anything except 'site'."
            )

        package_logger = vars_["package"]
        if package_logger == "root":
            # Rename the app logger in the rare case a project
            # is named "root"
            package_logger = "app"
        vars_["package_logger"] = package_logger
        vars_["geomapfish_version"] = os.environ["VERSION"]
        # Used in the Docker files to shoos the version of the build image
        vars_["geomapfish_version_tag"] = "GEOMAPFISH_VERSION"
        vars_["geomapfish_version_tag_env"] = "${GEOMAPFISH_VERSION}"
        geomapfish_major_version_tag = (
            "GEOMAPFISH_VERSION" if vars_.get("unsafe_long_version", False) else "GEOMAPFISH_MAIN_VERSION"
        )
        # Used in the Docker files to shoos the version of the run image
        vars_["geomapfish_major_version_tag"] = geomapfish_major_version_tag
        vars_["geomapfish_major_version_tag_env"] = "${" + geomapfish_major_version_tag + "}"
        vars_["geomapfish_main_version"] = os.environ["MAJOR_VERSION"]
        vars_["geomapfish_main_version_dash"] = os.environ["MAJOR_VERSION"].replace(".", "-")

    @staticmethod
    def out(msg: str) -> None:
        print(msg)

    @staticmethod
    def _get_vars(vars_: Dict[str, Any], name: str, prompt: str, type_: Optional[Type[Any]] = None) -> None:
        """Set an attribute in the vars dict."""
        if name.upper() in os.environ and os.environ[name.upper()] != "":
            value = os.environ.get(name.upper())
        else:
            value = vars_.get(name)

        if value is None:
            value = input_(prompt).strip()

        if type_ is not None and not isinstance(value, type_):
            try:
                value = type_(value)
            except ValueError:
                print(f"The attribute {name}={value} is not a {type_}")
                sys.exit(1)

        vars_[name] = value

    @staticmethod
    def _epsg2bbox(srid: int) -> Optional[List[str]]:
        try:
            r = requests.get(f"https://epsg.io/?format=json&q={srid}")
            bbox = r.json()["results"][0]["bbox"]
            r = requests.get(
                "https://epsg.io/trans?s_srs=4326&t_srs={srid}&data={bbox[1]},{bbox[0]}".format(
                    srid=srid, bbox=bbox
                )
            )
            r1 = r.json()[0]
            r = requests.get(
                "https://epsg.io/trans?s_srs=4326&t_srs={srid}&data={bbox[3]},{bbox[2]}".format(
                    srid=srid, bbox=bbox
                )
            )
            r2 = r.json()[0]
            return [r1["x"], r2["y"], r2["x"], r1["y"]]
        except requests.RequestException:
            print("Failed to establish a connection to epsg.io.")
        except json.JSONDecodeError:
            print("epsg.io doesn't return a correct json.")
        except IndexError:
            print("Unable to get the bbox")
        except Exception as exception:
            print(f"unexpected error: {str(exception)}")
        return None


def fix_executables(output_dir: str, patterns: Iterable[str], in_const_create_template: bool = False) -> None:
    """Fix the executable flag."""
    if os.name == "posix":
        for pattern in patterns:
            if in_const_create_template:
                pattern = os.path.join(output_dir, "CONST_create_template", pattern)
            else:
                pattern = os.path.join(output_dir, pattern)
            for file_ in glob.glob(pattern):
                subprocess.check_call(["chmod", "+x", file_])


def _gen_authtkt_secret() -> str:
    if os.environ.get("CI") == "true":
        return "io7heoDui8xaikie1rushaeGeiph8Bequei6ohchaequob6viejei0xooWeuvohf"
    return subprocess.check_output(["pwgen", "64"]).decode().strip()


class TemplateCreate(BaseTemplate):
    """
    The create template.

    Not used on application update but is copied in the CONST_create_template folder of the update template.
    """

    _template_dir = "create"
    summary = "Template used to create a c2cgeoportal project"

    def pre(self, command: str, output_dir: str, vars_: Dict[str, Union[str, int]]) -> None:
        """Override the base template."""
        super().pre(command, output_dir, vars_)
        vars_["authtkt_secret"] = _gen_authtkt_secret()

    def post(  # pylint: disable=arguments-renamed
        self, command: str, output_dir: str, vars_: Dict[str, str]
    ) -> None:
        """Override the base template class to print the next step."""

        print("Fix executable")
        fix_executables(output_dir, ("bin/*", "scripts/*", "build", "ci/trigger"))

        super().post(command, output_dir, vars_)

        print("Welcome to GeoMapFish!")


class TemplateUpdate(BaseTemplate):
    """The update template."""

    _template_dir = "update"
    summary = "Template used to update a c2cgeoportal project"

    @staticmethod
    def open_project(output_dir: str, vars_: Dict[str, Union[str, int]]) -> None:
        project_file = os.path.join(output_dir, "project.yaml")
        if os.path.exists(project_file):
            with open(project_file, encoding="utf8") as f:
                project = yaml.safe_load(f)
                if "template_vars" in project:
                    for key, value in list(project["template_vars"].items()):
                        vars_[key] = value
        else:
            print("Missing project file: " + project_file)
            sys.exit(1)

    def pre(self, command: str, output_dir: str, vars_: Dict[str, Union[str, int]]) -> None:
        """Override the base template."""
        self.open_project(output_dir, vars_)

        if "authtkt_secret" not in vars_:
            vars_["authtkt_secret"] = _gen_authtkt_secret()

        super().pre(command, output_dir, vars_)

    def post(  # pylint: disable=arguments-renamed
        self, command: str, output_dir: str, vars_: Dict[str, str]
    ) -> None:
        """
        Override the base template class to print "Welcome to c2cgeoportal!".

        After a successful scaffolding        rendering.
        """

        print("Fix executable")
        fix_executables(output_dir, ("bin/*", "scripts/*", "build", "ci/trigger"), True)

        super().post(command, output_dir, vars_)


class TemplateAdvanceCreate(TemplateCreate):
    """
    The create template for advance application.

    Not used on application update but is copied in the CONST_create_template folder of the update template.
    """

    _template_dir = "advance_create"
    summary = "Template used to create a advance c2cgeoportal project"


class TemplateAdvanceUpdate(TemplateUpdate):
    """The update template for advance application."""

    _template_dir = "advance_update"
    summary = "Template used to update a advance c2cgeoportal project"
