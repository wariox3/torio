from django_tenants.models import DomainMixin


class CtnDominio(DomainMixin):
    class Meta:
        db_table = "ctn_dominio"
        verbose_name = 'Dominio'
        verbose_name_plural = 'Dominios'