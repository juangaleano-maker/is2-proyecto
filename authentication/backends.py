from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class KeycloakOIDCBackend(OIDCAuthenticationBackend):
    """
    Backend de autenticación SSO contra Keycloak.
    Identifica/crea al usuario Django por email (username = email).

    No usamos django admin: is_staff/is_superuser quedan siempre en False,
    los permisos van por Groups + decoradores (ver IS2-29 / IS2-31).
    """

    def filter_users_by_claims(self, claims):
        email = claims.get('email')
        if not email:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(email__iexact=email)

    def create_user(self, claims):
        return self.UserModel.objects.create_user(
            username=claims.get('email'),
            email=claims.get('email'),
            first_name=claims.get('given_name', ''),
            last_name=claims.get('family_name', ''),
        )

    def update_user(self, user, claims):
        user.first_name = claims.get('given_name', user.first_name)
        user.last_name = claims.get('family_name', user.last_name)
        user.save()
        return user
