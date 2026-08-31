import logging

from django.contrib.auth.models import Group
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from .decorators import ROLES_KEYCLOAK

logger = logging.getLogger(__name__)


class KeycloakOIDCBackend(OIDCAuthenticationBackend):
    """
    Backend de autenticación SSO contra Keycloak.
    Identifica/crea al usuario Django por email (username = email) y
    sincroniza los roles que el usuario tenga asignados en Keycloak
    (claim `realm_access.roles`) como Groups de Django.

    No usamos django admin: is_staff/is_superuser quedan siempre en False,
    los permisos van por Groups + @rol_requerido.
    """

    def filter_users_by_claims(self, claims):
        email = claims.get('email')
        if not email:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(email__iexact=email)

    def create_user(self, claims):
        user = self.UserModel.objects.create_user(
            username=claims.get('email'),
            email=claims.get('email'),
            first_name=claims.get('given_name', ''),
            last_name=claims.get('family_name', ''),
        )
        self._sync_roles(user, claims)
        return user

    def update_user(self, user, claims):
        user.first_name = claims.get('given_name', user.first_name)
        user.last_name = claims.get('family_name', user.last_name)
        user.save()
        self._sync_roles(user, claims)
        return user

    def _sync_roles(self, user, claims):
        """Refleja en Django los roles que el usuario tiene asignados en Keycloak."""
        roles_keycloak = claims.get('realm_access', {}).get('roles', [])
        roles_relevantes = [r for r in roles_keycloak if r in ROLES_KEYCLOAK]

        if not roles_relevantes:
            logger.warning('Usuario %s vino sin roles de negocio asignados', user.email)

        grupos = [Group.objects.get_or_create(name=r)[0] for r in roles_relevantes]
        user.groups.set(grupos)
