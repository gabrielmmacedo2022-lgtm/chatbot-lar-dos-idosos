from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
import os

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


app = FastAPI()


#libera a requisição de endereços diferentes, já que possuem frentes diferentes e os domínios também serão diferentes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

#aqui definimos a instrução inicial para o gemini ter contexto de como agir.
SYSTEM_PROMPT = """Você é o atendente virtual do Albergue São Vicente de Paula, em Jataí (GO).
Seu tom é acolhedor, simples e paciente.
Responda de forma curta e clara, no máximo 3 parágrafos.
Nunca invente informações. Se não souber, diga que vai verificar com a equipe.

Você pode ajudar com:
- Informações sobre o Albergue
- Como fazer doações (dinheiro ou itens)
- Itens mais necessários: fraldas geriátricas, roupas GG/EG, alimentos não-perecíveis, higiene pessoal
- Como visitar ou se voluntariar

Pix, endereço e telefone serão preenchidos quando a equipe confirmar."""


# Seleciona qual modelo de de api será usado e qual instrução ele deve seguir.
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=SYSTEM_PROMPT
)

historicos = {} 


# Valida a estrutura dos dados. Se a requisição não contiver 'session_id' ou 'texto', ela é negada automaticamente.
class Mensagem(BaseModel):
    session_id: str
    texto: str



# Verifica se este usuário (identificado pelo session_id) já tem uma conversa aberta.
# Se for uma conversa nova, cria um histórico vazio associado a esse ID no dicionário.
@app.post("/chat")
async def chat(msg: Mensagem):
    if msg.session_id not in historicos:
        historicos[msg.session_id] = model.start_chat(history=[])
    
    chat_session = historicos[msg.session_id]
    resposta = chat_session.send_message(msg.texto)
    
    return {"resposta": resposta.text}



# Verifica se o servidor está online e se a conexão está funcionando corretamente
@app.get("/")
async def root():
    return {"status": "ok", "servico": "Chatbot Albergue São Vicente"}