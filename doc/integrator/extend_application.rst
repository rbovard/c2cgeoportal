.. _extend_application:

Extend the application
======================

To add an additional component in the project in simple mode we should:

- use an interface in canvas mode
- add a custom docker-compose service
- add a custom JavaScript file

Interface in canvas mode
------------------------

Get the files from the ``CONST_create_template``:

.. prompt:: bash

    mkdir -p geoportal/interfaces/
    cp CONST_create_template/geoportal/interfaces/desktop_alt.html.mako \
        geoportal/interfaces/desktop.html.mako
    mkdir -p geoportal/<package>_geoportal/static/images/
    cp CONST_create_template/geoportal/<package>_geoportal/static/images/background-layer-button.png \
        geoportal/<package>_geoportal/static/images/

In the file ``geoportal/interfaces/desktop.html.mako`` your can see that there is some HTML tags that
have an attribute slot. The slot says where the component should be added:

- ``header`` -> in the header part of the page.
- ``data`` -> in the data panel on the left of the map.
- ``tool-button`` -> in the tools on the right of the map.
- ``tool-button-separate`` -> in the tools on the right of the map, for the shared button.
- ``tool-<panel-name>`` -> in the tools panel on the right of the map, when the tool is activated.
- ``footer-<panel-name>`` -> in the footer part of the page, when the panel is activated.

In the ``vars.yaml`` file your interface should be declared like that:

.. code:: yaml

   interfaces:
     - name: desktop
       type: canvas
       layout: desktop
       default: true

The ``name`` is the interface name as usual.
The ``type`` should be set to 'canvas' to be able to get the canvas based interface present in the config image.
The ``layout`` is used to get the JavaScript and CSS files from ngeo.
The ``default`` is used to set the default interface as usual.

In the file ``geoportal/interfaces/desktop.html.mako`` you will use the following variables:

- ``request`` -> the Pyramid request.
- ``header`` -> the header additional part of the page, the ``dynamicUrl`` and ``interface`` meta, and the CSS inclusion.
- ``spinner`` -> the spinner SVG image content.
- ``footer`` -> the footer additional part of the page, for the JavaScript inclusion.

Custom docker-compose service
-----------------------------

In this chapter we will create a new Pyramid application that use cornice in a Docker image.

We will use the Pyramid Cookiecutter starter, we can use it directly
(by running ``cookiecutter gh:Pylons/pyramid-cookiecutter-starter``) if you want to do your
image by your own, but in this tutorial we will get the files directly from the demo.
For that run the following command (should be adapted for Windows but you will get the sense):

.. prompt:: bash

   cd /tmp
   git clone git@github.com:camptocamp/demo_geomapfish.git
   cd -
   cp --recursive /tmp/demo_geomapfish/custom /tmp/demo_geomapfish/haproxy .

Add in ``.prettierignore`` the following line:

.. code::

   custom/Pipfile.lock

Apply the following diff in the ``setup.cfg``:

.. code:: diff

   - known_first_party=c2cgeoportal_commons,c2cgeoportal_geoportal,c2cgeoportal_admin,geomapfish_geoportal
   + known_third_party=webtest
   + known_first_party=c2cgeoportal_commons,c2cgeoportal_geoportal,c2cgeoportal_admin,geomapfish_geoportal,custom

Add the following service in the ``docker-compose.yaml``:

.. code:: yaml

  custom:
    image: ${DOCKER_BASE}-custom:${DOCKER_TAG}
    build:
      context: custom
      args:
        GIT_HASH: ${GIT_HASH}
    environment:
      - GUNICORN_CMD_ARGS=${GUNICORN_PARAMS}
      - VISIBLE_WEB_HOST

Add the following service in the ``docker-compose.override.sample.yaml``:

.. code:: yaml

  custom:
    command:
      - /usr/local/bin/gunicorn
      - --reload
      - --paste
      - development.ini
    volumes:
      - ./custom/custom:/app/custom

.. note::

   If you needs the user credentials, you can do:

   .. code:: python

      requests.get(
          "http://geoportal:8080/loginuser",
          headers={"Cookie": request.headers.get("Cookie"), "Referer": request.referrer},
      ).json()

Custom JavaScript file
----------------------

In this example we will add a button in the tools bar, that open a new tool panel, that can be used to send a feedback.

The tool button should be an instance of
`gmfapi.elements.ToolButtonElement<https://camptocamp.github.io/ngeo/|main_branch|/apidoc/classes/srcapi_elements_ToolButtonElement.default.html>`_.

