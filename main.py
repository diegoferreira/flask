import os
import requests
from flask import Flask, request, redirect, session, url_for, jsonify
from dotenv import load_dotenv
from supabase import create_client, Client
from urllib.parse import urlencode
import time
import logging
logging.basicConfig(level=logging.INFO)

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# --- Configurações ---
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Configurações do Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive.file" # Permissão para criar arquivos

# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Rotas da Aplicação ---

@app.route("/")
def index():
    return "Servidor de autorização para o bot do WhatsApp está funcionando."

@app.route("/authorize/<user_id>")
def authorize(user_id):
    """
    Inicia o fluxo de autorização.
    O bot do WhatsApp deve chamar esta URL, que redirecionará o usuário para a tela de consentimento do Google.
    """
    # Armazena o ID do usuário na sessão para recuperá-lo no callback
    session['user_id'] = user_id
    
    # Parâmetros para a URL de autorização do Google
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",  # Necessário para obter o refresh_token
        "prompt": "consent"       # Garante que o usuário sempre veja a tela de consentimento
    }
    
    # Constrói a URL completa e redireciona o usuário
    auth_url_with_params = f"{AUTH_URL}?{urlencode(params)}"
    return redirect(auth_url_with_params)

@app.route("/oauth2callback")
def oauth2callback():
    """
    Endpoint de callback que o Google chama após o usuário dar o consentimento.
    """
    try:
        # 1. Obter o código de autorização da URL
        auth_code = request.args.get('code')
        print(f"[DEBUG] Auth code recebido: {auth_code[:10] if auth_code else 'None'}...")
        
        if not auth_code:
            print("[ERROR] Código de autorização não encontrado")
            return "Erro: Código de autorização não encontrado.", 400

        # 2. Obter o user_id que foi salvo na sessão
        user_id = session.get('user_id')
        print(f"[DEBUG] User ID da sessão: {user_id}")
        
        if not user_id:
            print("[ERROR] Sessão do usuário não encontrada")
            return "Erro: Sessão do usuário expirada ou não encontrada. Por favor, inicie o processo novamente.", 400

        # 3. Trocar o código de autorização por tokens de acesso
        print("[DEBUG] Iniciando troca de código por tokens...")
        
        token_data = {
            "code": auth_code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        response = requests.post(TOKEN_URL, data=token_data)
        print(f"[DEBUG] Status da resposta do Google: {response.status_code}")
        
        token_info = response.json()
        print(f"[DEBUG] Token info recebido: {list(token_info.keys()) if token_info else 'None'}")

        if response.status_code != 200:
            print(f"[ERROR] Erro ao obter tokens: {token_info}")
            return f"Erro ao obter tokens: {token_info}", 400

        # 4. Salvar os tokens no Supabase
        print("[DEBUG] Iniciando salvamento no Supabase...")
        
        try:
            # Prepara os dados para inserir ou atualizar na tabela
            data_to_upsert = {
                "user_id": str(user_id),
                "access_token": token_info["access_token"],
                "refresh_token": token_info.get("refresh_token"),
                "expires_in": int(token_info["expires_in"]),
            }
            
            print(f"[DEBUG] Dados preparados para Supabase: user_id={user_id}, expires_in={token_info['expires_in']}")
            
            # Tentar inserir primeiro
            response = supabase.table('google_tokens').insert(data_to_upsert).execute()
            print(f"[DEBUG] Inserção no Supabase bem-sucedida")

        except Exception as supabase_error:
            print(f"[ERROR] Erro no Supabase: {supabase_error}")
            return f"Erro ao salvar tokens no Supabase: {supabase_error}", 500
        
        # Limpa o user_id da sessão após o uso
        session.pop('user_id', None)
        print("[DEBUG] Processo concluído com sucesso")

        # 5. Redirecionar para uma página de sucesso
        return "Autorização concluída com sucesso! Você já pode fechar esta janela."
        
    except Exception as general_error:
        print(f"[ERROR] Erro geral no callback: {general_error}")
        return f"Erro interno: {general_error}", 500



@app.route("/oauth3callback")
def oauth3callback():
    """
    Endpoint de callback que o Google chama após o usuário dar o consentimento.
    """
    # 1. Obter o código de autorização da URL
    auth_code = request.args.get('code')
    if not auth_code:
        return "Erro: Código de autorização não encontrado.", 400

    # 2. Obter o user_id que foi salvo na sessão
    user_id = session.get('user_id')
    if not user_id:
        return "Erro: Sessão do usuário expirada ou não encontrada. Por favor, inicie o processo novamente.", 400

    # 3. Trocar o código de autorização por tokens de acesso
    token_data = {
        "code": auth_code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    response = requests.post(TOKEN_URL, data=token_data)
    token_info = response.json()

    if response.status_code != 200:
        return f"Erro ao obter tokens: {token_info}", 400

    # 4. Salvar os tokens no Supabase
    try:
        # Prepara os dados para inserir ou atualizar na tabela
        data_to_upsert = {
            "user_id": user_id,
            "access_token": token_info["access_token"],
            "refresh_token": token_info.get("refresh_token"), # refresh_token pode não vir sempre
            "expires_in": token_info["expires_in"],
            "updated_at": "now()" # Função do PostgreSQL para pegar o tempo atual
        }

        # 'upsert' irá inserir uma nova linha ou atualizar uma existente se o user_id já existir
        data, count = supabase.table('google_tokens').upsert(data_to_upsert).execute()

    except Exception as e:
        return f"Erro ao salvar tokens no Supabase: {e}", 500
    
    # Limpa o user_id da sessão após o uso
    session.pop('user_id', None)

    # 5. Redirecionar para uma página de sucesso ou exibir mensagem
    # O ideal é que seu bot envie uma mensagem de confirmação no WhatsApp.
    return "Autorização concluída com sucesso! Você já pode fechar esta janela."

if __name__ == "__main__":
    # Para desenvolvimento, use o servidor Flask. Para produção, use um servidor WSGI como Gunicorn.
    app.run(debug=True, port=5000)
