from flask import Flask, request, render_template_string, redirect, url_for, session
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from openai import OpenAI
import logging
import weaviate
import requests
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Configuración de logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# URL del Key Vault
key_vault_url = "https://almacenrag.vault.azure.net"
secret_name = "openai"

# Autenticación (usa DefaultAzureCredential, compatible con múltiples métodos de autenticación)
credential = DefaultAzureCredential()

# Crear cliente del Key Vault
client_secret = SecretClient(vault_url=key_vault_url, credential=credential)

# Obtener el secreto
try:
    secret = client_secret.get_secret(secret_name)
    print(f"El valor del secreto '{secret_name}' es: {secret.value}")
except Exception as e:
    print(f"Error al obtener el secreto: {e}")

client = OpenAI(api_key=secret.value)

def generar_embedding2(pregunta):
    
    url = "http://50.85.209.27:8080/get_embedding"
    data = {"text": pregunta}
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=data, headers=headers)

    if response.status_code == 200:
            embedding = response.json().get('embedding')
            flat_embedding = [item for sublist in embedding for item in sublist]
            return flat_embedding
    else:
            raise Exception(f"Error: {response.status_code}, {response.text}")
        
# Configuración de la base de datos
DATABASE_URL = 'sqlite:///users.db'
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = SessionLocal()

# Modelo de usuario
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)

Base.metadata.create_all(bind=engine)

# Usuarios predefinidos
if not db_session.query(User).filter_by(username='Mario').first():
    db_session.add(User(username='Mario', password='CxeyMH_-jA3_RiY'))
if not db_session.query(User).filter_by(username='Blanca').first():
    db_session.add(User(username='Blanca', password='CxeyMH_-jA3_RiY'))
db_session.commit()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = db_session.query(User).filter_by(username=username).first()
        if user and user.password == password:
            session['username'] = username
            return redirect(url_for('index'))
    return render_template_string('''
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Login</title>
        </head>
        <body>
            <form method="POST">
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
        </body>
        </html>''')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    answer1 = None
    answer2 = None
    error = None

    # Mensaje del sistema con instrucciones detalladas y secuenciales
    system_message = (
        "You are a highly reliable assistant that must follow the steps below precisely:\n\n"
        "Step 1: Analyze the user prompt for compliance with ethical principles: Beneficence, Non-maleficence, Justice, "
        "Autonomy, Explicability, Lawfulness, and ethical use of technology. If any part of the prompt contains inaccurate, "
        "discriminatory, or harmful content (for example discriminatory phrases), "
        "correct it and document the correction. Confirm the completion of this step before proceeding.\n\n"
        "Step 2: Extract all relevant references related to the topic, ensuring that duplicates are removed and that the extraction follows the RDA standard while respecting copyright and author rights. Confirm the completion of this step.\n\n"
        "Step 3: Construct your answer in the following format:\n"
        "   - Start with the note: \"This content was generated with artificial intelligence. Please note that the information provided is based on the latest available data as of  (put here the current date).\"\n"
        "   - Provide the answer text, integrating citations in the text using the format [n] (where [n] is the reference number).\n"
        "   - Include a sentence: \"If you have any further questions or would like to delve deeper into the topic, feel free to ask.\"\n"
        "   - List the references with proper numbering and formatting (use LaTeX-style \\textit{} for titles if applicable).\n"
        "   - Append a section titled \"Trustworthiness engine:\" where you explain any corrections made during Step 1 (if any). \n\n"
        "Ensure that you confirm the completion of each step before moving to the next one and only provide the final answer once all steps have been successfully completed."
    )
    
    if request.method == 'POST':
        question = request.form['question']
        # Generar el embedding de la pregunta
        embedding = generar_embedding2(question)
        logger.info("Embedding Generado")
        if embedding:
            
            # Conectar a la instancia de Weaviate
            bbddclient = weaviate.Client("http://50.85.209.27:8081")
            # Realizar una consulta a Weaviate para obtener los chunks más cercanos
            logger.info("Lanzamos consulta a Weaviate")
            nearvector = {
                "vector": embedding,
                "certainty": 0  # Ajusta este valor según tus necesidades
            }
            # result = bbddclient.query.get("Chunk", ["content", "pageNumber", "embeddingModel", "embeddingDate", "title", "author", "publicationDate", "identifier",  "documentType", "language", "rights"]).with_near_vector(nearvector).do()
            # result = bbddclient.query.get("Chunk", ["content", "pageNumber", "embeddingModel", "embeddingDate"]).with_near_vector(nearvector).do()
            result = bbddclient.query.get("Chunk",  ["content", "pageNumber", "embeddingModel", "embeddingDate", "title", "author", "publicationDate", "identifier",  "documentType", "language", "rights"]).with_limit(5).do()
            logger.info("Recibimos repuesta de weaviate e iniciamos la generación del prompt")          
            # Construir la variable prompt
            prompt = f"Pregunta: {question}\n\nContexto relevante:\n"
            
            chunks = result.get("data", {}).get("Get", {}).get("Chunk", [])

            # Iterar sobre los chunks y extraer información
            for chunk in chunks:
                content = chunk.get("content")
                page_number = chunk.get("pageNumber")
                embedding_date = chunk.get("embeddingDate")
                title = chunk.get("title")
                author = chunk.get("author")
                publication_date = chunk.get("publicationDate")
                rights = chunk.get("rights")

                #title = None
                #author = None
                #publication_date = None
                #rights = None
                prompt += f"- {content} (Page: {page_number}, Title: {title}, Author: {author}, Publication Date: {publication_date}, Embedding Date: {embedding_date}, Rights: {rights})\n"
                logger.info("Prompt Construido")

        '''    
        # Enviar el prompt al modelo de OpenAI
            logger.info("Llamamos a openAI con la llamada standard")
            response1 = client.chat.completions.create(
                model="gpt-4o-mini",
                store=False,
                messages=[
                    {"role": "system", "content": "You are a useful assistant that adheres to ethical principles and communicate in a formal and friendly tone in the same language of the question."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                n=1,
                temperature=0.5
            )


   	    # Enviar el prompt al modelo de OpenAI
            logger.info("Llamamos a openAI con la llamada Trust")
            response2 = client.chat.completions.create(
                model="gpt-4o-mini",
                store=False,
                messages=[
                    {  "role": "system",   "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
                n=1,
                temperature=0.5
            )

        # Imprimir la respuesta generada
        logger.info("Iniciamos la impresión de las preguntas")
        answer1 = response1.choices[0].message.content
        answer2 = response2.choices[0].message.content
        '''
        # Almacenar la salida de Weaviate en answer1
        answer1 = result
        # Almacenar el prompt construido en answer2
        answer2 = prompt
    return render_template_string('''
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>TRUSTWORTHY RAG</title>
    </head>
    <body>
        <h1>TRUSTWORTHY RAG</h1>
        <form method="post">
            <label for="question">Write your question:</label><br><br>
            <textarea id="question" name="question" rows="10" cols="50" maxlength="800"></textarea><br><br>
            <input type="submit" value="Enviar">
        </form>
        {% if answer1 %}
            <h2>Standard Answer:</h2>
            <p>{{ answer1 }}</p>
        {% endif %}
        {% if answer2 %}
            <h2>Trustworthy Answer:</h2>
            <p>{{ answer2 }}</p>
        {% endif %}
        {% if error %}
            <h2>Error:</h2>
            <p>{{ error }}</p>
        {% endif %}
        <a href="{{ url_for('logout') }}">Logout</a>
    </body>
    </html>
    ''', answer1=answer1, answer2=answer2, error=error)

if __name__ == '__main__':
    app.run(debug=True)
