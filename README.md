# Canal de Isabel II para Home Assistant

Componente para integrar los datos de consumo de agua del Canal de Isabel II en Home Assistant.

## Características

-   Descarga el consumo de agua.
-   Crea sensores con el consumo reciente.
-   Importa el histórico de datos.

## Instalación

### HACS (Recomendado)

1.  Asegúrate de tener [HACS](https://hacs.xyz/) instalado.
2.  Ve a **HACS > Integraciones**.
3.  Haz clic en los tres puntos de arriba a la derecha y elige **Repositorios personalizados**.
4.  Pega la URL de este repositorio: `https://github.com/miguelangel-nubla/homeassistant_canal_isabel_II`
5.  En categoría selecciona **Integración**.
6.  Dale a **Añadir**.
7.  Busca **Canal de Isabel II** en la lista y dale a **Descargar**.
8.  Reinicia Home Assistant.

### Instalación Manual

1.  Descarga la carpeta `custom_components/canal_de_isabel_ii` de este repositorio.
2.  Cópiala en tu carpeta `config/custom_components/`.
3.  Reinicia Home Assistant.

## Configuración

1.  Ve a **Ajustes > Dispositivos y Servicios**.
2.  Dale a **Añadir integración**.
3.  Busca **Canal de Isabel II**.
4.  Te pedirá el `JSESSIONID`. Para sacarlo:
    1.  Entra en la [oficina virtual](https://oficinavirtual.canaldeisabelsegunda.es/) con tu navegador e inicia sesión.
    2.  Pulsa F12 para abrir la consola de desarrollador.
    3.  Ve a la pestaña **Aplicación** > **Cookies**.
    4.  Busca la que se llama `JSESSIONID` y copia el valor.

> [!NOTE]
> Dada la web actual del Canal de Isabel II y la interfaz que utiliza, no hay forma de automatizar el proceso y obtener la cookie de otra manera. Tampoco hay API conocida, si alguien conoce una alternativa mejor o es capaz de obtener una API oficial, que me lo haga saber.