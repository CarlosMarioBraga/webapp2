from flask import Flask, request, render_template_string, redirect, url_for, session
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from openai import OpenAIError, AzureOpenAI 
import logging
import weaviate
import requests


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Configuración de logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

client = OpenAI(
    api_key="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"
)


clientchat = AzureOpenAI(
  azure_endpoint = "https://euserv4chatfinalization.openai.azure.com/", 
  api_key = "KLuw7NzikQIXxBXLcVJtfecbCTat2SS9J4pz0hCHf8KRenLvzoR3JQQJ99BAACfhMk5XJ3w3AAABACOG34Ko",  
  api_version = "2024-02-01"
)

def generar_embedding(pregunta):
    try:
        response = client.embeddings.create(
            input=pregunta,
            model="embedding"  # Usa el nombre del modelo que has desplegado
        )
        embedding = response['data'][0]['embedding']  

        return embedding, None
    except OpenAIError as e:
        # Captura errores específicos de OpenAI
        return None, f"OpenAIError: {str(e)}"
    except Exception as e:
        # Captura cualquier otro tipo de error
        return None, str(e)

def generar_embedding2(pregunta):
    
    url = "http://50.85.209.27:8080/get_embedding"
    data = {"text": pregunta}

    response = requests.post(url, json=data)

    if response.status_code == 200:
        return response.json().get('embedding')
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
    </html>
    ''')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    answer = None
    error = None
    
    if request.method == 'POST':
        question = request.form['question']
        # Generar el embedding de la pregunta
        embedding, error = generar_embedding2(question)
        if embedding:
            
            # Conectar a la instancia de Weaviate
            bbddclient = weaviate.Client("http://50.85.209.27:8080")
            # Realizar una consulta a Weaviate para obtener los chunks más cercanos
            near_vector = {
                "vector": embedding,
                "certainty": 0.7  # Ajusta este valor según tus necesidades
            }
            result = bbddclient.query.get("Chunk", ["content", "pageNumber", "embeddingModel", "embeddingDate", "document { ... on Document { title author publicationDate identifier documentType language publisher rights } }"]).with_near_vector(near_vector).do()
            """
            result = {
                      "data": {
                          "Get": {
                              "Chunk": [
                                  {
                                      "content": "Un dedo es una de las extremidades de la mano o del pie.",
                                      "pageNumber": 15,
                                      "embeddingModel": "model_v1",
                                      "embeddingDate": "2025-01-07",
                                      "document": {
                                          "title": "Anatomía Humana",
                                          "author": "Dr. Juan Pérez",
                                          "publicationDate": "2023-05-10",
                                          "identifier": "ISBN1234567890",
                                          "documentType": "Libro",
                                          "language": "es",
                                          "publisher": "Editorial Salud",
                                          "rights": "Todos los derechos reservados"
                                      }
                                  },
                                  {
                                      "content": "Los dedos son esenciales para la manipulación de objetos.",
                                      "pageNumber": 22,
                                      "embeddingModel": "model_v1",
                                      "embeddingDate": "2025-01-07",
                                      "document": {
                                          "title": "Fisiología del Movimiento",
                                          "author": "Dra. María López",
                                          "publicationDate": "2022-11-15",
                                          "identifier": "ISBN0987654321",
                                          "documentType": "Libro",
                                          "language": "es",
                                          "publisher": "Editorial Ciencia",
                                          "rights": "Todos los derechos reservados"
                                      }
                                  }
                              ]
                          }
                      }
                  }
            """
                  
            # Construir la variable prompt
            prompt = f"Pregunta: {question}\n\nContexto relevante:\n"
            
            # Iterar sobre los chunks en el resultado y agregar la información relevante al prompt
            for chunk in result['data']['Get']['Chunk']:
                content = chunk['content']
                page_number = chunk['pageNumber']
                embedding_date = chunk['embeddingDate']
                document = chunk['document']
                title = document['title']
                author = document['author']
                publication_date = document['publicationDate']
                rights = document['rights']
                
                prompt += f"- {content} (Page: {page_number}, Title: {title}, Author: {author}, Publication Date: {publication_date}, Embedding Date: {embedding_date}, Rights: {rights})\n"

            
        # Enviar el prompt al modelo de OpenAI
            response1 = client.chat.completions.create(
                model="gpt-4o-mini",
                store=False,
                messages=[
                    {"role": "system", "content": "You are a useful assistant that adheres to ethical principles and communicate in a formal and friendly tone in the same language of the question."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                n=1,
                stop=["\n"],
                temperature=0.5
            )


   	    # Enviar el prompt al modelo de OpenAI
            response2 = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                store=False,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a useful assistant that adheres to ethical principles and communicate in a formal and friendly tone in the same language of the question. \
                        This is the sequential process you should follow step by step with full attention: \
                        Step 1: Please analyze if the complete prompt adheres to the following ethical principles: \
                        Beneficence: Promote the user's well-being. \
                        Non-maleficence: Avoid causing harm. \
                        Justice: Ensure fairness and non-discrimination or bias. \
                        Autonomy: Respect the user's autonomy and decisions. \
                        Explicability: Provide clear and understandable explanations. \
                        Lawfulness: Comply with all applicable laws and regulations. \
                        Technology: Use advanced technology ethically and responsibly and manage all these interrelated principles in an integrated way. \
                        Confirm completion. If any part of the prompt contains incorrect, discriminatory, or harmful information, including gender bias, you must correct it before proceeding and document the correction. Include a message in the response indicating that the Trustworthiness engine was activated and describe the correction made. \
                        Step 2: Extract references from the prompt, ensuring that duplicated references appear only once and following the RDA (Resource Description and Access) standard, with great respect for copyright and author rights. Confirm completion. \
                        Step 3: Construct the answer to the question by composing a response based on the relevant context provided and by intercalating citations to the references from Step 2 within the text using the format [n], where [n] corresponds to the reference number. Confirm completion. Ensure that the citations are included in the response text. \
                        If any of these steps are not followed, you must generate an error message indicating which step was not completed correctly. Confirm completion of each step before proceeding to the next."
                    },
                    {"role": "user", "content": prompt},
                    {
                        "role": "assistant",
                        "content": "This content was generated with artificial intelligence. Please note that the information provided is based on the latest available data as of [current date].\n\n \
                        [Answer to the question (step 3), including citations to references as appropriate with format [n], where [n] corresponds to the reference number]. Ensure that the citations are intercalated within the text to support the information provided.\n\n \
                        If you have any further questions or would like to delve deeper into the topic, feel free to ask.\n\n \
                        References: Author (Date). *Title*. Rights (Step 2)\n\n \
                        [Trustworthiness engine: (only if the step 1 analysis of the prompt reveals any issue) A brief summary of the problem found in the question or in the context and a message saying that it was avoided in the response. Document the correction made to address the issue.]"
                    }
                ],
                max_tokens=600,
                n=1,
                stop=["\n"],
                temperature=0.5
            )
    # Imprimir la respuesta generada

    answer1 = response1.choices[0].message.content
    answer2 = response1.choices[0].message.content
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
        {% if answer 1 %}
            <h2>Standard Answer:</h2>
            <p>{{ answer1 }}</p>
        {% endif %}
        {% if answer 2 %}
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
    ''', answer=answer, error=error)

if __name__ == '__main__':
    app.run(debug=True)

