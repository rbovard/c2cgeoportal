FROM ubuntu:20.04

# Fail on error on pipe, see: https://github.com/hadolint/hadolint/wiki/DL4006.
# Treat unset variables as an error when substituting.
# Print commands and their arguments as they are executed.
SHELL ["/bin/bash", "-o", "pipefail", "-cux"]

RUN . /etc/os-release && \
    apt-get update && \
    apt-get install --assume-yes --no-install-recommends python3-pip gettext curl gnupg && \
    echo "deb https://deb.nodesource.com/node_16.x ${VERSION_CODENAME} main" > /etc/apt/sources.list.d/nodesource.list && \
    curl --silent https://deb.nodesource.com/gpgkey/nodesource.gpg.key | apt-key add - && \
    apt-get update && \
    apt-get install --assume-yes --no-install-recommends 'nodejs=16.*'

COPY requirements.txt /tmp/
RUN python3 -m pip install --disable-pip-version-check --no-cache-dir --requirement=/tmp/requirements.txt

COPY Pipfile Pipfile.lock /tmp/
RUN \
  cd /tmp && LC_ALL=C.UTF-8 LANG=C.UTF-8 pipenv sync --system --clear

#COPY package.json /doc/
#RUN cd /doc && npm install
#RUN npm install --global typedoc

ARG MAJOR_VERSION
ARG MAIN_BRANCH

COPY . /doc
WORKDIR /doc

RUN ./eval-templates
RUN mv typedoc /usr/bin
RUN mkdir --parent _build/html
#RUN rm node_modules/ngeo/srcapi/**/*.spec.ts
#RUN cp typedoc.json tsconfig.json node_modules/ngeo
RUN sphinx-build -b html -d _build/doctrees . _build/html
RUN ./build.sh
