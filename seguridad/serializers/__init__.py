from .autenticacion import SegLoginSerializer
from .grupo import SegGrupoDetalleSerializer, SegGrupoSerializer
from .permiso import SegPermisoSerializer
from .rol import SegRolSerializer
from .usuario import SegUsuarioActualizarSerializer, SegUsuarioMeSerializer, SegUsuarioSeleccionarSerializer, SegUsuarioSerializer
from .usuario_cliente import SegUsuarioClienteSerializer
from .usuario_cliente_permiso import (
    SegGrupoUsuarioSerializer,
    SegPermisoUsuarioSerializer,
    SegUsuarioClientePermisoSerializer,
)
