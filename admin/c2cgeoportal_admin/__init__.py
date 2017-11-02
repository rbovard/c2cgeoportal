from pyramid.config import Configurator
from c2cwsgiutils.health_check import HealthCheck
import c2cgeoportal_admin.routes


def main(_, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings)
    config.include('c2cwsgiutils.pyramid.includeme')
    config.include('pyramid_jinja2')
    config.include('c2cgeoform')
    config.include('c2cgeoportal_commons')
    config.include(c2cgeoportal_admin.routes)
    config.scan()

    health_check = HealthCheck(config)
    health_check.add_url_check('http://{}/'.format(settings['healthcheck_host']))
    # health_check.add_alembic_check(models.DBSession, '/app/alembic.ini', 1)

    return config.make_wsgi_app()
