import React, {useState} from 'react';
import {Image} from 'react-native';
import {
  Button,
  FormControl,
  Input,
  ScrollView,
  useToast,
  VStack,
  Box,
} from 'native-base';
import {validarCorreoElectronico} from '../../utils/funciones';
import {consultarApi} from '../../utils/api';
import Contenedor from 'common/Contenedor';
import {useNavigation} from '@react-navigation/native';
import {RespuestaUsuarioRecuperarClave} from 'interface/usuario';

function OlvidoContrasena() {
  const toast = useToast();
  const [usuario, setUsuario] = useState('');
  const navigation = useNavigation();

  const recuperarContrasena = async () => {
    if (validarCorreoElectronico(usuario)) {
      const respuestaApiUsuarioRecuperarClave: RespuestaUsuarioRecuperarClave =
        await consultarApi('api/usuario/recuperarclave', {usuario});
      if (respuestaApiUsuarioRecuperarClave.error === false) {
        navigation.goBack();
        toast.show({
          title: 'Correcto',
          description:
            'Se ha enviado un correo electrónico con a información de recuperación de contraseña',
        });
      } else {
        toast.show({
          title: 'Algo ha salido mal',
          description: respuestaApiUsuarioRecuperarClave.errorMensaje,
        });
      }
    } else {
      toast.show({
        title: 'Algo ha salido mal',
        description: 'El correo válido',
      });
    }
  };

  const habilitarBtnGuardar = usuario === '';

  return (
    <Contenedor>
      <VStack space={2}>
        <Box mt="5" alignItems="center" justifyContent="center">
          <Image
            style={{width: 128, height: 128}}
            source={require('../../assets/img/logo-fondo-blanco.png')}
          />
        </Box>
        <ScrollView>
          <FormControl isRequired={true}>
            <FormControl.Label
              _text={{
                color: 'coolGray.800',
                fontSize: 'md',
                fontWeight: 500,
              }}>
              Correo
            </FormControl.Label>
            <Input
              keyboardType={'email-address'}
              onChangeText={valor => setUsuario(valor)}
            />
          </FormControl>
        </ScrollView>
      </VStack>
      <Button
        mt="2"
        isDisabled={habilitarBtnGuardar}
        onPress={() => recuperarContrasena()}>
        Guardar
      </Button>
    </Contenedor>
  );
}

export default OlvidoContrasena;
