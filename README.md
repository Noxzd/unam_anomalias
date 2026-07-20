Análisis de resultados de admisión a la UNAM (2023–2026)

Este proyecto explora los resultados públicos de los concursos de ingreso a licenciatura de la UNAM entre 2023 y 2026. El objetivo es comparar la forma de las distribuciones de aciertos, los mínimos de ingreso y la proporción de aspirantes seleccionados para detectar cambios que merezcan estudiarse con mayor profundidad.

> **Estado del proyecto:** análisis exploratorio en desarrollo. Los patrones encontrados son descriptivos y no constituyen evidencia de fraude, manipulación ni una relación causal.

## Pregunta principal

Entre 2023 y 2025 los puntajes muestran distribuciones relativamente parecidas. En 2026 aparece una forma distinta, con una mayor concentración de resultados en zonas altas. Este repositorio intenta responder:

- ¿El cambio de 2026 es general o se concentra en ciertas carreras y planteles?
- ¿Cambió únicamente la escala de puntajes o también la selección?
- ¿Los aciertos mínimos aumentaron junto con los resultados?
- ¿Qué tan grande es la diferencia, más allá de que una prueba produzca un valor *p* pequeño?
- ¿La aparente bimodalidad se describe mejor mediante una o varias componentes estadísticas?

## Datos

Los datos fueron obtenidos de las páginas públicas de resultados de la **Dirección General de Administración Escolar de la UNAM (DGAE–UNAM)**.

Los archivos consolidados utilizados por el notebook contienen:

| Modalidad | Periodo | Registros |
|---|---:|---:|
| Escolarizado | 2023–2026 | 682,504 |
| SUAyED | 2023–2026 | 56,091 |
| **Total** | **2023–2026** | **738,595** |

Cada registro de aspirante puede incluir:

| Variable | Descripción |
|---|---|
| `year` | Año del concurso |
| `modalidad` | Escolarizado o SUAyED |
| `codigo_carrera` | Código publicado para la carrera |
| `carrera` | Nombre de la carrera |
| `plantel` | Facultad, escuela o sede |
| `folio` | Identificador publicado en la fuente; se elimina del análisis actual |
| `aciertos` | Número de respuestas correctas |
| `acreditado` | Estado publicado por la DGAE |
| `detalles` | Mensajes adicionales, cuando existen |

Los archivos `resumen_*.csv` agregan información de cada combinación carrera–plantel: oferta, aspirantes, personas que presentaron examen, aciertos mínimos y seleccionados.

## Estructura del repositorio

```text
unam_anomalias/
├── analisis/
│   ├── notebook.ipynb
│   ├── candidatos_escolarizado_2023_2026.csv
│   └── candidatos_suayed_2023_2026.csv
└── datos_scrapper/
    ├── scrapper.py
    ├── run_scraper.cmd
    ├── run_scraper.ps1
    ├── unam_data-2023-2025/
    └── datos_scrapper-2026/unam_data/
```

- `scrapper.py`: descubre las páginas de cada carrera–plantel, extrae sus datos y guarda los resultados.
- `run_scraper.cmd` y `run_scraper.ps1`: accesos directos para ejecutar el scraper en Windows.
- `candidatos_*.csv`: resultados individuales asociados al folio público mostrado por la fuente.
- `resumen_*.csv`: estadísticas publicadas por carrera y plantel.
- `_done_*.txt`: checkpoints que permiten reanudar el scraping sin repetir páginas terminadas.
- `notebook.ipynb`: limpieza, visualización, pruebas estadísticas y modelos exploratorios.

## Preparación del entorno

Se recomienda crear un entorno virtual e instalar las dependencias principales:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pandas numpy scipy matplotlib seaborn missingno scikit-learn jupyter curl-cffi
```

El notebook también importa `xgboost` y `optuna` para una etapa de modelado todavía no terminada. Si se desean ejecutar esas celdas:

```powershell
python -m pip install xgboost optuna
```

Los lanzadores incluidos contienen rutas locales de Python y pueden necesitar ajustes en otra computadora. Como alternativa portable se puede llamar directamente a `scrapper.py` con el Python del entorno virtual.

## Uso del scraper

Antes de descargar un año completo, conviene validar una sola página:

```powershell
python .\datos_scrapper\scrapper.py --years 2026 --modalidades escolarizado --test
```

Ejecución completa de ambas modalidades:

```powershell
python .\datos_scrapper\scrapper.py `
  --years 2023 2024 2025 2026 `
  --modalidades escolarizado suayed `
  --out .\datos_scrapper\unam_data
```

El scraper incluye pausas aleatorias, reintentos con espera progresiva y checkpoints. No se recomienda ejecutarlo en paralelo ni reducir agresivamente las pausas: el sitio puede limitar temporalmente las solicitudes y debe evitarse una carga innecesaria sobre sus servidores.

La estructura del sitio y sus códigos de índice pueden cambiar. Por ello, el modo `--test` debe ejecutarse siempre antes de una descarga completa y los resultados deben verificarse contra la página original.

## Ejecución del análisis

El notebook utiliza rutas relativas, por lo que debe iniciarse desde `analisis`:

```powershell
cd .\analisis
jupyter notebook .\notebook.ipynb
```

En el análisis actual, el estado `acreditado` se recodifica de la siguiente forma:

| Valor | Interpretación |
|---:|---|
| `0` | No seleccionado o sin marca de acreditación |
| `1` | Seleccionado (`S`) |
| `2` | No presentado (`N`) |
| `3` | Cancelado (`C`) |

Además, los datos individuales se unen con los resúmenes para obtener `aciertos_minimos` y calcular `margen_sobre_minimo = aciertos - aciertos_minimos`.

## Metodología actual

