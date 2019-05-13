FROM camptocamp/c2cwsgiutils:2 AS base
LABEL maintainer Camptocamp "info@camptocamp.com"

ENV \
  DEBIAN_FRONTEND=noninteractive
RUN \
  . /etc/os-release && \
  apt-get update && \
  apt-get install --assume-yes --no-install-recommends apt-utils gettext && \
  apt-get clean && \
  rm --recursive --force /var/lib/apt/lists/*

COPY requirements.txt /tmp/
RUN \
  python3 -m pip install --disable-pip-version-check --no-cache-dir --requirement=/tmp/requirements.txt && \
  rm --recursive --force /tmp/* /var/tmp/* /root/.cache/*

#############################################################################################################

FROM base AS common-build

RUN \
  . /etc/os-release && \
  apt-get update && \
  apt-get install --assume-yes --no-install-recommends apt-transport-https && \
  echo "deb https://deb.nodesource.com/node_10.x ${VERSION_CODENAME} main" > /etc/apt/sources.list.d/nodesource.list && \
  curl --silent https://deb.nodesource.com/gpgkey/nodesource.gpg.key | apt-key add - && \
  apt-get update && \
  apt-get install --assume-yes --no-install-recommends 'nodejs=10.*' && \
  apt-get clean && \
  rm --recursive --force /var/lib/apt/lists/*

COPY requirements-dev.txt /tmp/
RUN \
  python3 -m pip install --disable-pip-version-check --no-cache-dir --requirement=/tmp/requirements-dev.txt && \
  rm --recursive --force /tmp/* /var/tmp/* /root/.cache/*
# For mypy
RUN \
  touch /usr/local/lib/python3.6/dist-packages/zope/__init__.py && \
  touch /usr/local/lib/python3.6/dist-packages/c2c/__init__.py
# For awscli
COPY etc/bash_completion.d/* /etc/bash_completion.d/

#############################################################################################################

FROM common-build AS build1

ARG MAJOR_VERSION
ENV MAJOR_VERSION=$MAJOR_VERSION

RUN \
  . /etc/os-release && \
  apt-get update && \
  apt-get install --assume-yes --no-install-recommends libxml2-utils && \
  apt-get clean && \
  rm --recursive --force /var/lib/apt/lists/*

COPY geoportal/package.json /app/c2cgeoportal/geoportal/
WORKDIR /app/c2cgeoportal/geoportal
RUN \
  npm --no-optional --global --unsafe-perm --no-package-lock install ngeo && \
  npm cache clear --force && \
  rm -rf /tmp/*

COPY bin/npm-packages /usr/bin/
RUN npm-packages \
  @camptocamp/cesium @type jasmine-core karma karma-chrome-launcher karma-coverage \
  karma-coverage-istanbul-reporter karma-jasmine karma-sourcemap-loader karma-webpack \
  typedoc typescript \
  --src=/usr/lib/node_modules/ngeo/package.json --src=package.json --dst=npm-packages

COPY admin/package.json /app/c2cgeoportal/admin/
WORKDIR /app/c2cgeoportal/admin
RUN \
  npm --no-optional --no-package-lock install && \
  npm cache clear --force && \
  rm -rf /tmp/*

FROM common-build AS common-build-npm

COPY --from=build1 /app/c2cgeoportal/geoportal/npm-packages /opt/npm-packages
RUN \
  npm install --no-optional --global --unsafe-perm --no-package-lock $(cat /opt/npm-packages) && \
  npm cache clear --force && \
  rm -rf /tmp/*
RUN \
  git clone --branch=v1.7.x --depth=1 --single-branch https://github.com/angular/angular.js.git \
  /tmp/angular && \
  mv /tmp/angular/src/ngLocale/ /opt/angular-locale/ &&\
  rm -rf /tmp/angular
RUN \
  curl --output /opt/jasperreport.xsd http://jasperreports.sourceforge.net/xsd/jasperreport.xsd

#############################################################################################################

FROM build1 AS build

COPY . /app/c2cgeoportal/
WORKDIR /app/c2cgeoportal
COPY bin/import-ngeo-apps bin/eval-templates bin/wait-db /usr/bin/
RUN make build
RUN python3 -m pip install --editable=commons --editable=geoportal --editable=admin

#############################################################################################################
# Image used to build the project

FROM common-build-npm AS builder

WORKDIR /src

ENV NODE_PATH=/usr/lib/node_modules
COPY webpack.config.js /tmp
COPY bin/extract-ngeo-dependencies /usr/bin/

RUN \
  extract-ngeo-dependencies > /tmp/deps.js && \
  cd /tmp && \
  webpack --mode production --profile --json > stats.json

COPY --from=build /app/c2cgeoportal/geoportal/c2cgeoportal_geoportal/locale/ \
    /opt/c2cgeoportal_geoportal/c2cgeoportal_geoportal/locale/

#############################################################################################################

FROM build AS build-upgrade

RUN rm --recursive --force /app/c2cgeoportal/*/tests

#############################################################################################################

FROM build-upgrade AS build-run

RUN rm --recursive --force /app/c2cgeoportal/geoportal/c2cgeoportal_geoportal/scaffolds

#############################################################################################################
# Image used to run the project

FROM base AS runner

ARG VERSION
ENV VERSION=$VERSION

COPY bin/eval-templates bin/wait-db bin/update-po /usr/bin/
COPY --from=build-run /app/c2cgeoportal/commons /opt/c2cgeoportal_commons
COPY --from=build-run /app/c2cgeoportal/geoportal /opt/c2cgeoportal_geoportal
COPY --from=build-run /app/c2cgeoportal/admin /opt/c2cgeoportal_admin

RUN \
  ln -s /opt/c2cgeoportal_commons/c2cgeoportal_commons/alembic /opt && \
  python3 -m pip install --disable-pip-version-check --no-cache-dir --no-deps \
    --editable=/opt/c2cgeoportal_commons \
    --editable=/opt/c2cgeoportal_geoportal \
    --editable=/opt/c2cgeoportal_admin

RUN adduser www-data root

#############################################################################################################
# Image used to upgrade the project

FROM base AS upgrader

ARG VERSION
ENV VERSION=$VERSION

WORKDIR /src
COPY bin/run /usr/bin/
COPY --from=build-upgrade /app/c2cgeoportal/commons /opt/c2cgeoportal_commons
COPY --from=build-upgrade /app/c2cgeoportal/geoportal /opt/c2cgeoportal_geoportal

RUN \
  python3 -m pip install --disable-pip-version-check --no-cache-dir --no-deps \
    --editable=/opt/c2cgeoportal_commons \
    --editable=/opt/c2cgeoportal_geoportal && \
  pcreate -l|grep c2cgeoportal

#############################################################################################################

FROM build AS checks
RUN make checks
