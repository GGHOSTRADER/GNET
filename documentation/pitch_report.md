# GNET — Infraestructura de Trading Algorítmico con Capa de IA
### El puente entre el swing trading estadístico y la ejecución intradiaria con ML

---

## El contexto: dónde está el gap

El trading cuantitativo profesional opera en dos mundos distintos:

- **Swing estadístico**: estrategias basadas en backtests, señales discretas (MA crosses, breakouts), bots estáticos configurados manualmente. Funciona, pero las reglas son fijas — el bot no aprende ni adapta umbrales en función del contexto de mercado.
- **Trading intradiario con ML**: modelos que generan probabilidades dinámicas en tiempo real, adaptadas a microestructura, liquidez, y condiciones del momento. No opera con reglas estáticas; opera con distribuciones de probabilidad.

**El problema**: pasar del segundo mundo requiere una infraestructura de datos en tiempo real que casi nadie tiene. Sin ella, entrenar un modelo es trivial; desplegarlo en producción es la barrera real.

**GNET resuelve esa barrera.**

---

## ¿Qué es GNET?

GNET es una infraestructura completa que captura datos de TradeStation en tiempo real, computa features de microestructura y perfil de volumen, y alimenta un modelo de ML que filtra señales de entrada con probabilidades dinámicas — todo en un pipeline continuo de baja latencia.

La propuesta no es "el modelo ML es mejor que un MA cruzado". Es: **las señales de indicadores técnicos fijos tienen una tasa de éxito promedio — un modelo de probabilidad dinámica puede aprender cuándo esas señales tienen alta o baja probabilidad de éxito en el contexto actual del mercado.**

![[trading_signal_pipeline 1.png]]
---

## Por qué el swing estadístico y el intradiario con ML son complementarios

| Dimensión | Bot estático (MA + reglas) | GNET + ML |
|---|---|---|
| Señales | Fijas — regla se cumple o no | Probabilísticas — contexto importa |
| Adaptabilidad | Sin adaptación al régimen actual | Features de microestructura capturan volatilidad, liquidez, flujo |
| Velocidad de ejecución | Manual o bot simple | Intradiario, baja latencia, ~30s por barra |
| Escala | Un bot por estrategia | Una pipeline, múltiples cabezas de modelo |
| Requiere infraestructura | No | Sí — esta es la barrera que GNET resuelve |

La visión no es reemplazar el swing estadístico. Es **extenderlo**: el bot sigue generando la señal de entrada; el modelo decide si el contexto actual hace esa señal de alta o baja probabilidad.

---

## Features: qué mide el modelo

### 13 Features de Microestructura (por barra de 30s)

| Feature | Descripción |
|---|---|
| parkinson_vol_{5,15,30} | Volatilidad High/Low — estimador Parkinson, más eficiente que close-to-close |
| ofi_{5,15,30} | Order Flow Imbalance — (sum(Up)−sum(Down)) / sum(Up+Down), bounded [−1,1] |
| volume_percentile | Ranking del volumen actual vs últimas 60 barras (0–1) |
| volume_momentum | Cambio porcentual de volumen vs 5 barras atrás |
| amihud_illiquidity | Media 30-bar de pct_change(close) / (close × volume) — impacto de precio por dólar operado |
| vwap_distance | (close − VWAP) / ATR(14) — posición relativa al precio justo ponderado |
| minutes_since_open | Minutos transcurridos desde 09:30 |
| is_first_last_30min | Flag 1 si está en primeros o últimos 30 min de sesión |
| day_of_week | Día de la semana (Lunes=0 … Viernes=4) |

### 8 Features de Volume Profile / POC (por barra, desde ticks)

| Feature | Descripción |
|---|---|
| poc_price | Point of Control — precio con mayor volumen en la sesión |
| poc_distance | Distancia en ticks entre precio actual y POC |
| poc_concentration | poc_volume / total_volume — qué tan concentrado está el perfil |
| va_width | Ancho del Value Area en ticks (70% del volumen) |
| va_position | Posición del precio dentro del Value Area (0=VAL, 1=VAH) |
| vol_above_poc_ratio | Fracción del volumen por encima del POC |
| profile_entropy | −Σp·log(p) del perfil — bajo=concentrado, alto=difuso |
| poc_migration | Drift del POC desde la barra anterior (en ticks) |

> Las 8 features de VP están disponibles en el stream `features_volume_profile` pero **no incluidas en el modelo actual**. La arquitectura ya soporta agregarlas.

---

## El modelo actual: un MLP como prueba de concepto

El modelo entrenado es una red neuronal feedforward pequeña, seleccionada para demostrar que el **pipeline** (no el modelo) es el activo.

