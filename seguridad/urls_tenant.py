"""
Rutas de `seguridad` que se sirven DENTRO del schema de cada contenedor.

Hoy no hay ninguna: todo lo de `seguridad` (login, usuarios, membresías y sus
grupos) vive en el schema público, en `seguridad/urls.py`. Los permisos de un
miembro se leen y editan ahí (`usuario-cliente/<id>/grupo/`), sin `X-Tenant`.

Se sigue incluyendo desde `torioapp/urls_tenant.py` para que lo que haga falta
servir con el tenant ya resuelto tenga dónde ir.
"""

urlpatterns = []
