from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client
import os

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

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



#declaração de uma função que busca no banco de dados informações relacionado a FAQS.
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


#declaração de uma função que realiza busca de informações a respeito de estoque no banco de dados.
def buscar_estoque():
    try:
        resultado = supabase.table("view_estoque_atual").select("item, categoria, quantidade_atual, unidade_medida").execute()
        print("Estoque encontrado:", resultado.data)
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


@app.post("/chat")
async def chat(msg: Mensagem):
    # Busca FAQs do banco
    faqs = buscar_faqs()
    estoque = buscar_estoque()

    
    # Monta o system prompt com as FAQs
    system_prompt = SYSTEM_PROMPT_BASE.format(documento= DADOS_INSTITUCIONAIS,faqs=faqs, estoque=estoque)
    
    # Cria ou atualiza o modelo com o prompt atualizado
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt
    )
    
    if msg.session_id not in historicos:
        historicos[msg.session_id] = model.start_chat(history=[])
    
    chat_session = historicos[msg.session_id]
    resposta = chat_session.send_message(msg.texto)
    
    return {"resposta": resposta.text}

@app.get("/")
async def root():
    return {"status": "ok", "servico": "Chatbot Albergue São Vicente"}


@app.post("/webhook-whatsapp-teste")
async def webhook_whatsapp_teste(request: Request):
    """
    Rota para receber as mensagens enviadas para o número de teste da Meta.
    Usa a mesma lógica de banco e IA, mantendo o histórico pelo número de telefone.
    """
    try:
        dados = await request.json()
        
        # Estrutura padrão que a Meta envia quando alguém manda mensagem de texto
        if "entry" in dados and dados["entry"]:
            changes = dados["entry"][0].get("changes", [])
            if changes:
                value = changes[0].get("value", {})
                if "messages" in value and value["messages"]:
                    mensagem = value["messages"][0]
                    
                    numero_usuario = mensagem.get("from")
                    
                    # Garante que é uma mensagem de texto antes de ler o conteúdo
                    if mensagem.get("type") == "text":
                        texto_usuario = mensagem.get("text", {}).get("body")
                        
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
                        
                        # O número de telefone vira o session_id exclusivo daquela pessoa
                        if numero_usuario not in historicos:
                            historicos[numero_usuario] = model.start_chat(history=[])
                            
                        chat_session = historicos[numero_usuario]
                        resposta_gemini = chat_session.send_message(texto_usuario).text
                        # ================================
                        
                        # Mostra no terminal o resultado do processamento da Meta
                        print(f"\n[META WPP TESTE] Mensagem de {numero_usuario}: {texto_usuario}")
                        print(f"[META WPP TESTE] Resposta criada:\n{resposta_gemini}\n")
                        
                        return {"status": "sucesso", "mensagem": "Processado com sucesso"}
                        
    except Exception as e:
        print(f"Erro ao processar dados da Meta: {e}")
        return {"status": "erro", "detalhes": str(e)}
        
    return {"status": "dados_nao_relevantes"}