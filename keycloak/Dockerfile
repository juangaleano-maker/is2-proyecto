# keycloak/Dockerfile
FROM quay.io/keycloak/keycloak:26.0

# Copiar la exportación del realm al directorio de importación de Keycloak
COPY realm-export.json /opt/keycloak/data/import/realm-export.json

EXPOSE 8080

# Iniciar Keycloak en modo desarrollo importando el realm
ENTRYPOINT ["/opt/keycloak/bin/kc.sh", "start-dev", "--import-realm"]
