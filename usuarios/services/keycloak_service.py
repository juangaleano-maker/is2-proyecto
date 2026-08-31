import logging
import uuid
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class KeycloakAdminError(Exception):
    """Excepción para errores ocurridos al interactuar con la Admin API de Keycloak."""
    pass


class KeycloakAdminService:
    """
    Servicio de integración con la Admin REST API de Keycloak.
    Permite la creación de usuarios, asignación de credenciales,
    disparo de emails de verificación y consulta de estado.
    """

    def __init__(self):
        self.server_url = getattr(settings, 'KEYCLOAK_SERVER_URL', 'http://localhost:8080').rstrip('/')
        self.realm = getattr(settings, 'KEYCLOAK_REALM', 'global-exchange')
        self.admin_client_id = getattr(settings, 'KEYCLOAK_ADMIN_CLIENT_ID', 'admin-cli')
        self.admin_client_secret = getattr(settings, 'KEYCLOAK_ADMIN_CLIENT_SECRET', '')
        self.admin_username = getattr(settings, 'KEYCLOAK_ADMIN_USERNAME', 'admin')
        self.admin_password = getattr(settings, 'KEYCLOAK_ADMIN_PASSWORD', 'admin')
        self.is_enabled = getattr(settings, 'KEYCLOAK_ENABLED', True)

    def get_admin_token(self):
        """
        Obtiene un token de acceso OAuth2 para interactuar con la Admin API.
        Intenta primero por autenticación de usuario admin (master realm) y luego por client_credentials.
        """
        if not self.is_enabled:
            return "simulated-token"

        token_url = f"{self.server_url}/realms/master/protocol/openid-connect/token"
        
        # Estrategia 1: Password grant con credenciales de admin en master realm
        data = {
            'client_id': self.admin_client_id,
            'grant_type': 'password',
            'username': self.admin_username,
            'password': self.admin_password,
        }
        if self.admin_client_secret:
            data['client_secret'] = self.admin_client_secret

        try:
            response = requests.post(token_url, data=data, timeout=5)
            if response.status_code == 200:
                return response.json().get('access_token')
            
            # Estrategia 2: Client credentials grant si el realm tiene client dedicado
            token_url_realm = f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/token"
            data_cc = {
                'client_id': self.admin_client_id,
                'grant_type': 'client_credentials',
            }
            if self.admin_client_secret:
                data_cc['client_secret'] = self.admin_client_secret
                response_cc = requests.post(token_url_realm, data=data_cc, timeout=5)
                if response_cc.status_code == 200:
                    return response_cc.json().get('access_token')
            
            logger.warning("No se pudo autenticar contra Keycloak Admin API: HTTP %s - %s", response.status_code, response.text)
            return None
        except requests.exceptions.RequestException as e:
            logger.warning("Error de conexión al conectar con Keycloak Admin API en %s: %s", self.server_url, e)
            return None

    def crear_usuario(self, username, email, first_name, last_name, password, required_actions=None):
        """
        Crea un nuevo usuario en el Realm de Keycloak mediante la Admin API.
        
        Retorna:
            dict: { 'success': bool, 'keycloak_id': str, 'message': str, 'simulated': bool }
        """
        if required_actions is None:
            required_actions = ['VERIFY_EMAIL']

        token = self.get_admin_token()

        # Si Keycloak está deshabilitado o no está disponible en este entorno, operar en modo fallback
        if not token or token == "simulated-token":
            simulated_id = f"mock-{uuid.uuid4()}"
            logger.info("Keycloak no disponible o en modo simulación. Usuario creado virtualmente: %s (ID: %s)", username, simulated_id)
            return {
                'success': True,
                'keycloak_id': simulated_id,
                'message': 'Usuario registrado en modo desarrollo / simulado.',
                'simulated': True
            }

        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }

        user_payload = {
            'username': username,
            'email': email,
            'firstName': first_name,
            'lastName': last_name,
            'enabled': True,
            'emailVerified': False,
            'requiredActions': required_actions,
            'credentials': [
                {
                    'type': 'password',
                    'value': password,
                    'temporary': False
                }
            ]
        }

        users_url = f"{self.server_url}/admin/realms/{self.realm}/users"

        try:
            response = requests.post(users_url, json=user_payload, headers=headers, timeout=5)

            if response.status_code == 201:
                # El ID viene en el header Location: .../users/{id}
                location = response.headers.get('Location', '')
                keycloak_id = location.rstrip('/').split('/')[-1] if location else None
                
                # Si no viene en el header Location, buscar el ID por username
                if not keycloak_id:
                    keycloak_id = self.obtener_id_por_username(username, token=token)

                logger.info("Usuario %s creado con éxito en Keycloak (ID: %s)", username, keycloak_id)
                return {
                    'success': True,
                    'keycloak_id': keycloak_id,
                    'message': 'Usuario registrado exitosamente en Keycloak.',
                    'simulated': False
                }
            elif response.status_code == 409:
                return {
                    'success': False,
                    'keycloak_id': None,
                    'message': 'El usuario o correo electrónico ya existe en Keycloak.',
                    'simulated': False
                }
            else:
                logger.error("Error al crear usuario en Keycloak: HTTP %s - %s", response.status_code, response.text)
                return {
                    'success': False,
                    'keycloak_id': None,
                    'message': f"Error en Keycloak ({response.status_code}): {response.text}",
                    'simulated': False
                }

        except requests.exceptions.RequestException as e:
            logger.error("Fallo de red al intentar crear usuario en Keycloak: %s", e)
            simulated_id = f"mock-{uuid.uuid4()}"
            return {
                'success': True,
                'keycloak_id': simulated_id,
                'message': 'Registro completado localmente (servidor Keycloak no alcanzable).',
                'simulated': True
            }

    def enviar_correo_verificacion(self, keycloak_id):
        """
        Solicita a Keycloak que envíe el correo de verificación al usuario.
        Endpoint: PUT /admin/realms/{realm}/users/{id}/send-verify-email
        """
        if not keycloak_id or keycloak_id.startswith('mock-'):
            return {'success': True, 'simulated': True, 'message': 'Simulado'}

        token = self.get_admin_token()
        if not token:
            return {'success': False, 'message': 'No se pudo obtener token de Keycloak.'}

        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }

        url = f"{self.server_url}/admin/realms/{self.realm}/users/{keycloak_id}/send-verify-email"

        try:
            response = requests.put(url, headers=headers, timeout=5)
            if response.status_code in (200, 204):
                logger.info("Correo de verificación enviado por Keycloak al usuario %s", keycloak_id)
                return {'success': True, 'message': 'Correo de verificación enviado por Keycloak.'}
            else:
                logger.warning("Error de Keycloak al enviar correo: %s - %s", response.status_code, response.text)
                return {'success': False, 'message': response.text}
        except requests.exceptions.RequestException as e:
            logger.warning("Error de conexión al enviar correo desde Keycloak: %s", e)
            return {'success': False, 'message': str(e)}

    def marcar_email_verificado(self, keycloak_id):
        """
        Actualiza el estado del usuario en Keycloak marcando emailVerified=True y eliminando VERIFY_EMAIL.
        """
        if not keycloak_id or keycloak_id.startswith('mock-'):
            return True

        token = self.get_admin_token()
        if not token:
            return False

        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }

        url = f"{self.server_url}/admin/realms/{self.realm}/users/{keycloak_id}"
        payload = {
            'emailVerified': True,
            'requiredActions': []
        }

        try:
            response = requests.put(url, json=payload, headers=headers, timeout=5)
            return response.status_code in (200, 204)
        except requests.exceptions.RequestException as e:
            logger.warning("Error al actualizar estado en Keycloak: %s", e)
            return False

    def obtener_usuario(self, keycloak_id):
        """
        Obtiene los datos de un usuario en Keycloak por su ID.
        """
        if not keycloak_id or keycloak_id.startswith('mock-'):
            return None

        token = self.get_admin_token()
        if not token or token == "simulated-token":
            return None

        headers = {'Authorization': f"Bearer {token}"}
        url = f"{self.server_url}/admin/realms/{self.realm}/users/{keycloak_id}"

        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning("Error al consultar usuario en Keycloak: %s", e)
        return None

    def obtener_id_por_username(self, username, token=None):
        """
        Busca el ID de Keycloak a partir del nombre de usuario.
        """
        if not token:
            token = self.get_admin_token()
        if not token or token == "simulated-token":
            return None

        headers = {'Authorization': f"Bearer {token}"}
        url = f"{self.server_url}/admin/realms/{self.realm}/users"
        params = {'username': username, 'exact': 'true'}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                users = response.json()
                if users and len(users) > 0:
                    return users[0].get('id')
        except requests.exceptions.RequestException:
            pass
        return None