**Arquitectura:**
- Input: 13 features escaladas (StandardScaler)
- 2 capas ocultas: 64 → 32 neuronas, BatchNorm + ReLU + Dropout(0.3)
- Output: 1 logit → BCEWithLogitsLoss con pos_weight para clases desbalanceadas
- Threshold: sigmoid(logit) ≥ 0.5 → señal de compra

**Meta-labeling:** Las señales las genera el bot MA2Cross existente. El modelo aprende a filtrar: label=1 si la señal del bot fue rentable, label=0 si fue pérdida. El modelo no genera señales nuevas — **filtra las existentes con contexto**.

---

## Entrenamiento y validación

- **Walk-forward cross-validation**: 5 folds, split temporal estricto
- **Purge**: 20 barras (~10 min) entre train y val para evitar data leakage
- **Embargo**: 60 barras (~30 min) adicionales post-purge
- **Test set**: 10% final congelado, nunca visto durante entrenamiento ni tuning
- **Scaler**: ajustado solo en train, aplicado a val/test (sin data snooping)

---

## Resultado en test set

| Métrica | Valor |
|---|---|
| Accuracy | 58.2% |
| F1 Score | 0.612 |
| AUC-ROC | 0.620 |
| Baseline (frecuencia de clase) | 50.6% |

### Traducción a dinero

La estrategia MA2CrossLE está configurada con una relación riesgo/recompensa simétrica de 1:1 — tanto el objetivo de ganancia como el stop loss están fijados en **1 handle (4 ticks)** en ES. Un handle equivale a 4 × $12.50 = **$50 por contrato**. Comisión de $1.50 por lado, $3.00 por operación completa. Slippage no incluido.

**Resultado por operación:**

| Resultado | Bruto | Comisión | Neto |
|---|---|---|---|
| Win | +$50.00 | −$3.00 | **+$47.00** |
| Loss | −$50.00 | −$3.00 | **−$53.00** |

La comisión introduce asimetría: un win neto es $47 pero una pérdida cuesta $53. El win rate de equilibrio no es 50% — es $53 / ($47 + $53) = **53.0%** solo para cubrir comisiones. La estrategia naive al 50.6% está estructuralmente por debajo del break-even.

**Valor esperado por operación:**

| Estrategia | Win Rate | Cálculo EV | EV por Operación |
|---|---|---|---|
| MA crossover sin filtro | 50.6% | 0.506 × $47 − 0.494 × $53 | **−$2.40** |
| MLP meta-model | 58.2% | 0.582 × $47 − 0.418 × $53 | **+$5.20** |

El MA crossover sin filtrar **pierde $2.40 por operación** después de comisiones. El meta-model lo convierte en **+$5.20 por operación** — un cambio de $7.60 por operación a partir de una mejora de 7.6 puntos porcentuales en el win rate. Con riesgo/recompensa simétrico y costos fijos de comisión, cada 1 pp de mejora en win rate por encima del break-even equivale a aproximadamente **$1.00 adicional de valor esperado por operación**.

**Escalado a volumen diario** (sin slippage):

| Señales/día | EV Diario | EV Anual (250 días) |
|---|---|---|
| 5 | +$26 | **+$6,500** |
| 10 | +$52 | **+$13,000** |

---

## Por qué no existe esto como producto comercial

| Capa                     | Por qué es difícil                                                                                   |
| ------------------------ | ---------------------------------------------------------------------------------------------------- |
| Datos en tiempo real     | Requiere acceso a feed de baja latencia (TradeStation, Bloomberg, etc.)                              |
| Infraestructura          | Redis + TCP + pipeline multi-proceso es ingeniería de sistemas, no solo ML                           |
| Meta-labeling            | Requiere estrategia base existente para etiquetar — no hay dataset público                           |
| Walk-forward CV correcto | La mayoría de los repos usan CV aleatorio — válido para NLP, inválido para trading                   |
| Deployment               | Cerrar el loop desde Python a la plataforma de ejecución (DLLs, TCP) es la parte que nadie documenta |
|                          |                                                                                                      |

Productos como QuantConnect o Zipline resuelven backtesting. **Nadie resuelve el deployment en tiempo real con pipeline de features propio.**

---

## Lo que se puede construir encima

- Agregar las 8 features de Volume Profile al modelo (ya disponibles en el stream)
- Cambiar la cabeza de modelo: XGBoost, LSTM, Transformer — el pipeline no cambia
- Multi-símbolo: replicar para ES, NQ, CL — misma infraestructura, distintos pesos
- Señales cortas (short): meta-labeling inverso — el pipeline ya captura los datos
- Dashboard de monitoreo en tiempo real de features y probabilidades

**El pipeline es el producto. El MLP es la prueba de concepto.**
