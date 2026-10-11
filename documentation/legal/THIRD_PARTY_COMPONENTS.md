# Inventario formal de componentes de terceros y licencias

**Producto:** GNET  
**Versión:** 1.0-rc1  
**Fecha de corte:** 3 de septiembre de 2026  
**Base:** `requirements-runtime-lock.txt`, `requirements-development-lock.txt`, `install.ps1` y `EL_files/build_hardened.cmd`

## 1. Alcance

Este documento identifica los componentes de terceros conocidos que requiere la Versión Entregada de GNET. No transfiere propiedad sobre ellos ni sustituye sus textos de licencia. Ante cualquier diferencia, prevalece la licencia del titular.

- **Incluido:** el archivo forma parte del paquete de GNET.
- **Descargado:** no forma parte del paquete; el instalador lo obtiene de su distribuidor.
- **Externo:** el Cliente debe obtenerlo, instalarlo y licenciarlo directamente.

Los paquetes Python no se redistribuyen dentro del paquete fuente. `install.ps1` los descarga desde PyPI conforme a las versiones bloqueadas. Las ruedas binarias pueden contener bibliotecas y avisos adicionales; los archivos `LICENSE`, `NOTICE` y metadatos de cada distribución instalada se incorporan a este inventario por referencia.

## 2. Componentes incluidos

| Componente | Versión | Modalidad | Licencia/aplicación | Observaciones |
|---|---:|---|---|---|
| Código fuente propio de GNET | Versión Entregada identificada por commit, tag y SHA-256 | Incluido | Contrato de licencia de GNET | No es un componente de terceros. |
| `BarBridge.dll`, `TickBridge.dll`, `SignalBridge.dll`, `StrategyBridge.dll` | Binarios x86 de la Versión Entregada | Incluido | Contrato de GNET; dependencias del sistema bajo términos de Microsoft | Compilados del código incluido; usan Winsock (`ws2_32`) y StrategyBridge también OLE (`ole32`). |
| Configuración de entrenamiento MA2Cross_Zona | Identificada por el manifiesto SHA-256 | Incluido | Contrato de GNET_Zona | Incluye código, características canónicas, arquitectura, hiperparámetros, umbrales y procedimientos. El modelo, scaler y demás artefactos se generan localmente con datos licenciados por el Cliente. |

No se incluyen los pesos, escaladores, datos históricos, datos procesados ni demás artefactos del modelo de referencia del Proveedor. Los pesos, parámetros ajustados, escaladores, métricas, reportes y demás artefactos producidos mediante el entrenamiento local de MA2Cross_Zona pertenecen al Cliente, con sujeción al contrato de GNET_Zona y a los derechos aplicables sobre los datos y componentes de terceros.

No se han identificado bibliotecas de terceros copiadas directamente al árbol fuente de GNET.

## 3. Infraestructura descargada o externa

