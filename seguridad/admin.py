from django.contrib import admin

from seguridad.models import SegAcceso


@admin.register(SegAcceso)
class SegAccesoAdmin(admin.ModelAdmin):
    """
    Bitácora de ingresos, de solo lectura.

    Las tres acciones de escritura van en False a propósito: un registro de auditoría
    que se puede editar o borrar desde el admin deja de servir como registro de
    auditoría. Se consulta acá y se corrige, si hiciera falta, en la base.
    """

    list_display = ['fecha', 'email', 'resultado', 'ip', 'metodo_mfa',
                    'dispositivo_recordado', 'codigo_respaldo']
    list_filter = ['resultado', 'metodo_mfa', 'dispositivo_recordado', 'codigo_respaldo', 'fecha']
    search_fields = ['email', 'ip']
    date_hierarchy = 'fecha'
    list_select_related = ['usuario']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
