from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
import openai
import json

# Inicializa FastAPI
app = FastAPI()

# Configuración de la clave de la API de OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Modelo de datos para recibir la entrada desde la aplicación móvil
class InputData(BaseModel):
    texto: str  # El texto que se enviará para generar las preguntas

# Función que genera preguntas utilizando OpenAI
def generar_preguntas(texto: str):
    prompt = f"""
    Eres un generador de preguntas altamente específico y objetivo. Sigues estrictamente las siguientes reglas al generar preguntas de opción múltiple basadas en el texto proporcionado:

    1. Ambigüedad en los conceptos: Si el texto contiene términos abiertos a múltiples interpretaciones, verifica si hay suficiente contexto para definirlos claramente. Si no es claro, no generes preguntas.
    2. Falta de detalles concretos: Si el texto no tiene detalles específicos, es ambiguo o carece de claridad, no generes preguntas.
    3. Dependencia del contexto: Si las palabras dependen de un contexto para su interpretación, solo genera preguntas si el contexto es claro.
    4. Complejidad en los conceptos abstractos: Si el texto contiene conceptos abstractos o teóricos sin una base práctica, no generes preguntas.
    5. Interpretación subjetiva: Las preguntas deben ser objetivas y basadas solo en hechos proporcionados en el texto.

    Texto para analizar:
    {texto}
    """

    try:
        # Solicita a OpenAI generar las preguntas basadas en el texto proporcionado
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente para generar preguntas de opción múltiple."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000  # Ajusta este valor según tus necesidades
        )

        # Extrae el contenido generado por el modelo
        resultado = response["choices"][0]["message"]["content"]
        tokens_usados = response["usage"]["total_tokens"]
        print(f"Tokens usados en la solicitud: {tokens_usados}")

        return resultado
    except Exception as error:
        # Manejo de errores genéricos
        print(f"Error inesperado: {error}")
        return {"error": f"Error al interactuar con OpenAI o en el servidor: {str(error)}"}

# Registra manualmente el endpoint en FastAPI sin usar decoradores
def generate_questions_endpoint(app: FastAPI):
    async def generate_questions(request: Request):
        try:
            # Extrae los datos de la solicitud
            body = await request.body()
            data = json.loads(body)

            # Validación inicial del texto proporcionado
            if "texto" not in data or not data["texto"].strip():
                raise HTTPException(status_code=400, detail="El texto no puede estar vacío.")

            # Llama a la función para generar preguntas
            result = generar_preguntas(data["texto"])

            # Si el resultado contiene un error, devolvemos una excepción HTTP
            if isinstance(result, dict) and "error" in result:
                raise HTTPException(status_code=500, detail=result["error"])

            # Devuelve el resultado generado por OpenAI
            return {"resultado": result}
        except HTTPException as e:
            raise e
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"Error al procesar la solicitud: {str(error)}")

    # Asocia manualmente la ruta con la función del endpoint
    app.router.add_api_route(
        path="/generate-questions/",
        endpoint=generate_questions,
        methods=["POST"]
    )

# Agrega el endpoint a la aplicación
generate_questions_endpoint(app)
