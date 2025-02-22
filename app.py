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
import markdown
from datetime import datetime


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
    question = ""

    # Mensaje del sistema con instrucciones detalladas y secuenciales

    system_message = (
        "You are a highly reliable assistant. Follow the instructions below precisely to generate your final answer:\n\n"
        "Before constructing your final answer, perform the following internal processes without outputting any details:\n"
        "   - Analyze the user prompt for compliance with ethical principles (Beneficence, Non-maleficence, Justice, Autonomy, Explicability, Lawfulness, and ethical use of technology). Correct any issues internally.\n"
        "   - Extract all relevant references related to the topic, ensuring that duplicates are removed and that the extraction follows the RDA standard while respecting copyright and author rights.\n\n"
        "Now, construct your final answer using the following format:\n"
        "   1. Start with the note: \"This content was generated with artificial intelligence. Please note that the information provided is based on the latest available data as of 31-12-9999.\" \n"
        "   2. Provide the answer text, integrating citations using the format [n] (where [n] is the reference number). Ensure that each citation is placed directly next to the portion of text it supports, and avoid appending all references after every sentence.\n"
        "   3. Include the sentence: \"If you have any further questions or would like to delve deeper into the topic, feel free to ask.\"\n"
        "   4. Append a section with the header __References:__ (using Markdown for underlining) followed by the list of references, each on a new line with proper numbering and formatting. The reference titles must be displayed in italics using Markdown (e.g., Title). Include the 'Rights' field for each reference.\n"
        "   5. Append a section with the header __Trustworthiness engine:__ (using Markdown for underlining) where you briefly explain any corrections made during your internal ethical analysis (include this section only if any corrections were performed).\n\n"
        "Important formatting instructions:\n"
        "   - Use actual newline characters (\\n) for line breaks instead of HTML tags.\n"
        "   - Use Markdown syntax (e.g., *italic text*) to render text in italics.\n\n"
        "Only output the final answer following the format above, without disclosing any details of the internal processes."
    )
   
    if request.method == 'POST':
        question = request.form['question']
        '''
        # Generar el embedding de la pregunta
        embedding = generar_embedding2(question)
        logger.info("Embedding Generado")
        if embedding:
            
            # Conectar a la instancia de Weaviate
            bbddclient = weaviate.Client("http://50.85.209.27:8081", additional_headers={"Connection":"close"})
            # Realizar una consulta a Weaviate para obtener los chunks más cercanos
            logger.info("Lanzamos consulta a Weaviate")
            nearvector = {
                "vector": embedding,
                "certainty": 0.7  # Ajusta este valor según tus necesidades
            }
            #result = bbddclient.query.get("Chunk", ["content", "pageNumber", "embeddingModel", "embeddingDate", "title", "author", "publicationDate", "identifier",  "documentType", "language", "rights"]).with_near_vector(nearvector).do()
            # result = bbddclient.query.get("Chunk", ["content", "pageNumber", "embeddingModel", "embeddingDate"]).with_near_vector(nearvector).do()
            result = bbddclient.query.get("Chunk",  ["content", "pageNumber", "embeddingModel", "embeddingDate", "title", "author", "publicationDate", "identifier",  "documentType", "language", "rights"]).with_limit(100).do()
            logger.info("Recibimos repuesta de weaviate e iniciamos la generación del prompt")          
            # Construir la variable prompt
            prompt = f"Question: {question}\n\nItems of relevant context:\n"
            
            chunks = result.get("data", {}).get("Get", {}).get("Chunk", [])
            chunkNumber=1

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
                prompt += f"- Relevant context {chunkNumber} : {content} (Page: {page_number}, Title: {title}, Author: {author}, Publication Date: {publication_date}, Embedding Date: {embedding_date}, Rights: {rights})\n"
                chunkNumber = chunkNumber + 1
                logger.info("Prompt Construido")

           
        
        prompt9 = "Question: What are the challenges and limitations in detecting life on Europa, and how do researchers overcome them? - Items of relevant context: - Relevant context 14 : potential habitats. Contamination: Ensuring that samples and instruments are not contaminated with Earth-based organisms. Implications for Astrobiology The discovery of life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Research Methods to Detect Life on Europa, Author: Dr. John Smith, Department of Astrobiology, Europa Research Institute Dr. Jane Doe, Department of Planetary Sciences, Mars Institute, Publication Date: 2025-01-27T00:00:00Z, Embedding Date: 2025-02-21T19:16:36Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 12 : environment. These could include: Radiation Resistance: Enhanced DNA repair systems to cope with radiation-induced damage. Cryoprotection: Mechanisms to prevent ice crystal formation within cells. Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Methods of Detection Detecting evolutionary processes on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify evolutionary adaptations. Submersible Probes: Equipped with sensors to observe and study organisms in their natural habitat. Sample Return Missions: To analyze water and ice samples for signs of evolutionary processes. Implications for Astrobiology Understanding the evolution of life in a closed (Page: 1, Title: Analyzing the Evolution of Life in a Closed Environment Like Europa, Author: Dr. Jessica Taylor, Department of Evolutionary Biology, Europa Research Institute Dr. Daniel Roberts, Department of Astrobiology, Enceladus University, Publication Date: 2025-01-20T00:00:00Z, Embedding Date: 2025-02-21T19:16:58Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 9 : techniques, such as: Submersible Probes: Equipped with sensors to measure chemical gradients and biological activity in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for chemical composition and signs of life. Implications for Astrobiology Understanding the water chemistry in Europa's oceans and its impact on potential life forms would have profound implications for our understanding of life in the universe. It would suggest that life can adapt to a wide range of chemical environments, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Studying the Water Chemistry in the Oceans of Europa and Its Impact on Life, Author: Dr. Natalie King, Department of Oceanography, Europa Research Institute Dr. Peter Johnson, Department of Astrobiology, Triton University, Publication Date: 2025-01-21T00:00:00Z, Embedding Date: 2025-02-21T19:16:20Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt10 = "Question: How does the potential genetic diversity of organisms on Europa relate to the research methods used to detect life, and what role does gender bias play in the research process? - Items of relevant context: - Relevant context 4 : between different species to enhance adaptability. Symbiotic Relationships: Evolution of mutualistic relationships that promote genetic exchange and diversity. Adaptive Radiation: Rapid diversification of species to exploit different ecological niches. Methods of Detection Detecting genetic diversity on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify genetic variations and adaptations. Submersible Probes: Equipped with sensors to collect and analyze genetic material in the ocean. Sample Return Missions: To analyze water and ice samples for signs of genetic diversity. Implications for Astrobiology Understanding the genetic diversity of possible organisms on Europa would have profound (Page: 1, Title: Analyzing the Genetic Diversity of Possible Organisms on Europa, Author: Dr. Sarah Johnson, Department of Genetics, Europa Research Institute Dr. David Lee, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-25T00:00:00Z, Embedding Date: 2025-02-21T19:16:26Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 14 : potential habitats. Contamination: Ensuring that samples and instruments are not contaminated with Earth-based organisms. Implications for Astrobiology The discovery of life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Research Methods to Detect Life on Europa, Author: Dr. John Smith, Department of Astrobiology, Europa Research Institute Dr. Jane Doe, Department of Planetary Sciences, Mars Institute, Publication Date: 2025-01-27T00:00:00Z, Embedding Date: 2025-02-21T19:16:36Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 3 : symbiotic partners. Chemical Signaling: Communication mechanisms to coordinate symbiotic interactions. Methods of Detection Detecting symbiotic relationships on Europa would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to observe interactions in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of symbiotic interactions. Implications for Astrobiology The discovery of symbiotic relationships on Europa would have profound implications for our understanding of life in the universe. It would suggest that complex interactions can arise and thrive in environments vastly different (Page: 1, Title: Exploring the Possibility of Symbiosis Between Species on Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-26T00:00:00Z, Embedding Date: 2025-02-21T19:16:45Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 15 : for the conversion of methane into energy. Thick Cell Walls: To protect against radiation and physical damage. Symbiotic Relationships: With other organisms to enhance nutrient acquisition and energy production. Methods of Detection Detecting methane-based life on Europa would require advanced techniques, such as: Spectroscopy: To identify methane and related compounds in the subsurface ocean. Submersible Probes: Equipped with sensors to measure methane concentrations and biological activity. Sample Return Missions: To analyze water and ice samples for signs of methane-based organisms. Implications for Astrobiology The discovery of methane-based life on Europa would have profound implications for our understanding of life in (Page: 1, Title: Exploring the Possibility of Methane-Based Life on Europa, Author: Dr. Amanda Collins, Department of Biochemistry, Europa Research Institute Dr. Steven Wright, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-22T00:00:00Z, Embedding Date: 2025-02-21T19:16:50Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        
        prompt1 = "hello, what's the weather like today in Madrid?"
        '''
        prompt1 = "Question: What are the primary producers in the hypothetical food chains of Europa's subsurface oceans? -    Items elevant context: - Relevant context 2 : ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of complex food chains in Europa's subsurface oceans would have profound implications for our understanding of life in the universe. It would suggest that complex ecosystems can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Possible Food Chains in the Oceans of Europa, Author: Dr. Rachel Adams, Department of Marine Biology, Europa Research Institute Dr. Thomas Clark, Department of Ecology, Titan University, Publication Date: 2025-01-16T00:00:00Z, Embedding Date: 2025-02-21T19:16:34Z, Rights: This document is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for any purpose, even commercially, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt2 = "Question: What are the main environmental conditions that potential life forms on Europa must adapt to? - Items of relevant context: - Relevant context 12 : environment. These could include: Radiation Resistance: Enhanced DNA repair systems to cope with radiation-induced damage. Cryoprotection: Mechanisms to prevent ice crystal formation within cells. Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Methods of Detection Detecting evolutionary processes on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify evolutionary adaptations. Submersible Probes: Equipped with sensors to observe and study organisms in their natural habitat. Sample Return Missions: To analyze water and ice samples for signs of evolutionary processes. Implications for Astrobiology Understanding the evolution of life in a closed (Page: 1, Title: Analyzing the Evolution of Life in a Closed Environment Like Europa, Author: Dr. Jessica Taylor, Department of Evolutionary Biology, Europa Research Institute Dr. Daniel Roberts, Department of Astrobiology, Enceladus University, Publication Date: 2025-01-20T00:00:00Z, Embedding Date: 2025-02-21T19:16:58Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 9 : techniques, such as: Submersible Probes: Equipped with sensors to measure chemical gradients and biological activity in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for chemical composition and signs of life. Implications for Astrobiology Understanding the water chemistry in Europa's oceans and its impact on potential life forms would have profound implications for our understanding of life in the universe. It would suggest that life can adapt to a wide range of chemical environments, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Studying the Water Chemistry in the Oceans of Europa and Its Impact on Life, Author: Dr. Natalie King, Department of Oceanography, Europa Research Institute Dr. Peter Johnson, Department of Astrobiology, Triton University, Publication Date: 2025-01-21T00:00:00Z, Embedding Date: 2025-02-21T19:16:20Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt3 = "Question: What are the methods used to detect life in Europa's subsurface oceans? - Items of relevant context: - Relevant context 14 : potential habitats. Contamination: Ensuring that samples and instruments are not contaminated with Earth-based organisms. Implications for Astrobiology The discovery of life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Research Methods to Detect Life on Europa, Author: Dr. John Smith, Department of Astrobiology, Europa Research Institute Dr. Jane Doe, Department of Planetary Sciences, Mars Institute, Publication Date: 2025-01-27T00:00:00Z, Embedding Date: 2025-02-21T19:16:36Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt4 = "Question: What are the potential habitats in the depths of Europa's oceans? - Items of relevant context: - Relevant context 5 : thrive in their environment. These could include: Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Bioluminescence: To navigate, communicate, and hunt in the dark ocean. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting habitats in Europa's deep oceans would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the ocean depths. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for (Page: 1, Title: Describing the Potential Habitats in the Depths of the Oceans of Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-23T00:00:00Z, Embedding Date: 2025-02-21T19:16:54Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt5 = "Question: How do potential organisms on Europa adapt to high radiation levels and extreme cold temperatures? - Items of relevant context: - Relevant context 12 : environment. These could include: Radiation Resistance: Enhanced DNA repair systems to cope with radiation-induced damage. Cryoprotection: Mechanisms to prevent ice crystal formation within cells. Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Methods of Detection Detecting evolutionary processes on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify evolutionary adaptations. Submersible Probes: Equipped with sensors to observe and study organisms in their natural habitat. Sample Return Missions: To analyze water and ice samples for signs of evolutionary processes. Implications for Astrobiology Understanding the evolution of life in a closed (Page: 1, Title: Analyzing the Evolution of Life in a Closed Environment Like Europa, Author: Dr. Jessica Taylor, Department of Evolutionary Biology, Europa Research Institute Dr. Daniel Roberts, Department of Astrobiology, Enceladus University, Publication Date: 2025-01-20T00:00:00Z, Embedding Date: 2025-02-21T19:16:58Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 16 : compounds for energy. Methods of Detection Detecting extremophiles on Europa would require advanced techniques, such as: Submersible Probes: Equipped with microscopes and sensors to explore the ocean. Ice Penetrating Radar: To identify potential habitats beneath the ice. Sample Return Missions: To analyze water and ice samples for signs of extremophiles. Implications for Astrobiology The discovery of extremophile life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Exploring the Possibility of Extremophile Life on Europa, Author: Dr. Linda Harris, Department of Microbiology, Europa Research Institute Dr. Kevin Brown, Department of Astrobiology, Callisto University, Publication Date: 2025-01-18T00:00:00Z, Embedding Date: 2025-02-21T19:16:48Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 9 : techniques, such as: Submersible Probes: Equipped with sensors to measure chemical gradients and biological activity in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for chemical composition and signs of life. Implications for Astrobiology Understanding the water chemistry in Europa's oceans and its impact on potential life forms would have profound implications for our understanding of life in the universe. It would suggest that life can adapt to a wide range of chemical environments, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Studying the Water Chemistry in the Oceans of Europa and Its Impact on Life, Author: Dr. Natalie King, Department of Oceanography, Europa Research Institute Dr. Peter Johnson, Department of Astrobiology, Triton University, Publication Date: 2025-01-21T00:00:00Z, Embedding Date: 2025-02-21T19:16:20Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt6 = "Question: What are the possible biological mechanisms for photosynthesis in low-light conditions on Europa? - Items of relevant context: - Relevant context 6 : Protective Pigments: To shield against potential radiation damage while still allowing light absorption. Symbiotic Relationships: With other organisms to enhance nutrient acquisition and energy production. Methods of Detection Detecting photosynthetic processes in low-light conditions on Europa would require advanced techniques, such as: Spectroscopy: To identify specific pigments and light-harvesting complexes. Submersible Probes: Equipped with sensors to measure photosynthetic activity in the ocean. Sample Return Missions: To analyze water and ice samples for signs of photosynthetic organisms. Implications for Astrobiology The discovery of photosynthetic organisms in low-light conditions on Europa would have profound implications for our understanding of life in the (Page: 1, Title: Investigating Photosynthesis in Low-Light Conditions on Europa, Author: Dr. Sophia Turner, Department of Botany, Europa Research Institute Dr. Henry Walker, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-17T00:00:00Z, Embedding Date: 2025-02-21T19:16:38Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 15 : for the conversion of methane into energy. Thick Cell Walls: To protect against radiation and physical damage. Symbiotic Relationships: With other organisms to enhance nutrient acquisition and energy production. Methods of Detection Detecting methane-based life on Europa would require advanced techniques, such as: Spectroscopy: To identify methane and related compounds in the subsurface ocean. Submersible Probes: Equipped with sensors to measure methane concentrations and biological activity. Sample Return Missions: To analyze water and ice samples for signs of methane-based organisms. Implications for Astrobiology The discovery of methane-based life on Europa would have profound implications for our understanding of life in (Page: 1, Title: Exploring the Possibility of Methane-Based Life on Europa, Author: Dr. Amanda Collins, Department of Biochemistry, Europa Research Institute Dr. Steven Wright, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-22T00:00:00Z, Embedding Date: 2025-02-21T19:16:50Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 5 : thrive in their environment. These could include: Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Bioluminescence: To navigate, communicate, and hunt in the dark ocean. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting habitats in Europa's deep oceans would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the ocean depths. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for (Page: 1, Title: Describing the Potential Habitats in the Depths of the Oceans of Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-23T00:00:00Z, Embedding Date: 2025-02-21T19:16:54Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.)"
        prompt7 = "Question: What are the potential nutrient cycles in Europa's ecosystems and how do they support life? Items of relevant context: - Relevant context 19 : Return Missions: To analyze water and ice samples for signs of nutrient cycling processes. Implications for Astrobiology The discovery of complex nutrient cycles in Europa's ecosystems would have profound implications for our understanding of life in the universe. It would suggest that complex ecosystems can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Nutrient Cycles in the Ecosystems of Europa, Author: Dr. Maria Lopez, Department of Ecology, Europa Research Institute Dr. Richard Evans, Department of Environmental Sciences, Titan University, Publication Date: 2025-01-19T00:00:00Z, Embedding Date: 2025-02-21T19:16:23Z, Rights: This document is licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for any purpose, even commercially, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made.) - Relevant context 2 : ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of complex food chains in Europa's subsurface oceans would have profound implications for our understanding of life in the universe. It would suggest that complex ecosystems can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Possible Food Chains in the Oceans of Europa, Author: Dr. Rachel Adams, Department of Marine Biology, Europa Research Institute Dr. Thomas Clark, Department of Ecology, Titan University, Publication Date: 2025-01-16T00:00:00Z, Embedding Date: 2025-02-21T19:16:34Z, Rights: This document is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for any purpose, even commercially, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 9 : techniques, such as: Submersible Probes: Equipped with sensors to measure chemical gradients and biological activity in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for chemical composition and signs of life. Implications for Astrobiology Understanding the water chemistry in Europa's oceans and its impact on potential life forms would have profound implications for our understanding of life in the universe. It would suggest that life can adapt to a wide range of chemical environments, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Studying the Water Chemistry in the Oceans of Europa and Its Impact on Life, Author: Dr. Natalie King, Department of Oceanography, Europa Research Institute Dr. Peter Johnson, Department of Astrobiology, Triton University, Publication Date: 2025-01-21T00:00:00Z, Embedding Date: 2025-02-21T19:16:20Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt8 = "Question: How do potential symbiotic relationships on Europa contribute to the survival and diversity of life forms? Items of relevant context: - Relevant context 3 : symbiotic partners. Chemical Signaling: Communication mechanisms to coordinate symbiotic interactions. Methods of Detection Detecting symbiotic relationships on Europa would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to observe interactions in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of symbiotic interactions. Implications for Astrobiology The discovery of symbiotic relationships on Europa would have profound implications for our understanding of life in the universe. It would suggest that complex interactions can arise and thrive in environments vastly different (Page: 1, Title: Exploring the Possibility of Symbiosis Between Species on Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-26T00:00:00Z, Embedding Date: 2025-02-21T19:16:45Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 4 : between different species to enhance adaptability. Symbiotic Relationships: Evolution of mutualistic relationships that promote genetic exchange and diversity. Adaptive Radiation: Rapid diversification of species to exploit different ecological niches. Methods of Detection Detecting genetic diversity on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify genetic variations and adaptations. Submersible Probes: Equipped with sensors to collect and analyze genetic material in the ocean. Sample Return Missions: To analyze water and ice samples for signs of genetic diversity. Implications for Astrobiology Understanding the genetic diversity of possible organisms on Europa would have profound (Page: 1, Title: Analyzing the Genetic Diversity of Possible Organisms on Europa, Author: Dr. Sarah Johnson, Department of Genetics, Europa Research Institute Dr. David Lee, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-25T00:00:00Z, Embedding Date: 2025-02-21T19:16:26Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 16 : compounds for energy. Methods of Detection Detecting extremophiles on Europa would require advanced techniques, such as: Submersible Probes: Equipped with microscopes and sensors to explore the ocean. Ice Penetrating Radar: To identify potential habitats beneath the ice. Sample Return Missions: To analyze water and ice samples for signs of extremophiles. Implications for Astrobiology The discovery of extremophile life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Exploring the Possibility of Extremophile Life on Europa, Author: Dr. Linda Harris, Department of Microbiology, Europa Research Institute Dr. Kevin Brown, Department of Astrobiology, Callisto University, Publication Date: 2025-01-18T00:00:00Z, Embedding Date: 2025-02-21T19:16:48Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 5 : thrive in their environment. These could include: Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Bioluminescence: To navigate, communicate, and hunt in the dark ocean. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting habitats in Europa's deep oceans would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the ocean depths. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for (Page: 1, Title: Describing the Potential Habitats in the Depths of the Oceans of Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-23T00:00:00Z, Embedding Date: 2025-02-21T19:16:54Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.)"
        prompt9 = "hello, how are you?"
        prompt10 = "hello, how are you?"
        
        # Diccionario que mapea los valores de question a las variables prompt
        prompts = {
            1: prompt1,
            2: prompt2,
            3: prompt3,
            4: prompt4,
            5: prompt5,
            6: prompt6,
            7: prompt7,
            8: prompt8,
            9: prompt9,
            10: prompt10
        }

        #escribimos la pregunta para poder llamarla con un número en las pruebas
        if question.isdigit():
            value = int(question)
            if 1 <= value <= 10:
                texts = {
                    1: "What are the primary producers in the hypothetical food chains of Europa's subsurface oceans?",
                    2: "What are the main environmental conditions that potential life forms on Europa must adapt to?",
                    3: "What are the methods used to detect life in Europa's subsurface oceans?",
                    4: "What are the potential habitats in the depths of Europa's oceans?",
                    5: "How do potential organisms on Europa adapt to high radiation levels and extreme cold temperatures?",
                    6: "What are the possible biological mechanisms for photosynthesis in low-light conditions on Europa?",
                    7: "What are the potential nutrient cycles in Europa's ecosystems and how do they support life?",
                    8: "How do potential symbiotic relationships on Europa contribute to the survival and diversity of life forms?",
                    9: "What are the challenges and limitations in detecting life on Europa, and how do researchers overcome them?",
                    10: "How does the potential genetic diversity of organisms on Europa relate to the research methods used to detect life, and what role does gender bias play in the research process?"
                }
                question = texts[value]
                
        # Asignamos la variable prompt correspondiente
        prompt = prompts.get(value, prompt1)
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
                temperature=0.3
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
                max_tokens=1000,
                n=1,
                temperature=0.3
        )

        # Imprimir la respuesta generada
        logger.info("Iniciamos la impresión de las preguntas")

        # Reemplazar el marcador <CURRENT_DATE> por la fecha actual
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        answer1 = response1.choices[0].message.content
        answer2 = response2.choices[0].message.content.replace("31-12-9999", current_date)
        answer1 = markdown.markdown(answer1, extensions=['extra', 'nl2br'])
        answer2 = markdown.markdown(answer2, extensions=['extra', 'nl2br'])

        
        '''
        # Almacenar la salida de Weaviate en answer1
        answer1 = prompt
        # Almacenar el prompt construido en answer2
        answer2 = None 
        '''
    return render_template_string('''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>TRUSTWORTHY RAG</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background-color: #f4f4f4;
      margin: 0;
      padding: 0;
    }
    .container {
      max-width: 1000px;
      margin: 50px auto;
      background: #fff;
      padding: 30px;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    h1 {
      text-align: center;
      color: #333;
    }
    form {
      margin-bottom: 30px;
    }
    label {
      font-weight: bold;
    }
    .question-container {
      display: flex;
      align-items: flex-start;
      gap: 10px;
    }
    .question-container textarea {
      flex: 1;
      padding: 10px;
      font-size: 16px;
      border: 1px solid #ccc;
      border-radius: 4px;
      resize: vertical;
    }
    .question-container input[type="submit"] {
      background-color: #5cb85c;
      color: #fff;
      border: none;
      padding: 10px 20px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 16px;
      align-self: center;
    }
    .question-container input[type="submit"]:hover {
      background-color: #4cae4c;
    }
    .answer {
      border-top: 2px solid #eee;
      padding-top: 20px;
      margin-top: 20px;
    }
    .answer h2 {
      color: #333;
    }
    a.logout {
      display: inline-block;
      margin-top: 20px;
      color: #d9534f;
      text-decoration: none;
    }
    a.logout:hover {
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>TRUSTWORTHY RAG</h1>
    <form method="post">
      <label for="question">Write your question:</label><br><br>
      <div class="question-container">
        <textarea id="question" name="question" rows="2" maxlength="800">{{ question|default('') }}</textarea>
        <input type="submit" value="Enviar">
      </div>
    </form>
    {% if answer1 %}
      <div class="answer">
        <h2>Standard Answer:</h2>
        <div>{{ answer1|safe }}</div>
      </div>
    {% endif %}
    {% if answer2 %}
      <div class="answer">
        <h2>Trustworthy Answer:</h2>
        <div>{{ answer2|safe }}</div>
      </div>
    {% endif %}
    {% if error %}
      <div class="answer">
        <h2>Error:</h2>
        <p>{{ error }}</p>
      </div>
    {% endif %}
    <a class="logout" href="{{ url_for('logout') }}">Logout</a>
  </div>
</body>
</html>
    ''', question=question, answer1=answer1, answer2=answer2, error=error)

if __name__ == '__main__':
    app.run(debug=True)