| Componente | Versión fijada/soportada | Modalidad | Licencia o términos | Obligaciones y límites relevantes | Fuente oficial |
|---|---:|---|---|---|---|
| CPython | 3.12.7, Windows x64 | Externo | Python Software Foundation License Version 2 y avisos incorporados | Conservar avisos si se redistribuye Python. GNET no redistribuye el intérprete. | [Python 3.12: Copyright and License](https://docs.python.org/3.12/copyright.html) |
| Docker Desktop | Versión compatible; registrar versión probada en Anexo G | Externo | Docker Subscription Service Agreement | El Cliente acepta los términos y verifica si requiere suscripción pagada. | [Docker Desktop license agreement](https://docs.docker.com/subscription/desktop-license/) |
| Imagen oficial Redis Alpine | `redis:7.4.2-alpine` | Descargado por `install.ps1` | Redis Community Edition 7.4: elección RSALv2 o SSPLv1; uso previsto documentado bajo RSALv2. La imagen incluye Alpine y paquetes con avisos propios. | Mantener avisos. Bajo RSALv2 no ofrecer Redis o una versión modificada como servicio ni distribuirlo haciendo su funcionalidad disponible a terceros. En GNET es infraestructura interna y no se incluye en el ZIP. Revisar jurídicamente cualquier servicio que exponga Redis. | [Licencias Redis](https://redis.io/legal/licenses/), [RSALv2](https://redis.io/legal/rsalv2-agreement/), [imagen oficial](https://hub.docker.com/_/redis) |
| TradeStation Desktop | Versión compatible; registrar versión probada en Anexo G | Externo | Términos propietarios de TradeStation | Requiere cuenta, licencia y permisos de datos propios. GNET no suministra TradeStation ni datos CME. | [TradeStation legal](https://www.tradestation.com/legal/) |
| Windows | Versión compatible; registrar versión probada en Anexo G | Externo | Microsoft Software License Terms | El Cliente suministra y licencia el sistema operativo. | [Microsoft License Terms](https://www.microsoft.com/en-us/useterms) |
| Visual Studio / MSVC Build Tools y Windows SDK | Sólo para recompilar DLL | Externo | Términos de Microsoft y licencias aplicables | No son necesarios para ejecutar las DLL entregadas. | [Visual Studio licensing](https://visualstudio.microsoft.com/license-terms/) |
| Windows Terminal | Opcional; usado por `launch_grid.ps1` | Externo | MIT para el proyecto; la distribución de Microsoft queda sujeta además a sus términos | GNET no lo redistribuye. | [Repositorio/licencia](https://github.com/microsoft/terminal) |

## 4. Dependencias Python de ejecución

Todas son **descargadas por pip** y no están incorporadas al paquete fuente.

| Paquete | Versión | Licencia principal declarada | Uso | Fuente oficial |
|---|---:|---|---|---|
| redis (redis-py) | 7.4.0 | MIT | Cliente Redis | [PyPI](https://pypi.org/project/redis/7.4.0/) |
| numpy | 1.26.4 | BSD-3-Clause | Cálculo numérico | [PyPI](https://pypi.org/project/numpy/1.26.4/) |
| scipy | 1.13.1 | BSD-3-Clause y avisos incorporados | Cálculo científico | [PyPI](https://pypi.org/project/scipy/1.13.1/) |
| scikit-learn | 1.8.0 | BSD-3-Clause | Escalado/utilidades ML | [PyPI](https://pypi.org/project/scikit-learn/1.8.0/) |
| joblib | 1.4.2 | BSD-3-Clause | Serialización/utilidades | [PyPI](https://pypi.org/project/joblib/1.4.2/) |
| threadpoolctl | 3.5.0 | BSD-3-Clause | Control de pools nativos | [PyPI](https://pypi.org/project/threadpoolctl/3.5.0/) |
| torch | 2.12.0 | BSD-3-Clause principal; binario con avisos adicionales | Inferencia MLP | [PyPI](https://pypi.org/project/torch/2.12.0/), [licencia upstream](https://github.com/pytorch/pytorch/blob/main/LICENSE) |
| filelock | 3.13.1 | Unlicense | Dependencia de PyTorch | [PyPI](https://pypi.org/project/filelock/3.13.1/) |
| fsspec | 2024.6.1 | BSD-3-Clause | Dependencia de PyTorch | [PyPI](https://pypi.org/project/fsspec/2024.6.1/) |
| Jinja2 | 3.1.4 | BSD-3-Clause | Dependencia de PyTorch | [PyPI](https://pypi.org/project/Jinja2/3.1.4/) |
| MarkupSafe | 2.1.3 | BSD-3-Clause | Dependencia de Jinja2 | [PyPI](https://pypi.org/project/MarkupSafe/2.1.3/) |
| mpmath | 1.3.0 | BSD-3-Clause | Dependencia matemática | [PyPI](https://pypi.org/project/mpmath/1.3.0/) |
| networkx | 3.3 | BSD-3-Clause | Dependencia de PyTorch | [PyPI](https://pypi.org/project/networkx/3.3/) |
| sympy | 1.14.0 | BSD-3-Clause | Dependencia matemática | [PyPI](https://pypi.org/project/sympy/1.14.0/) |
| typing_extensions | 4.15.0 | PSF-2.0 | Compatibilidad de tipos | [PyPI](https://pypi.org/project/typing-extensions/4.15.0/) |

## 5. Dependencias de desarrollo, pruebas y entrenamiento

Se instalan de forma predeterminada con `install.ps1`. La opción `-RuntimeOnly`
las omite cuando se desea instalar únicamente el entorno de ejecución live.

| Paquete | Versión | Licencia principal declarada | Uso | Fuente oficial |
|---|---:|---|---|---|
| pytest | 7.4.4 | MIT | Pruebas | [PyPI](https://pypi.org/project/pytest/7.4.4/) |
| colorama | 0.4.6 | BSD-3-Clause | Terminal | [PyPI](https://pypi.org/project/colorama/0.4.6/) |
| iniconfig | 1.1.1 | MIT | Dependencia de pytest | [PyPI](https://pypi.org/project/iniconfig/1.1.1/) |
| packaging | 24.1 | Apache-2.0 o BSD-2-Clause | Empaquetado | [PyPI](https://pypi.org/project/packaging/24.1/) |
| pluggy | 1.0.0 | MIT | Plugins de pytest | [PyPI](https://pypi.org/project/pluggy/1.0.0/) |
| pandas | 2.3.2 | BSD-3-Clause | Preparación/análisis | [PyPI](https://pypi.org/project/pandas/2.3.2/) |
| pyarrow | 16.1.0 | Apache-2.0 | Parquet | [PyPI](https://pypi.org/project/pyarrow/16.1.0/) |
| matplotlib | 3.9.4 | Licencia Matplotlib basada en PSF; compatible con BSD | Gráficos | [PyPI](https://pypi.org/project/matplotlib/3.9.4/), [licencia](https://matplotlib.org/stable/project/license.html) |
| python-dotenv | 0.21.0 | BSD-3-Clause | Variables de entorno | [PyPI](https://pypi.org/project/python-dotenv/0.21.0/) |
| tqdm | 4.66.5 | MPL-2.0 y MIT | Progreso | [PyPI](https://pypi.org/project/tqdm/4.66.5/) |
| xgboost | 3.3.0 | Apache-2.0 | Investigación/modelos | [PyPI](https://pypi.org/project/xgboost/3.3.0/) |
| wandb | 0.29.0 | MIT | Registro opcional de experimentos | [PyPI](https://pypi.org/project/wandb/0.29.0/) |

## 6. Referencia metodológica que no constituye dependencia

Parte de la metodología estadística y de validación de GNET se inspira en conceptos publicados
por Marcos López de Prado, incluyendo meta-labeling, purging, embargo y combinatorial purged
cross-validation. La referencia bibliográfica principal es:

> Marcos López de Prado, *Advances in Financial Machine Learning*, Wiley, 2018.

GNET contiene una implementación propia de esas ideas. El libro, sus textos y cualquier software
del autor no se incluyen, descargan ni transfieren con GNET. La referencia no implica autoría,
afiliación, patrocinio o aprobación del producto. Por tanto, se documenta como referencia
académica y no como componente de software de terceros.

## 7. Obligaciones operativas

1. No eliminar archivos de licencia, copyright o `NOTICE` de las dependencias.
2. No presentar componentes de terceros como propiedad del Proveedor o Cliente.
3. No redistribuir instaladores, imágenes, ruedas Python o datos de mercado sin revisar antes sus términos.
4. Si cambia una versión bloqueada, regenerar este inventario antes de distribuir la nueva versión.
5. En servicios comerciales basados en GNET, mantener Redis como infraestructura interna no expuesta; cualquier otro uso exige revisión específica de RSALv2/SSPLv1.
6. El Cliente responde por licencias de TradeStation, CME/datos, Windows, Docker Desktop y demás productos externos.
7. Conservar con la Versión Entregada este inventario, los requisitos bloqueados, el manifiesto SHA-256 y los avisos instalados por pip.

## 8. Reservas

- Datos históricos, credenciales, cuentas y contenido de Redis no forman parte de la entrega.
- Una rueda binaria o imagen puede incorporar subcomponentes regidos por avisos adicionales.
- Este inventario es técnico-contractual, no una opinión jurídica independiente. Debe revisarlo un abogado competente en Guatemala antes de firma.

## 9. Aceptación

**Proveedor:** ____________________  **Fecha:** ____________________

**Cliente:** ______________________  **Fecha:** ____________________