In this example we will directly use
`gmf-tool-button<https://camptocamp.github.io/ngeo/|main_branch|/apidoc/classes/srcapi_elements_ToolButtonElement.ToolButtonDefault.html>`_.

Then we will include the following HTML in the canvas element, in ``geoportal/interfaces/desktop.html.mako``:

```html
<gmf-tool-button slot="tool-button" iconClasses="fas fa-file-signature" panelName="feedback"></gmf-tool-button>
```

The panel will be included with the following HTML:

```html
<proj-feedback slot="tool-panel-feedback"></proj-feedback>
```

And panel should be an instance of:
`gmfapi.elements.ToolPanelElement<https://camptocamp.github.io/ngeo/|main_branch|/apidoc/classes/srcapi_elements_ToolPanelElement.default.html>`_.


In this tutorial we will create a new WebComponent based on `Lit <https://lit.dev/>`_,
and build by `Vite <https://vitejs.dev/>`_. We will directly get the component and the build environment
from the demo:

.. prompt:: bash

   cd /tmp
   git clone git@github.com:camptocamp/demo_geomapfish.git
   cd -
   cp --recursive /tmp/demo_geomapfish/webcomponents \
      /tmp/demo_geomapfish/package.json \
      /tmp/demo_geomapfish/package-lock.json \
      /tmp/demo_geomapfish/tsconfig.json \
      /tmp/demo_geomapfish/vite.config.ts .

Add the following lines in the ``.dockerignore``:

.. code::

   !webcomponents/
   !package.json
   !package-lock.json
   !tsconfig.json
   !vite.config.ts

Add the following lines in the ``.gitignore``:

.. code::

   /node_modules

Add the following lines at the end of ``Dockerfile``:

.. code::

   ###############################################################################

   FROM node:16-slim AS custom-build

   WORKDIR /app
   COPY package.json ./

   RUN npm install

   COPY tsconfig.json vite.config.ts ./
   COPY webcomponents/ ./webcomponents/
   RUN npm run build

   ###############################################################################

   FROM gmf_config AS config
   COPY --from=custom-build /app/dist/ /etc/geomapfish/static/custom/

Apply the following diff in the ``geoportal/vars.yaml``:

.. code:: diff

   +
   +         # For dev, the corresponding values in static should also be commented.
   +         # gmfCustomJavascriptUrl:
   +         #   - https://localhost:3001/@vite/client
   +         #   - https://localhost:3001/webcomponents/index.ts
   +
   +         sitnFeedbackPath: custom/feedback
   +
   +       static:
   +         # Those tow lines should be commented in dev mode.
   +         gmfCustomJavascriptUrl:
   +           name: '/etc/geomapfish/static/custom/custom.es.js'
   +         gmfCustomStylesheetUrl:
   +           name: /etc/geomapfish/static/css/desktop_alt.css
   +
   +       routes:
   +         gmfBase:
   +           name: base

   -   content_security_policy_main_script_src_extra: "'unsafe-eval'"
   +   content_security_policy_main_script_src_extra: "'unsafe-eval' http://localhost:3001"

Working with Custom JavaScript and service
------------------------------------------

Build and run as usual:

.. prompt:: bash

    ./build <params>
    docker-compose down
    docker-compose up -d

To have a development environment, with auto-reload mode you should apply the following diff in the
``geoportal/vars.yaml`` (don't commit them):

.. code:: diff

              # For dev, the corresponding values in static should also be removed.
   -          # gmfCustomJavascriptUrl:
   -          #   - https://localhost:3001/@vite/client
   -          #   - https://localhost:3001/webcomponents/index.ts
   +          gmfCustomJavascriptUrl:
   +            - https://localhost:3001/@vite/client
   +            - https://localhost:3001/webcomponents/index.ts


              # Those tow lines should be commented in dev mode.
   -          gmfCustomJavascriptUrl:
   -            name: '/etc/geomapfish/static/custom/custom.es.js'
   +          # gmfCustomJavascriptUrl:
   +          #   name: '/etc/geomapfish/static/custom/custom.es.js'

Rename the ``docker-compose.override.sample.yaml`` file to ``docker-compose.override.yaml``.

Build and run as usual:

.. prompt:: bash

    ./build <params>
    docker-compose down
    docker-compose up -d

The download and start the Vite dev server:

.. prompt:: bash

   npm install
   npm run dev

Extend the geoportal image
--------------------------

Will be filled later.
