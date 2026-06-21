# Generador de Imágenes de Producto

Genera variaciones de fotografía de producto usando **Gemini 2.5 Flash** de Google AI Studio.
- **Free tier**: 10 RPM, 500 RPD, sin tarjeta de crédito
- **Costo prueba de 10 imágenes**: $0
- **Para escalar a 150 imágenes**: activa facturación → ~$1.87 USD total

---

## 1. Obtener API key gratis (sin tarjeta)

1. Ve a **https://aistudio.google.com/apikey**
2. Inicia sesión con cualquier cuenta Google
3. Clic en **"Create API key"** → selecciona o crea un proyecto
4. Copia la key (empieza con `AIza...`)

No se requiere tarjeta de crédito ni datos de pago para el free tier.

---

## 2. Instalar dependencias

Requiere **Python 3.9 o superior**.

```bash
# (Recomendado) Crear entorno virtual primero
python -m venv venv

# Activar en Mac/Linux:
source venv/bin/activate

# Activar en Windows:
venv\Scripts\activate

# Instalar
pip install -r requirements.txt
```

---

## 3. Configurar el archivo .env

```bash
# Mac/Linux
cp .env.example .env

# Windows
copy .env.example .env
```

Abre `.env` con cualquier editor y configura:

```env
GEMINI_API_KEY=AIzaXXXXXXXXXXXXXXXXXXXXXXXXXXX
PRODUCT_DESCRIPTION=Termo de acero inoxidable 500ml negro mate con tapa plateada y logo circular blanco
```

**Tip para PRODUCT_DESCRIPTION**: incluye color exacto, material, acabado, logo y
cualquier detalle visual que no quieras que el modelo cambie.

---

## 4. Correr el script

```bash
python main.py
```

Salida esperada:

```
Generador de Imágenes — Free Tier Google AI Studio
  Imágenes    : 10
  Modelo      : gemini-2.5-flash
  Concurrencia: 5  |  Rate limit: 10 RPM
  Tiempo est. : ~1.0 min
  Output      : /ruta/al/proyecto/output

Generando: 100%|████████████| 10/10 [01:12<00:00,  7.2s/img]

──────────────────────────────────────────
  Generadas  : 10
  Omitidas   : 0  (ya existían, no se cobran)
  Errores    : 0
──────────────────────────────────────────
```

Las imágenes quedan en `output/` con nombres como:
```
producto_001_fondo-blanco-estudio_frontal.jpg
producto_002_fondo-negro_45-grados.jpg
...
producto_010_lifestyle-exterior_tres-cuartos.jpg
```

**Si el script se interrumpe**, vuélvelo a correr — omite automáticamente las
imágenes ya generadas y continúa desde donde se quedó.

---

## 5. Personalizar las variaciones

Edita `variaciones.csv`. Tiene 3 columnas:

| fondo | angulo | iluminacion |
|-------|--------|-------------|
| fondo blanco estudio | frontal | luz suave difusa |
| lifestyle cocina | 45 grados | luz natural |

Puedes usar cualquier descripción en texto libre. Mientras más descriptivo,
mejor resultado. Ejemplos de valores:

- **Fondos**: `fondo blanco estudio`, `fondo negro`, `textura madera oscura`,
  `lifestyle playa`, `gradiente azul pastel`, `escena navideña`
- **Ángulos**: `frontal`, `45 grados`, `lateral derecho`, `cenital (top view)`,
  `perspectiva baja`, `tres cuartos`
- **Iluminación**: `luz suave difusa`, `luz dramática lateral`, `contraluz`,
  `luz natural de ventana`, `luz de estudio con softbox`

---

## 6. Interpretar errors.log

El archivo `errors.log` se crea automáticamente cuando hay fallas:

```
2024-01-15 14:23:01 | [producto_003_...jpg] HTTP 429: quota exceeded
2024-01-15 14:25:33 | [producto_007_...jpg] La respuesta no contiene imagen
```

### Errores comunes

| Error | Causa | Solución |
|-------|-------|----------|
| `HTTP 429` | Superaste 10 RPM o 500 RPD | El script espera 60s y reintenta solo |
| `HTTP 403` | API key inválida | Verifica la key en aistudio.google.com |
| `Sin imagen en respuesta` | El modelo generó solo texto | Vuelve a correr; puede ser temporal |
| `SSL certificate error` | Python sin certificados (Mac) | `pip install certifi` |
| `ModuleNotFoundError` | Dependencias no instaladas | `pip install -r requirements.txt` |

Si el 429 persiste (superaste los 500 RPD del día), espera al día siguiente.

---

## 7. Escalar a 150 imágenes

1. **Activa facturación** en Google Cloud Console (tarda ~5 min):
   - Ve a https://console.cloud.google.com/billing
   - Vincula una tarjeta al proyecto de tu API key

2. **Agrega filas al CSV** — el script procesa todas las filas que encuentre.
   Puedes tener 150, 300 o más.

3. **Ajusta la concurrencia** en `.env`:
   ```env
   MAX_CONCURRENT=10
   ```

4. Costo estimado: 150 imágenes × $0.0125 = **$1.87 USD**
