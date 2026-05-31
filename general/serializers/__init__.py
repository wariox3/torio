from .archivo import GenArchivoSerializer
from .asesor import GenAsesorSeleccionarSerializer
from .banco import GenBancoSeleccionarSerializer
from .ciudad import GenCiudadSeleccionarSerializer
from .contacto import GenContactoSerializer
from .contacto_exportar import GenContactoExportarSerializer
from .contacto_importar import GenContactoImportarSerializer
from .cuenta_banco_clase import GenCuentaBancoClaseSeleccionarSerializer
from .documento import (
    GenDocumentoCrearSerializer,
    GenDocumentoDetalleVistaSerializer,
    GenDocumentoSerializer,
)
from .documento_detalle import GenDocumentoDetalleSerializer
from .documento_exportar import GenDocumentoExportarSerializer
from .documento_importar import GenDocumentoImportarSerializer
from .identificacion import GenIdentificacionSeleccionarSerializer
from .item import GenItemSerializer
from .item_exportar import GenItemExportarSerializer
from .item_importar import GenItemImportarSerializer
from .log import GenLogSerializer
from .modelo import GenModeloSerializer
from .plazo_pago import GenPlazoPagoSeleccionarSerializer
from .precio import GenPrecioSeleccionarSerializer
from .responsabilidad import GenResponsabilidadSeleccionarSerializer
from .tipo_persona import GenTipoPersonaSeleccionarSerializer
