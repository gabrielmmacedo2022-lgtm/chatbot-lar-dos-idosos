from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

# Inicializa o cliente com as novas chaves
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

try:
    # Vamos tentar listar o que tem na view de estoque
    print("Tentando buscar dados de: view_estoque_atual")
    resultado = supabase.table("view_estoque_atual").select("*").limit(5).execute()
    
    print("Sucesso! Dados encontrados:")
    print(resultado.data)
except Exception as e:
    print("Erro ao conectar ou buscar dados:", e)