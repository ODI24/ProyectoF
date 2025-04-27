from fastapi import FastAPI, Request, HTTPException
import firebase_admin
from firebase_admin import credentials, firestore
from pydantic import BaseModel
import json

app = FastAPI()

# Inicializar Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate('/etc/secrets/quizforge-bf3c3-firebase-adminsdk-fbsvc-7b3f56d424')
    firebase_admin.initialize_app(cred)

db = firestore.client()

class PayPalIPN(BaseModel):
    pass  # No campos estrictos porque PayPal envía muchos datos

@app.post("/paypal/webhook/")
async def paypal_webhook(request: Request):
    form_data = await request.form()
    data = dict(form_data)

    print("✅ Webhook recibido de PayPal:", data)

    if data.get("payment_status") != "Completed":
        raise HTTPException(status_code=400, detail="Pago no completado.")

    amount = float(data.get("mc_gross", "0.00"))
    user_uid = data.get("custom")

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
