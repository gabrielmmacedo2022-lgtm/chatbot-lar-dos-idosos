from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client
import os

import httpx

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Configurações do WhatsApp
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# Conecta no Supabase
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

#acessa o arquivo "documento.md" e realiza a leitura das informações para maior contextualização do modelo
def carregar_dados_institucionais():
    caminho = "documento.md" 
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            return f.read()
    return "Informações institucionais não disponíveis."


DADOS_INSTITUCIONAIS = carregar_dados_institucionais()

SYSTEM_PROMPT_BASE = """Você é o atendente virtual do Albergue São Vicente de Paula, em Jataí (GO).
Seu tom é acolhedor, simples e paciente.
Responda de forma curta e clara, no máximo 3 parágrafos.

IMPORTANTE: As informações abaixo são OFICIAIS e CONFIÁVEIS do Albergue. Use-as diretamente nas respostas sem hesitar.

{documento}
{faqs}
{estoque}

Se a pergunta não estiver coberta pelas informações acima, aí sim diga que vai verificar com a equipe."""

historicos = {}

class Mensagem(BaseModel):
    session_id: str
    texto: str

def buscar_faqs():
    try:
        resultado = supabase.table("faqs").select("pergunta, resposta").eq("ativo", True).execute()
        faqs = resultado.data
        
        if not faqs:
            return "Nenhuma informação disponível no momento."
        
        texto = ""
        for faq in faqs:
            texto += f"P: {faq['pergunta']}\nR: {faq['resposta']}\n\n"
        return texto
    except Exception as e:
        print(f"Erro ao buscar FAQs: {e}")
        return "Nenhuma informação disponível no momento."

def buscar_estoque():
    try:
        resultado = supabase.table("view_estoque_atual").select("item, categoria, quantidade_atual, unidade_medida").execute()
        itens = resultado.data
        if not itens:
            return "Informações de estoque não disponíveis no momento."
        
        texto = "Estoque atual do Albergue:\n"
        for item in itens:
            quantidade = item['quantidade_atual']
            if quantidade is None:
                quantidade = "não informado"
            texto += f"- {item['item']} ({item['categoria']}): {quantidade} {item['unidade_medida']}\n"
        return texto
    except Exception as e:
        print(f"Erro ao buscar estoque: {e}")
        return "Informações de estoque não disponíveis no momento."

async def enviar_mensagem_whatsapp(numero, texto):
    """Envia a resposta de volta para o usuário via API do WhatsApp Cloud."""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto}
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Erro ao enviar mensagem para WhatsApp: {e}")
            return None

def obter_resposta_gemini(session_id, texto_usuario):
    # Busca dados atualizados para o prompt
    faqs = buscar_faqs()
    estoque = buscar_estoque()
    
    system_prompt = SYSTEM_PROMPT_BASE.format(
        documento=DADOS_INSTITUCIONAIS, 
        faqs=faqs, 
        estoque=estoque
    )
    
    
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt
    )
    
    if session_id not in historicos:
        historicos[session_id] = model.start_chat(history=[])
        
    chat_session = historicos[session_id]
    resposta = chat_session.send_message(texto_usuario)
    return resposta.text

@app.post("/chat")
async def chat(msg: Mensagem):
    try:
        resposta = obter_resposta_gemini(msg.session_id, msg.texto)
        return {"resposta": resposta}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    return {"status": "ok", "servico": "Chatbot Albergue São Vicente"}

@app.post("/webhook-whatsapp-teste")
async def webhook_whatsapp_teste(request: Request):
    try:
        dados = await request.json()
        
        if "entry" in dados and dados["entry"]:
            changes = dados["entry"][0].get("changes", [])
            if changes:
                value = changes[0].get("value", {})
                if "messages" in value and value["messages"]:
                    mensagem = value["messages"][0]
                    numero_usuario = mensagem.get("from")
                    
                    if mensagem.get("type") == "text":
                        texto_usuario = mensagem.get("text", {}).get("body")
                        
                        # Gera resposta via Gemini
                        resposta_gemini = obter_resposta_gemini(numero_usuario, texto_usuario)
                        
                        # ENVIA DE VOLTA PARA O WHATSAPP
                        await enviar_mensagem_whatsapp(numero_usuario, resposta_gemini)
                        
                        print(f"\n[META WPP] Mensagem de {numero_usuario}: {texto_usuario}")
                        print(f"[META WPP] Resposta enviada:\n{resposta_gemini}\n")
                        
                        return {"status": "sucesso"}
                        
    except Exception as e:
        print(f"Erro ao processar dados da Meta: {e}")
        return {"status": "erro", "detalhes": str(e)}
        
    return {"status": "dados_nao_relevantes"}