El notebook avanza desde una vista general hacia comparaciones más específicas:

1. Revisión de tipos, valores faltantes y número de registros.
2. Distribuciones anuales mediante histogramas, KDE, boxplots y ECDF.
3. Comparación entre puntajes, estado de selección y aciertos mínimos.
4. Frecuencia de puntajes altos usando umbrales de 90, 100 y 110 aciertos.
5. Análisis del margen respecto al mínimo solicitado por carrera–plantel.
6. Comparaciones por carrera y por sede.
7. Kruskal–Wallis con epsilon cuadrada para la comparación conjunta de años.
8. Chi-cuadrada y V de Cramér para año frente a selección.
9. Mann–Whitney y delta de Cliff para comparar 2025 contra 2026 dentro de cada carrera.
10. Gaussian Mixture Models, seleccionando el número de componentes mediante BIC.

Con tamaños de muestra tan grandes, un valor *p* muy pequeño puede aparecer incluso ante diferencias poco importantes. Por eso la interpretación da prioridad al tamaño del efecto, las distribuciones, los intervalos y la consistencia del patrón entre carreras y planteles.

## Hallazgos preliminares

- El número anual de registros se mantiene relativamente estable, aunque 2026 contiene menos observaciones que algunos años anteriores.
- Las distribuciones de 2023, 2024 y 2025 son parecidas; la de 2026 presenta un desplazamiento visible y una forma más compleja.
- En 2026 aumenta la frecuencia de puntajes altos, especialmente al observar umbrales de 90, 100 y 110 aciertos.
- La proporción de seleccionados cambia mucho menos que los puntajes absolutos.
- Los aciertos mínimos también aumentan, de modo que una parte del desplazamiento se conserva al medir el margen respecto al corte, pero el contraste se reduce.
- El cambio aparece en varias carreras y planteles, no únicamente en una sede.
- Médico Cirujano, Derecho, Psicología, Arquitectura y Cirujano Dentista presentan movimientos claros, aunque con magnitudes diferentes.
- Carreras con menos registros, como Teatro y Actuación, Comunicación y Diseño Industrial, también muestran cambios; por tanto, el fenómeno no parece limitarse a las carreras más masivas.
- Los GMM describen mejor algunas distribuciones usando varias componentes, pero esas componentes son zonas estadísticas superpuestas: **no representan automáticamente tipos reales de aspirantes**.

Estos resultados justifican continuar investigando, pero no permiten determinar si el cambio proviene de la dificultad del examen, preparación de los aspirantes, modalidad de aplicación, composición de la población, reglas institucionales u otra variable no disponible.

## Limitaciones

- El estudio utiliza resultados observacionales y públicos; no incluye reactivos, dificultad por pregunta, condiciones de aplicación ni características individuales de los aspirantes.
- Los años no necesariamente representan poblaciones idénticas.
- Una KDE o un GMM pueden mostrar multimodalidad sin que existan grupos reales separados.
- La comparación de muchas carreras incrementa el riesgo de encontrar resultados significativos por azar; falta aplicar una corrección por comparaciones múltiples.
- Aún falta cuantificar incertidumbre mediante intervalos de confianza o bootstrap para varios tamaños de efecto.
- Las diferencias entre planteles, carreras, cupos y cortes pueden actuar como variables de confusión.
- El cambio de 2026 coincide temporalmente con cambios en el proceso de aplicación, pero una coincidencia temporal no demuestra causalidad.
- Los resultados dependen de que la extracción y el emparejamiento carrera–plantel sean correctos.

## Uso de inteligencia artificial y autoría

El scraper **no fue escrito originalmente por mí**. Lo solicité a una inteligencia artificial porque todavía no domino bien el web scraping. Después probé su funcionamiento y corregí varios problemas con ayuda de IA, entre ellos errores de dependencias, acceso al sitio, ejecución en Windows y escritura de los archivos CSV.

También utilicé IA para corregir algunas partes del notebook, depurar código, ordenar ideas y entender mejor ciertas pruebas estadísticas. Este repositorio forma parte de mi aprendizaje: las preguntas que decidí investigar, la exploración de los datos y la interpretación final siguen en revisión. La asistencia de IA no garantiza que el código o las conclusiones sean correctos, por lo que intento documentar las decisiones, contrastar los resultados y conservar las limitaciones visibles.

## Uso responsable

El propósito del proyecto es aprender análisis de datos y localizar patrones que puedan formularse como preguntas verificables. No pretende acusar a personas ni instituciones. Un resultado atípico es una señal para revisar datos, metodología y contexto; no es por sí solo una prueba de irregularidad.

Aunque los folios se publican en la fuente, no se utilizan en el análisis actual y se recomienda no emplearlos para intentar identificar aspirantes.

## Próximos pasos

- Validar automáticamente la integridad de cada archivo y el número de páginas descargadas.
- Añadir un archivo de dependencias reproducible.
- Aplicar intervalos de confianza por bootstrap a delta de Cliff y a diferencias de proporciones.
- Corregir valores *p* cuando se comparen muchas carreras.
- Separar con mayor cuidado carrera, plantel, área y modalidad.
- Construir un modelo base con 2023–2025 y evaluar si 2026 queda fuera de sus predicciones.
- Realizar análisis de sensibilidad para comprobar cuánto depende el resultado de los faltantes y cambios de composición.
- Incorporar fuentes oficiales sobre cualquier cambio en el proceso de aplicación antes de discutir posibles causas.

## Fuente

- Dirección General de Administración Escolar de la UNAM: <https://www.dgae.unam.mx/>

---

Este repositorio documenta un análisis en proceso. Si encuentras un error en los datos, el código o la interpretación, una revisión reproducible es bienvenida.
