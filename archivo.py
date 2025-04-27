from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
import openai
import json
import os
import firebase_admin
import requests
from firebase_admin import credentials, firestore
from requests.auth import HTTPBasicAuth

# Inicializar Firebase Admin SDK una sola vez
if not firebase_admin._apps:
    cred = credentials.Certificate('/etc/secrets/quizforge-bf3c3-firebase-adminsdk-fbsvc-7b3f56d424')
    firebase_admin.initialize_app(cred)

db = firestore.client()

openai.api_key = os.getenv("API_KEY")  # Variable de entorno

app = FastAPI()

# =========================
# Endpoint de Generar Preguntas
# =========================

class DatosRecibidos(BaseModel):
    texto: str

def GenerarPreguntas(texto: str):
    prompt = f"""Q 
    (todo tu prompt sigue igual)
    Texto para analizar:
    {texto}
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente para generar preguntas de opción múltiple"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        resultado = response["choices"][0]["message"]["content"]
        tokens_usados = response["usage"]["total_tokens"]
        print(f"Tokens usados en la solicitud: {tokens_usados}")
        return {
            "resultado": resultado,
            "tokens_usados": tokens_usados
        }
    except Exception as error:
        return {"error": f"Error al interactuar con OpenAI: {str(error)}"}



@app.post("/generate-questions/")
async def Manejo_GenerarPreguntas(request: Request):
    body = await request.body()
    data = json.loads(body)

    uid = data.get("uid")  # 🔥 🔥 🔥 Muy importante: ahora debes enviar el UID desde la app

    if not uid:
        raise HTTPException(status_code=400, detail="Falta el UID del usuario.")

    resultado = GenerarPreguntas(data["texto"])

    if isinstance(resultado, dict) and "error" in resultado:
        return resultado

    # Se vuelve a llamar mal aquí, eliminamos esta llamada duplicada:
    # response = openai.ChatCompletion.create(...)
    # tokens_usados = response["usage"]["total_tokens"]

    # Recupera los tokens usados del primer llamado
    tokens_usados = resultado.get("tokens_usados") if isinstance(resultado, dict) else None

    if not tokens_usados:
        raise HTTPException(status_code=400, detail="No se pudieron calcular los tokens usados.")

    # 🔥 Actualizar tokens en Firestore
    user_ref = db.collection('usuarios').document(uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        current_tokens = user_data.get('tokens', 0)

        if not isinstance(current_tokens, int):
            current_tokens = 0

        if current_tokens < tokens_usados:
            raise HTTPException(status_code=400, detail="No tienes suficientes tokens.")

        new_token_balance = current_tokens - tokens_usados
        user_ref.update({'tokens': new_token_balance})

        print(f"✅ Tokens descontados: {tokens_usados}. Balance ahora: {new_token_balance}")
    else:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    return {"resultado": resultado, "tokens_usados": tokens_usados}


# =========================
# Endpoint Webhook de PayPal
# =========================

@app.post("/paypal/webhook/")
async def paypal_webhook(request: Request):
    data = await request.json()

    print("✅ Webhook recibido de PayPal:", data)

    # Detectar tipo de evento
    event_type = data.get("event_type")
    resource = data.get("resource")

    if event_type == "CHECKOUT.ORDER.COMPLETED":
        amount = float(resource["purchase_units"][0]["amount"]["value"])
        user_uid = resource["purchase_units"][0]["custom_id"]

    elif event_type == "PAYMENT.SALE.COMPLETED":
        amount = float(resource["amount"]["total"])
        user_uid = None

        print(f"✅ Pago recibido: {amount} USD")
        return {"message": "Pago recibido, pero sin user_uid."}

    else:
        raise HTTPException(status_code=400, detail="Evento de Webhook no soportado.")

    if not user_uid:
        raise HTTPException(status_code=400, detail="Falta UID del usuario.")

    tokens_to_add = 0
    if amount == 1.00:
        tokens_to_add = 1000
    elif amount == 5.00:
        tokens_to_add = 5000
    elif amount == 10.00:
        tokens_to_add = 10000
    else:
        raise HTTPException(status_code=400, detail="Monto no válido.")

    user_ref = db.collection('usuarios').document(user_uid)
    user_doc = user_ref.get()

    if user_doc.exists:
        current_tokens = user_doc.to_dict().get('tokens', 0)
        user_ref.update({'tokens': current_tokens + tokens_to_add})
        print(f"✅ Tokens actualizados para UID {user_uid}: {current_tokens} ➡️ {current_tokens + tokens_to_add}")
        return {"message": "Tokens agregados exitosamente."}
    else:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

# =========================
# Endpoint PayPal Success
# =========================

@app.get("/paypal/success")
async def paypal_success(token: str):
    try:
        client_id = "AUa7RDnRzErc3h2jSSybsUSH9UOkJzanZ51pD3Z0yIK1oajN5x9-c1XVeQrVyn8d4qYZRXJ94feyrPZQ"
        client_secret = "EBVIEVa_JfQfDmh8Uawg4IRxqHPXNS0L6MZ__W3x7uB2RzZK8ynnnU8H2kPMmfvx1yNgTQL9AzC9O8dD"

        # Obtener Access Token
        auth_response = requests.post(
            'https://api-m.sandbox.paypal.com/v1/oauth2/token',
            data={'grant_type': 'client_credentials'},
            auth=HTTPBasicAuth(client_id, client_secret)
        )
        auth_response.raise_for_status()
        access_token = auth_response.json()['access_token']

        # Capturar Orden
        capture_response = requests.post(
            f'https://api-m.sandbox.paypal.com/v2/checkout/orders/{token}/capture',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            }
        )
        capture_response.raise_for_status()

        capture_data = capture_response.json()
        print('✅ Orden capturada exitosamente:', capture_data)

        # === 🔥 NUEVO: actualizar tokens manualmente 🔥 ===
        purchase_unit = capture_data["purchase_units"][0]
        capture_details = purchase_unit["payments"]["captures"][0]
        amount = float(capture_details["amount"]["value"])
        custom_id = capture_details.get("custom_id")  # El UID del usuario

        if not custom_id:
            print("❌ Error: No se encontró custom_id en la captura.")
            return RedirectResponse(url="https://proyectof-gmma.onrender.com/pago-error")

        # Calcular tokens a agregar
        tokens_to_add = 0
        if amount == 1.00:
            tokens_to_add = 1000
        elif amount == 5.00:
            tokens_to_add = 5000
        elif amount == 10.00:
            tokens_to_add = 10000
        else:
            print("❌ Error: Monto de pago no reconocido.")
            return RedirectResponse(url="https://proyectof-gmma.onrender.com/pago-error")

        # Actualizar Firestore
        user_ref = db.collection('usuarios').document(custom_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            current_tokens = user_data.get('tokens', 0)

            if not isinstance(current_tokens, int):
                current_tokens = 0  # 🔥 Si "tokens" existe pero no es número, lo corregimos

            user_ref.update({'tokens': current_tokens + tokens_to_add})
            print(f"✅ Tokens actualizados para UID {custom_id}: {current_tokens} ➡️ {current_tokens + tokens_to_add}")
        else:
            # 🔥 Si no existe el usuario, crear registro con los tokens iniciales
            user_ref.set({'tokens': tokens_to_add})
            print(f"✅ Usuario creado con UID {custom_id} y {tokens_to_add} tokens asignados.")

        # === 🔥 Fin actualización de tokens ===

        return RedirectResponse(url="https://proyectof-gmma.onrender.com/pago-exitoso")

    except Exception as e:
        print('❌ Error capturando pago:', str(e))
        return RedirectResponse(url="https://proyectof-gmma.onrender.com/pago-error")



# =========================
# Endpoints HTML: pago exitoso y error
# =========================

@app.get("/pago-exitoso", response_class=HTMLResponse)
async def pago_exitoso():
    return """
    <html>
      <head><title>Pago Exitoso</title></head>
      <body style="background-color: #111827; color: #4CAF50; display: flex; justify-content: center; align-items: center; height: 100vh; flex-direction: column;">
        <h1>✅ ¡Pago realizado con éxito!</h1>
        <p>Ya puedes regresar a la app y continuar.</p>
      </body>
    </html>
    """

@app.get("/pago-error", response_class=HTMLResponse)
async def pago_error():
    return """
    <html>
      <head><title>Error en el Pago</title></head>
      <body style="background-color: #111827; color: #DC2626; display: flex; justify-content: center; align-items: center; height: 100vh; flex-direction: column;">
        <h1>❌ Hubo un problema con tu pago.</h1>
        <p>Por favor intenta nuevamente.</p>
      </body>
    </html>
    """
