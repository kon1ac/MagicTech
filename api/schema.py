from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ApiTokenScheme(OpenApiAuthenticationExtension):
    target_class = 'api.auth.ApiTokenAuthentication'
    name = 'TokenAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey', 'in': 'header', 'name': 'Authorization',
            'description': 'Формат: `Token <ключ>`. Ключ выпускается в панели (Сервисные учётки) '
                           'или через POST /api/v1/mobile/auth/token/ для покупателя.',
        }
