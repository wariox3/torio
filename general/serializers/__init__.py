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
from .identificacion import GenIdentificacionSeleccionarSerializer
from .log import GenLogSerializer
from .plazo_pago import GenPlazoPagoSeleccionarSerializer
from .precio import GenPrecioSeleccionarSerializer
from .responsabilidad import GenResponsabilidadSeleccionarSerializer
from .tipo_persona import GenTipoPersonaSeleccionarSerializer
